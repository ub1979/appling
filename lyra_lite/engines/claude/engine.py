"""ClaudeEngine: the Claude program's event loop, connection and controls.

Turn handling, the helper bridge and tool permissions live in their own
mixins; this class owns the state they share.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from lyra_lite.engines.base import TurnHooks, TurnResult
from lyra_lite.engines.claude import routes
from lyra_lite.engines.claude.common import DISALLOWED
from lyra_lite.engines.claude.helpers import HelpersMixin
from lyra_lite.engines.claude.permissions import PermissionsMixin
from lyra_lite.engines.claude.playbooks import builder_plugin_dir, engine_notes
from lyra_lite.engines.claude.turns import TurnsMixin, _Turn

logger = logging.getLogger(__name__)


class ClaudeEngine(TurnsMixin, HelpersMixin, PermissionsMixin):
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
        self._task_ids: dict[str, str] = {}  # tool_use_id -> the CLI's task id (to stop it)
        self._backgrounded: set[str] = set()  # Agent calls whose result is only "started"
        self._pending: list[_Turn] = []  # sent to Claude, not started yet
        self._current: _Turn | None = None
        self._starting = False
        self._carry = ""
        self._reader: asyncio.Task | None = None
        self._goals: dict[str, str] = {}  # tool_use_id -> goal, kept for naming reports
        self._reports: list[tuple[str, str]] = []  # helpers that finished while Claude was idle
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
        return routes.claude_env(self.settings)

    def _memory_server(self):
        """project_recall as an in-process tool for Claude Code (and its agents)."""
        from claude_agent_sdk import create_sdk_mcp_server, tool

        from lyra_lite.memory import RECALL_DESCRIPTION, ProjectMemory, format_results

        root = self.workspace

        @tool("project_recall", RECALL_DESCRIPTION,
              {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})
        async def project_recall(args):
            query = str(args.get("query") or "").strip()
            results = await asyncio.to_thread(ProjectMemory(root).search, query) if query else []
            return {"content": [{"type": "text", "text": format_results(query, results)}]}

        return create_sdk_mcp_server("lyra", tools=[project_recall])

    async def _connect(self):
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher

        state = self.store.state() if self.store is not None else {}
        resume = state.get("claude_session") if state.get("claude_chat") == state.get("chat_id") else None
        options = ClaudeAgentOptions(
            cwd=self.workspace,
            model=routes.claude_model(self.settings),
            effort=routes.claude_effort(self.settings),
            permission_mode="acceptEdits",
            system_prompt={"type": "preset", "preset": "claude_code",
                           "append": self.system_prompt + engine_notes()},
            include_partial_messages=True,
            setting_sources=[],
            plugins=[{"type": "local", "path": str(builder_plugin_dir())}],
            mcp_servers={"lyra": self._memory_server()},
            can_use_tool=self._can_use_tool,
            disallowed_tools=list(DISALLOWED),
            hooks={"PreToolUse": [HookMatcher(matcher="Agent|Task", hooks=[self._agents_hook])]},
            # Echo each turn's first message, so a turn Appling asked for can be
            # told from one the Claude program started for a helper's report.
            extra_args={"replay-user-messages": None},
            resume=resume or None,
            env=self._env(),
            cli_path=routes.claude_cli_path(self.settings),
        )
        client = ClaudeSDKClient(options)
        await client.connect()
        return client, bool(resume)

    # -- turn ------------------------------------------------------------

    def run_turn(self, text: str, history: list[dict], hooks: TurnHooks) -> TurnResult:
        self._hooks = hooks
        self._interrupted = False
        try:
            reply, usage, error, interrupted = self._call(self._ask(text, history, hooks))
        # Last resort: route errors ("isn't installed", no API key), SDK connect
        # failures and anything else become the error the runner shows,
        # instead of an exception that leaves the project busy.
        except Exception as exc:
            logger.exception("lyra-lite: claude turn failed")
            return TurnResult(reply="", messages=list(history), completed=False,
                              error=f"{type(exc).__name__}: {exc}")
        messages = list(history) + [{"role": "user", "content": text}]
        if reply:
            messages.append({"role": "assistant", "content": reply})
        return TurnResult(reply=reply, messages=messages, completed=error is None and not interrupted,
                          interrupted=interrupted, error=error, usage=usage)

    async def _ask(self, text: str, history: list[dict], hooks: TurnHooks):
        resumed = True
        if self._client is None:
            self._client, resumed = await self._connect()
            self._reader = asyncio.get_running_loop().create_task(self._read(self._client))
        prompt = text
        if not resumed and history:
            prompt = self._seed(history) + text
        turn = _Turn(hooks, prompt, asyncio.get_running_loop().create_future())
        turn.carry, self._carry = self._carry, ""
        self._pending.append(turn)
        await self._client.query(prompt)
        return await turn.future

    # -- control ---------------------------------------------------------

    def interrupt(self) -> None:
        self._interrupted = True
        client = self._client
        if client is not None and self._loop is not None:
            try:
                asyncio.run_coroutine_threadsafe(client.interrupt(), self._loop).result(10)
            # The SDK raises a bare Exception when the CLI doesn't answer a
            # control request, so nothing narrower is safe; _stop_turn below
            # must still run, since it is what ends the turn either way.
            except Exception:
                logger.warning("claude interrupt failed", exc_info=True)
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._stop_turn)

    def close(self) -> None:
        client, self._client = self._client, None
        reader, self._reader = self._reader, None
        if reader is not None and self._loop is not None:
            self._loop.call_soon_threadsafe(reader.cancel)
        if client is not None and self._loop is not None:
            try:
                asyncio.run_coroutine_threadsafe(client.disconnect(), self._loop).result(15)
            # Last resort: the program may already be gone or hung; closing must
            # still stop the loop below.
            except Exception:
                logger.debug("claude disconnect failed", exc_info=True)
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._loop = None
        self._hooks = None
