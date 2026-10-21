"""The helper bridge: Claude Code's background agents, as Appling's helpers.

Appling's own agents run in the background, so its turn ends at once and the
owner can talk to it while they work. Their progress reaches the runner as
``helper`` events; each report arrives later as a turn of its own.
"""

from __future__ import annotations

import asyncio
import logging
import re

from lyra_lite.engines.claude.common import AGENT_TOOLS, TOOL_NAMES, _preview, _result_text

logger = logging.getLogger(__name__)

REPORT_PREFIX = "<task-notification>"


async def _background_agents(hook_input, tool_use_id, context):
    """Appling's own agents run in the background, so its turn ends at once and
    the owner can talk to it while they work; each report arrives as its own
    turn. An agent's agents (agent_id set) are left as the agent chose."""
    if hook_input.get("agent_id"):
        return {}
    tool_input = dict(hook_input.get("tool_input") or {})
    if tool_input.get("run_in_background"):
        return {}
    tool_input["run_in_background"] = True
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "allow",
                                   "updatedInput": tool_input}}


class HelpersMixin:
    """ClaudeEngine's helper bookkeeping: ``_agents`` (running), ``_task_ids``,
    ``_backgrounded``, ``_goals`` and ``_reports``."""

    async def _agents_hook(self, hook_input, tool_use_id, context):
        call_id = hook_input.get("tool_use_id") or tool_use_id
        if not hook_input.get("agent_id") and call_id:
            self._backgrounded.add(call_id)
        return await _background_agents(hook_input, tool_use_id, context)

    def _emit_helper(self, **data) -> None:
        if self._hooks is not None:
            self._hooks.emit("helper", **data)

    # -- messages from the Claude program --------------------------------

    def _helper_started(self, msg) -> None:
        """A TaskStartedMessage."""
        key = msg.tool_use_id or msg.task_id
        self._task_ids[key] = msg.task_id
        if key not in self._agents:
            self._agents[key] = msg.description
            self._goals.setdefault(key, msg.description)
            self._emit_helper(event="start", subagent_id=key, goal=msg.description)

    def _helper_notified(self, msg) -> None:
        """A TaskNotificationMessage: a helper finished."""
        key = msg.tool_use_id or msg.task_id
        goal = self._agents.pop(key, "")
        self._task_ids.pop(key, None)
        self._backgrounded.discard(key)
        self._emit_helper(event="complete", subagent_id=key, goal=goal,
                          status="completed" if str(msg.status) == "completed" else str(msg.status),
                          summary=_preview(msg.summary or "", 1200))
        if self._current is None:
            # Claude is idle, so it starts a turn of its own to read this.
            self._reports.append((goal or self._goals.get(key, "") or str(msg.summary or ""),
                                  _preview(msg.summary or "", 1200)))

    def _helper_activity(self, parent: str, msg) -> None:
        """A message from inside a helper (parent_tool_use_id set)."""
        from claude_agent_sdk import AssistantMessage

        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                name = getattr(block, "name", None)
                if name:
                    self._emit_helper(event="tool", subagent_id=parent, tool=TOOL_NAMES.get(name, name))

    def _helper_called(self, turn, block) -> bool:
        """An Agent/Task tool call in Appling's own turn; False for other tools."""
        if block.name not in AGENT_TOOLS:
            return False
        goal = str(block.input.get("description") or block.input.get("prompt") or "")[:300]
        self._agents[block.id] = goal
        self._goals[block.id] = goal
        turn.emit("tool", phase="start", id=block.id, name="delegate_task", args=_preview(block.input))
        self._emit_helper(event="start", subagent_id=block.id, goal=goal)
        return True

    def _helper_result(self, block) -> None:
        """A tool result that may end a helper: a foreground one finished, or
        one failed to start."""
        if block.tool_use_id in self._agents and block.tool_use_id not in self._backgrounded:
            goal = self._agents.pop(block.tool_use_id)
            self._emit_helper(event="complete", subagent_id=block.tool_use_id, goal=goal,
                              status="failed" if block.is_error else "completed",
                              summary=_preview(_result_text(block.content), 1200))
        elif block.is_error and block.tool_use_id in self._agents:
            self._agents.pop(block.tool_use_id, None)  # never started
            self._emit_helper(event="complete", subagent_id=block.tool_use_id, goal="",
                              status="failed", summary=_preview(_result_text(block.content), 1200))

    def _report_parts(self, text: str) -> tuple[str, str]:
        """The helper's goal and summary from the CLI's <task-notification>."""
        def tag(name: str) -> str:
            m = re.search(rf"<{name}>(.*?)</{name}>", text, re.S)
            return m.group(1).strip() if m else ""

        call_id = tag("tool-use-id")
        summary = tag("summary") or tag("result")
        goal = self._goals.get(call_id, "") or summary
        return goal[:300], _preview(summary, 1200)

    # -- control ---------------------------------------------------------

    def stop_helpers(self) -> int:
        """Stop every helper, including ones running in the background."""
        running = len(self._agents)
        client, loop = self._client, self._loop
        if client is not None and loop is not None:
            for task_id in list(self._task_ids.values()):
                try:
                    asyncio.run_coroutine_threadsafe(client.stop_task(task_id), loop).result(10)
                # The SDK raises a bare Exception when the CLI doesn't answer a
                # control request, so nothing narrower is safe; one helper that
                # won't stop must not keep the rest running or skip the interrupt.
                except Exception:
                    logger.debug("could not stop helper %s", task_id, exc_info=True)
        if running:
            self.interrupt()
        return running

    def helpers(self) -> list[dict]:
        return [{"id": k, "goal": v, "started": None} for k, v in list(self._agents.items())]
