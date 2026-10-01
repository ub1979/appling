"""Claude Code (via the Claude Agent SDK) as a Lyra Lite engine.

The model is chosen separately from the engine: an Anthropic API key runs
Claude models; a custom Anthropic-compatible address (for example Ollama)
runs other models through the same engine. Lyra never falls back to a
Claude subscription login — the CLI gets its own config folder.

Safety matches the Hermes engine: file edits inside the project are allowed,
shell commands that Hermes' danger check flags go to the owner's inbox.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from lyra_lite.engines.base import TurnHooks, TurnResult

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5-5"
APPROVAL_TIMEOUT_S = 30 * 60
REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = REPO_ROOT / "plugins" / "ultimate-builder" / "skills"

# Claude Code tool names -> the names the Lyra screen already words nicely.
TOOL_NAMES = {
    "Bash": "terminal", "Read": "read_file", "Write": "write_file", "Edit": "patch",
    "MultiEdit": "patch", "NotebookEdit": "patch", "Glob": "search_files",
    "Grep": "search_files", "WebSearch": "web_search", "WebFetch": "web_extract",
    "TodoWrite": "todo", "Task": "delegate_task", "Agent": "delegate_task",
    "Skill": "skill_view",
}
AGENT_TOOLS = {"Task", "Agent"}
# Claude Code tools Lyra must not use: scheduling itself, background agent
# plumbing it can't observe, and worktree/workflow modes outside the project.
DISALLOWED = ["CronCreate", "CronDelete", "CronList", "ScheduleWakeup", "EnterWorktree",
              "ExitWorktree", "Workflow", "ReportFindings", "SendMessage", "ListAgents"]
ALWAYS_OK = {"WebSearch", "WebFetch", "TodoWrite", "Read", "Glob", "Grep"}


def _skill_index() -> str:
    lines = []
    for path in sorted(SKILLS_ROOT.rglob("SKILL.md")):
        lines.append(f"- ultimate-builder:{path.parent.name} → {path}")
    return "\n".join(lines)


def engine_notes() -> str:
    try:
        app_it = (SKILLS_ROOT / "app-it" / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        app_it = ""
    return f"""
## Running on Claude Code

The playbooks were written for another engine. Translate their tool names:
- `delegate_task` → the Agent (Task) tool. Run agents in the foreground; to
  work in parallel, start several in one message. Give each the task, the files
  it owns and the playbook path to read.
- `skill_view(name="ultimate-builder:X")` → Read the playbook file for X below.
- `clarify` → ask in your reply and end the turn.
- `terminal` → Bash; `read_file`/`write_file`/`patch`/`search_files` →
  Read/Write/Edit/Grep/Glob; `todo` → TodoWrite.

Playbooks:
{_skill_index()}

## The app-it playbook (already loaded)

{app_it}
"""


def _preview(value: Any, limit: int = 300) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    try:
        from agent.redact import redact_sensitive_text

        text = redact_sensitive_text(text)
    except Exception:
        pass
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(c.get("text") or "") for c in content if isinstance(c, dict))
    return ""


async def _foreground_agents(hook_input, tool_use_id, context):
    """Agents run in the foreground so their results land inside the turn."""
    tool_input = dict(hook_input.get("tool_input") or {})
    if not tool_input.get("run_in_background"):
        return {}
    tool_input["run_in_background"] = False
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "allow",
                                   "updatedInput": tool_input}}


class ClaudeEngine:
    name = "claude"

    def __init__(self, *, workspace: str, session_key: str, system_prompt: str = "",
                 store=None, settings: dict | None = None, **_ignored: Any):
        self.workspace = workspace
        self.session_key = session_key
        self.system_prompt = system_prompt
        self.store = store
        self.settings = dict(settings or {})
        self._hooks: TurnHooks | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._client = None
        self._agents: dict[str, str] = {}  # tool_use_id -> goal (running)
        self._session_allowed: set[str] = set()
        self._interrupted = False
        self._lock = threading.Lock()

    # -- loop / client ---------------------------------------------------

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None:
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(target=self._loop.run_forever,
                                                name="lyra-claude-loop", daemon=True)
                self._thread.start()
            return self._loop

    def _call(self, coro, timeout: float | None = None):
        loop = self._ensure_loop()
        return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout)

    def _env(self) -> dict[str, str]:
        from hermes_constants import get_hermes_home

        config_dir = get_hermes_home() / "lyra-lite" / "claude-config"
        config_dir.mkdir(parents=True, exist_ok=True)
        env = {
            "CLAUDE_CONFIG_DIR": str(config_dir),
            "DISABLE_TELEMETRY": "1",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        }
        base_url = str(self.settings.get("base_url") or "").strip()
        if base_url:
            env["ANTHROPIC_BASE_URL"] = base_url
            env["ANTHROPIC_AUTH_TOKEN"] = str(self.settings.get("auth_token") or "ollama")
            env["ANTHROPIC_API_KEY"] = ""
            return env
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "The Claude engine needs an Anthropic API key (add ANTHROPIC_API_KEY with "
                "`hermes setup` or to ~/.hermes/.env), or a custom model address such as "
                "Ollama in this project's engine settings."
            )
        env["ANTHROPIC_API_KEY"] = key
        return env

    async def _connect(self):
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher

        state = self.store.state() if self.store is not None else {}
        resume = state.get("claude_session") if state.get("claude_chat") == state.get("chat_id") else None
        options = ClaudeAgentOptions(
            cwd=self.workspace,
            model=str(self.settings.get("model") or DEFAULT_MODEL),
            permission_mode="acceptEdits",
            system_prompt={"type": "preset", "preset": "claude_code",
                           "append": self.system_prompt + engine_notes()},
            include_partial_messages=True,
            setting_sources=[],
            can_use_tool=self._can_use_tool,
            disallowed_tools=list(DISALLOWED),
            hooks={"PreToolUse": [HookMatcher(matcher="Agent|Task", hooks=[_foreground_agents])]},
            resume=resume or None,
            env=self._env(),
        )
        client = ClaudeSDKClient(options)
        await client.connect()
        return client, bool(resume)

    # -- permissions -----------------------------------------------------

    async def _can_use_tool(self, tool_name: str, tool_input: dict, context):
        from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

        if tool_name in ALWAYS_OK:
            return PermissionResultAllow()
        command = str(tool_input.get("command") or "") if tool_name == "Bash" else ""
        pattern = tool_name
        description = f"Claude wants to use {tool_name}"
        if tool_name == "Bash":
            from tools.approval import detect_dangerous_command, detect_hardline_command, is_approved

            hard, hard_desc = detect_hardline_command(command)[:2]
            if hard:
                return PermissionResultDeny(message=f"BLOCKED: {hard_desc}. Never run this.")
            dangerous, pattern_key, desc = detect_dangerous_command(command)
            if not dangerous:
                return PermissionResultAllow()
            pattern = str(pattern_key)
            description = str(desc)
            if pattern in self._session_allowed or is_approved(self.session_key, pattern):
                return PermissionResultAllow()
        elif pattern in self._session_allowed:
            return PermissionResultAllow()

        hooks = self._hooks
        if hooks is None:
            return PermissionResultDeny(message="No owner is available to approve this.")
        loop = asyncio.get_running_loop()
        answer: asyncio.Future = loop.create_future()

        def _on_answer(value: Any) -> None:
            loop.call_soon_threadsafe(lambda: answer.done() or answer.set_result(value))

        item_id = hooks.ask("approval", _on_answer,
                            command=command or _preview(tool_input, 500),
                            description=description,
                            choices=["once", "session", "always", "deny"])
        try:
            choice = str(await asyncio.wait_for(answer, APPROVAL_TIMEOUT_S) or "deny")
        except asyncio.TimeoutError:
            hooks.expire(item_id)
            choice = "deny"
        if choice == "deny":
            return PermissionResultDeny(
                message="BLOCKED: the owner did not allow this. Do not retry it or work around it.")
        if choice in {"session", "always"}:
            self._session_allowed.add(pattern)
        if choice == "always" and tool_name == "Bash":
            try:
                from tools.approval import _permanent_approved, approve_permanent, save_permanent_allowlist

                approve_permanent(pattern)
                save_permanent_allowlist(_permanent_approved)
            except Exception:
                logger.debug("could not save permanent approval", exc_info=True)
        return PermissionResultAllow()

    # -- turn ------------------------------------------------------------

    def run_turn(self, text: str, history: list[dict], hooks: TurnHooks) -> TurnResult:
        self._hooks = hooks
        self._interrupted = False
        try:
            reply, usage, error, interrupted = self._call(self._turn(text, history, hooks))
        except Exception as exc:
            logger.exception("lyra-lite: claude turn failed")
            return TurnResult(reply="", messages=list(history), completed=False,
                              error=f"{type(exc).__name__}: {exc}")
        messages = list(history) + [{"role": "user", "content": text}]
        if reply:
            messages.append({"role": "assistant", "content": reply})
        return TurnResult(reply=reply, messages=messages, completed=error is None and not interrupted,
                          interrupted=interrupted, error=error, usage=usage)

    async def _turn(self, text: str, history: list[dict], hooks: TurnHooks):
        from claude_agent_sdk import (
            AssistantMessage, ResultMessage, StreamEvent, TaskNotificationMessage,
            TaskStartedMessage, TextBlock, ToolResultBlock, ToolUseBlock, UserMessage,
        )

        resumed = True
        if self._client is None:
            self._client, resumed = await self._connect()
        prompt = text
        if not resumed and history:
            prompt = self._seed(history) + text

        await self._client.query(prompt)
        streamed_any = False
        need_gap = False
        texts: list[str] = []
        tool_names: dict[str, str] = {}
        result_text, usage, error, interrupted = None, {}, None, False
        async for msg in self._client.receive_response():
            if isinstance(msg, StreamEvent):
                if msg.parent_tool_use_id:
                    continue
                event = msg.event or {}
                if event.get("type") == "message_start" and streamed_any:
                    need_gap = True
                delta = event.get("delta") or {}
                if event.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                    piece = str(delta.get("text") or "")
                    if piece:
                        if need_gap:
                            hooks.emit("delta", text="\n\n")
                            need_gap = False
                        hooks.emit("delta", text=piece)
                        streamed_any = True
            elif isinstance(msg, AssistantMessage):
                parent = msg.parent_tool_use_id
                for block in msg.content:
                    if isinstance(block, ToolUseBlock):
                        tool_names[block.id] = block.name
                        if parent:
                            hooks.emit("helper", event="tool", subagent_id=parent,
                                       tool=TOOL_NAMES.get(block.name, block.name))
                        elif block.name in AGENT_TOOLS:
                            goal = str(block.input.get("description") or block.input.get("prompt") or "")[:300]
                            self._agents[block.id] = goal
                            hooks.emit("tool", phase="start", id=block.id, name="delegate_task",
                                       args=_preview(block.input))
                            hooks.emit("helper", event="start", subagent_id=block.id, goal=goal)
                        else:
                            hooks.emit("tool", phase="start", id=block.id,
                                       name=TOOL_NAMES.get(block.name, block.name),
                                       args=_preview(block.input))
                    elif isinstance(block, TextBlock) and not parent:
                        texts.append(block.text)
            elif isinstance(msg, UserMessage):
                if msg.parent_tool_use_id or isinstance(msg.content, str):
                    continue
                for block in msg.content:
                    if not isinstance(block, ToolResultBlock):
                        continue
                    name = tool_names.get(block.tool_use_id, "")
                    if block.tool_use_id in self._agents:
                        goal = self._agents.pop(block.tool_use_id)
                        hooks.emit("helper", event="complete", subagent_id=block.tool_use_id,
                                   goal=goal, status="failed" if block.is_error else "completed",
                                   summary=_preview(_result_text(block.content), 1200))
                    hooks.emit("tool", phase="done", id=block.tool_use_id,
                               name=TOOL_NAMES.get(name, name),
                               result=_preview(_result_text(block.content)))
            elif isinstance(msg, TaskStartedMessage):
                key = msg.tool_use_id or msg.task_id
                if key not in self._agents:
                    self._agents[key] = msg.description
                    hooks.emit("helper", event="start", subagent_id=key, goal=msg.description)
            elif isinstance(msg, TaskNotificationMessage):
                key = msg.tool_use_id or msg.task_id
                goal = self._agents.pop(key, "")
                hooks.emit("helper", event="complete", subagent_id=key, goal=goal,
                           status="completed" if str(msg.status) == "completed" else str(msg.status),
                           summary=_preview(msg.summary or "", 1200))
            elif isinstance(msg, ResultMessage):
                result_text = msg.result
                usage = {k: v for k, v in {
                    "cost_usd": msg.total_cost_usd, "num_turns": msg.num_turns,
                    "duration_ms": msg.duration_ms}.items() if v is not None}
                interrupted = self._interrupted
                if msg.is_error and not interrupted:
                    error = f"Claude engine: {msg.subtype}"
                if self.store is not None and msg.session_id:
                    state = self.store.state()
                    self.store.update_state(claude_session=msg.session_id,
                                            claude_chat=state.get("chat_id"))
        reply = (result_text or (texts[-1] if texts else "")).strip()
        if reply and not streamed_any:
            hooks.emit("delta", text=reply)
        return reply, usage, error, interrupted

    @staticmethod
    def _seed(history: list[dict]) -> str:
        lines = []
        for m in history[-30:]:
            content = m.get("content")
            if m.get("role") in {"user", "assistant"} and isinstance(content, str) and content.strip():
                lines.append(f"{m['role'].upper()}: {content.strip()[:2000]}")
        convo = "\n\n".join(lines)[-12000:]
        return ("(This project's conversation so far, from before this engine took over:)\n\n"
                f"{convo}\n\n(The owner's new message:)\n\n")

    # -- control ---------------------------------------------------------

    def interrupt(self) -> None:
        self._interrupted = True
        client = self._client
        if client is not None and self._loop is not None:
            try:
                asyncio.run_coroutine_threadsafe(client.interrupt(), self._loop).result(10)
            except Exception:
                logger.debug("claude interrupt failed", exc_info=True)

    def stop_helpers(self) -> int:
        running = len(self._agents)
        if running:
            self.interrupt()
        return running

    def helpers(self) -> list[dict]:
        return [{"id": k, "goal": v, "started": None} for k, v in list(self._agents.items())]

    def close(self) -> None:
        client, self._client = self._client, None
        if client is not None and self._loop is not None:
            try:
                asyncio.run_coroutine_threadsafe(client.disconnect(), self._loop).result(15)
            except Exception:
                pass
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._loop = None
        self._hooks = None
