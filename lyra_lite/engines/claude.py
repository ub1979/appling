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
OLLAMA_URL = "http://localhost:11434"
ROUTES = ("subscription", "ollama", "api", "custom")


def claude_route(settings: dict) -> str:
    route = str(settings.get("route") or "")
    if route in ROUTES:
        return route
    return "custom" if settings.get("base_url") else "subscription"


def find_claude_cli() -> str | None:
    import shutil

    found = shutil.which("claude")
    if found:
        return found
    for candidate in (Path.home() / ".local" / "bin" / "claude", Path("/opt/homebrew/bin/claude")):
        if candidate.exists():
            return str(candidate)
    return None


def claude_cli_status() -> dict:
    """Is the owner's Claude program installed and signed in to a plan?"""
    import json as _json
    import subprocess

    path = find_claude_cli()
    if not path:
        return {"found": False, "logged_in": False}
    env = {k: v for k, v in os.environ.items()
           if k not in {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"}}
    try:
        out = subprocess.run([path, "auth", "status", "--json"], capture_output=True, text=True,
                             timeout=20, env=env).stdout
        data = _json.loads(out or "{}")
    except Exception:
        return {"found": True, "logged_in": False}
    return {"found": True, "logged_in": bool(data.get("loggedIn")),
            "method": data.get("authMethod"), "plan": data.get("subscriptionType")}
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
ALWAYS_OK = {"WebSearch", "WebFetch", "TodoWrite", "Read", "Glob", "Grep", "Skill"}


def _skill_index() -> str:
    lines = []
    for path in sorted(SKILLS_ROOT.rglob("SKILL.md")):
        lines.append(f"- ultimate-builder:{path.parent.name} → {path}")
    return "\n".join(lines)


PLUGIN_NAME = "ultimate-builder"


def builder_plugin_dir() -> Path:
    """Lyra's builder playbooks as a native Claude Code plugin.

    The playbooks are already SKILL.md files. Linked into a plugin called
    ``ultimate-builder`` they load with Claude Code's own Skill tool under the
    same names Hermes uses (``ultimate-builder:req-engineer`` …), instead of
    relying on the model choosing to read a file.
    """
    from hermes_constants import get_hermes_home

    root = get_hermes_home() / "lyra-lite" / "claude-plugin" / PLUGIN_NAME
    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    manifest = {"name": PLUGIN_NAME, "version": "1.0.0",
                "description": "Lyra's application-builder playbooks."}
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest, indent=2) + "\n")
    skills = root / "skills"
    skills.mkdir(exist_ok=True)
    wanted = {path.parent.name: path.parent for path in SKILLS_ROOT.rglob("SKILL.md")}
    for link in skills.iterdir():
        if link.name not in wanted or not link.is_symlink() or link.resolve() != wanted[link.name].resolve():
            if link.is_symlink() or link.is_file():
                link.unlink()
    for name, target in wanted.items():
        link = skills / name
        if not link.exists():
            link.symlink_to(target, target_is_directory=True)
    return root


def engine_notes() -> str:
    try:
        app_it = (SKILLS_ROOT / "app-it" / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        app_it = ""
    return f"""
## Running on Claude Code

Lyra's playbooks are installed as Claude Code skills named
`{PLUGIN_NAME}:<name>`. Translate the playbooks' tool names:
- `skill_view(name="{PLUGIN_NAME}:X")` → load it with the **Skill** tool as
  `{PLUGIN_NAME}:X`, then follow it exactly. Never improvise a phase whose
  playbook you have not loaded.
- `delegate_task` → the Agent (Task) tool. Run agents in the foreground; to
  work in parallel, start several in one message. Tell each agent which
  `{PLUGIN_NAME}:` skill to load, its task, the files it owns and the test command.
- `clarify` → ask in your reply and end the turn.
- `terminal` → Bash; `read_file`/`write_file`/`patch`/`search_files` →
  Read/Write/Edit/Grep/Glob; `todo` → TodoWrite.

Requirements: before asking any requirements question, load
`{PLUGIN_NAME}:req-engineer` with the Skill tool and follow its conversation
contract — one question per message.

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
        """Environment for the Claude Code program, by route.

        subscription — the owner's own `claude` program and its sign-in (their
                       Claude plan), exactly as when they run Claude Code;
                       API keys are blanked so billing can't switch silently.
        ollama       — Ollama's Anthropic-compatible address on this computer.
        api          — an Anthropic API key (pay per use).
        custom       — another Anthropic-compatible address and token.
        """
        env = {"DISABLE_TELEMETRY": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
        route = claude_route(self.settings)
        if route == "subscription":
            if not find_claude_cli():
                raise RuntimeError(
                    "Claude Code isn't installed on this Mac. Install it from "
                    "https://claude.com/claude-code, sign in once with `claude`, then try again — "
                    "or pick Ollama or an API key in AI settings.")
            env.update({"ANTHROPIC_API_KEY": "", "ANTHROPIC_AUTH_TOKEN": "", "ANTHROPIC_BASE_URL": ""})
            return env
        # Every other route uses Lyra's own Claude config folder, so the owner's
        # personal Claude sign-in is never used by accident.
        from hermes_constants import get_hermes_home

        config_dir = get_hermes_home() / "lyra-lite" / "claude-config"
        config_dir.mkdir(parents=True, exist_ok=True)
        env["CLAUDE_CONFIG_DIR"] = str(config_dir)
        if route in {"ollama", "custom"}:
            base_url = str(self.settings.get("base_url") or "").strip() or (OLLAMA_URL if route == "ollama" else "")
            if not base_url:
                raise RuntimeError("Add the model address in AI settings.")
            env["ANTHROPIC_BASE_URL"] = base_url
            env["ANTHROPIC_AUTH_TOKEN"] = str(self.settings.get("auth_token") or "ollama")
            env["ANTHROPIC_API_KEY"] = ""
            return env
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "No Anthropic API key found (ANTHROPIC_API_KEY in ~/.hermes/.env). "
                "To use your Claude plan instead, choose 'Your Claude plan' in AI settings.")
        env["ANTHROPIC_API_KEY"] = key
        return env

    async def _connect(self):
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher

        state = self.store.state() if self.store is not None else {}
        resume = state.get("claude_session") if state.get("claude_chat") == state.get("chat_id") else None
        options = ClaudeAgentOptions(
            cwd=self.workspace,
            # On the owner's plan, no model means the Claude program's own default.
            model=str(self.settings.get("model") or "") or (
                None if claude_route(self.settings) == "subscription" else DEFAULT_MODEL),
            permission_mode="acceptEdits",
            system_prompt={"type": "preset", "preset": "claude_code",
                           "append": self.system_prompt + engine_notes()},
            include_partial_messages=True,
            setting_sources=[],
            plugins=[{"type": "local", "path": str(builder_plugin_dir())}],
            can_use_tool=self._can_use_tool,
            disallowed_tools=list(DISALLOWED),
            hooks={"PreToolUse": [HookMatcher(matcher="Agent|Task", hooks=[_foreground_agents])]},
            resume=resume or None,
            env=self._env(),
            cli_path=find_claude_cli() if claude_route(self.settings) == "subscription" else None,
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
                raw = msg.usage or {}
                usage = {
                    "api_calls": int(msg.num_turns or 0),
                    "input": int(raw.get("input_tokens") or 0),
                    "cache_read": int(raw.get("cache_read_input_tokens") or 0),
                    "cache_write": int(raw.get("cache_creation_input_tokens") or 0),
                    "output": int(raw.get("output_tokens") or 0),
                    "duration_ms": msg.duration_ms,
                }
                # On the owner's plan this figure is only what the API would have
                # charged, not a bill — don't show it as a cost.
                if msg.total_cost_usd is not None and claude_route(self.settings) != "subscription":
                    usage["cost_usd"] = msg.total_cost_usd
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
