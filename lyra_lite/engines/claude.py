"""Claude Code (via the Claude Agent SDK) as an Appling Lite engine.

The model is chosen separately from the engine: an Anthropic API key runs
Claude models; a custom Anthropic-compatible address (for example Ollama)
runs other models through the same engine. Appling never falls back to a
Claude subscription login — the CLI gets its own config folder.

Safety matches the Hermes engine: file edits inside the project are allowed,
shell commands that Hermes' danger check flags go to the owner's inbox.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
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


NO_EFFORT_MODELS = ("claude-3", "haiku-4", "sonnet-4-5", "sonnet-4-2025", "opus-4-2025", "opus-4-1")


def claude_effort(settings: dict) -> str | None:
    """The --effort to give the Claude program: the owner's choice, else Appling's default.

    Only Anthropic's own models take an effort level; an Ollama or custom
    address gets none, since those servers may reject the field.
    """
    from lyra_lite.settings import DEFAULT_EFFORT, EFFORTS

    if claude_route(settings) not in ("subscription", "api"):
        return None
    effort = str(settings.get("effort") or "")
    if effort in EFFORTS:
        return effort
    # Older models take no effort level; the default isn't forced on them.
    model = str(settings.get("model") or "").lower()
    if any(old in model for old in NO_EFFORT_MODELS):
        return None
    return DEFAULT_EFFORT


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
# The shared design skills the playbooks load by bare name
# (skill_view(name="design-taste-frontend"), "design-tokens", "a11y-audit" …).
DESIGN_SKILLS_ROOT = REPO_ROOT / "skills" / "ui-ux"
# Other repo skills the playbooks name for a project kind (slides → .pptx).
EXTRA_SKILLS = [REPO_ROOT / "skills" / "productivity" / "powerpoint" / "SKILL.md"]


def _skill_name(skill_md: Path) -> str:
    try:
        for line in skill_md.read_text(encoding="utf-8").splitlines()[:8]:
            if line.startswith("name:"):
                return line.split(":", 1)[1].strip().strip("'\"") or skill_md.parent.name
    except OSError:
        pass
    return skill_md.parent.name

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
RECALL_TOOL = "mcp__lyra__project_recall"
ALWAYS_OK = {"WebSearch", "WebFetch", "TodoWrite", "Read", "Glob", "Grep", "Skill", RECALL_TOOL}


def _skill_index() -> str:
    lines = []
    for path in sorted(SKILLS_ROOT.rglob("SKILL.md")):
        lines.append(f"- ultimate-builder:{path.parent.name} → {path}")
    return "\n".join(lines)


PLUGIN_NAME = "ultimate-builder"


def builder_plugin_dir() -> Path:
    """Appling's builder playbooks as a native Claude Code plugin.

    The playbooks are already SKILL.md files. Linked into a plugin called
    ``ultimate-builder`` they load with Claude Code's own Skill tool under the
    same names Hermes uses (``ultimate-builder:req-engineer`` …), instead of
    relying on the model choosing to read a file.
    """
    from hermes_constants import get_hermes_home

    root = get_hermes_home() / "lyra-lite" / "claude-plugin" / PLUGIN_NAME
    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    manifest = {"name": PLUGIN_NAME, "version": "1.0.0",
                "description": "Appling's application-builder playbooks."}
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest, indent=2) + "\n")
    skills = root / "skills"
    skills.mkdir(exist_ok=True)
    wanted = {path.parent.name: path.parent for path in SKILLS_ROOT.rglob("SKILL.md")}
    for path in [*sorted(DESIGN_SKILLS_ROOT.rglob("SKILL.md")), *EXTRA_SKILLS]:
        if path.is_file():
            wanted.setdefault(_skill_name(path), path.parent)
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

Appling's playbooks are installed as Claude Code skills named
`{PLUGIN_NAME}:<name>`. Translate the playbooks' tool names:
- `skill_view(name="{PLUGIN_NAME}:X")` → load it with the **Skill** tool as
  `{PLUGIN_NAME}:X`, then follow it exactly. Never improvise a phase whose
  playbook you have not loaded. A bare `skill_view(name="X")` (design skills
  such as `design-taste-frontend`, `design-tokens`, `a11y-audit`) is
  `{PLUGIN_NAME}:X` too.
- Any interface: load `{PLUGIN_NAME}:color-and-ux` before choosing colours,
  type or layout, and run its `palette.py check` on the final palette.
- `delegate_task` → the Agent (Task) tool. Agents always run in the
  background: start them (several in one message to work in parallel), tell
  the owner in a sentence or two what is now running, and end your turn.
  Each agent's report arrives later as its own message; react to it then.
  Never wait or poll for an agent. The owner can message you at any time
  while agents work — answer from the project files and what you know.
  Tell each agent which `{PLUGIN_NAME}:` skill to load, its task, the files
  it owns and the test command.
- `clarify` → ask in your reply and end the turn.
- `project_recall` → the `{RECALL_TOOL}` tool (search this project's memory).
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


REPORT_PREFIX = "<task-notification>"


class _Turn:
    """One Claude Code turn as it streams in — Appling's own (it has a future),
    or one the Claude program started itself to read a helper's report."""

    def __init__(self, hooks, prompt: str = "", future=None):
        self.hooks = hooks
        self.prompt = prompt
        self.future = future
        self.external: dict | None = None  # the runner's turn for a report turn
        self.merged = False   # a report turn while Appling's own turn is waiting
        self.ignored = False  # a report turn while the owner has Appling stopped
        self.carry = ""       # replies of report turns merged into this one
        self.streamed_any = False
        self.need_gap = False
        self.texts: list[str] = []
        self.tool_names: dict[str, str] = {}

    def emit(self, type_: str, **data) -> None:
        if not self.ignored and self.hooks is not None:
            self.hooks.emit(type_, **data)


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
            # On the owner's plan, no model means the Claude program's own default.
            model=str(self.settings.get("model") or "") or (
                None if claude_route(self.settings) == "subscription" else DEFAULT_MODEL),
            effort=claude_effort(self.settings),
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

    async def _agents_hook(self, hook_input, tool_use_id, context):
        call_id = hook_input.get("tool_use_id") or tool_use_id
        if not hook_input.get("agent_id") and call_id:
            self._backgrounded.add(call_id)
        return await _background_agents(hook_input, tool_use_id, context)

    def run_turn(self, text: str, history: list[dict], hooks: TurnHooks) -> TurnResult:
        self._hooks = hooks
        self._interrupted = False
        try:
            reply, usage, error, interrupted = self._call(self._ask(text, history, hooks))
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

    # -- the one reader ----------------------------------------------------

    async def _read(self, client) -> None:
        """Everything the Claude program sends, for as long as it runs: Appling's
        turns, turns it starts itself for helper reports, and helper activity
        between turns."""
        try:
            async for msg in client.receive_messages():
                try:
                    self._route(msg)
                except Exception:
                    logger.exception("lyra-lite: could not handle a Claude message")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("lyra-lite: the Claude program stopped", exc_info=True)
        finally:
            if self._client is client:
                self._client = None
            waiting = [t for t in [self._current, *self._pending] if t is not None]
            self._current, self._pending, self._starting = None, [], False
            self._agents.clear()  # its background helpers died with it
            self._task_ids.clear()
            for turn in waiting:
                if turn.external is not None:
                    end = getattr(self._hooks, "end_external_turn", None)
                    if end is not None:
                        end(turn.external, reply=turn.carry,
                            error="The Claude program stopped before finishing this report.")
                if turn.future is not None and not turn.future.done():
                    turn.future.set_result((turn.carry, {}, "The Claude program stopped; send the message again.",
                                            False))

    def _route(self, msg) -> None:
        from claude_agent_sdk import (
            AssistantMessage, ResultMessage, StreamEvent, SystemMessage, TaskNotificationMessage,
            TaskStartedMessage, UserMessage,
        )

        # Task messages are SystemMessages too: check them first.
        if isinstance(msg, TaskStartedMessage):
            key = msg.tool_use_id or msg.task_id
            self._task_ids[key] = msg.task_id
            if key not in self._agents:
                self._agents[key] = msg.description
                self._goals.setdefault(key, msg.description)
                self._emit_helper(event="start", subagent_id=key, goal=msg.description)
            return
        if isinstance(msg, TaskNotificationMessage):
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
            return
        if isinstance(msg, SystemMessage):
            if msg.subtype == "init":
                self._starting = True
            return
        if not isinstance(msg, (StreamEvent, AssistantMessage, UserMessage, ResultMessage)):
            # Rate-limit notices and the like come between turns too (a
            # helper's model call); they never start one, or nothing ends it.
            return
        parent = getattr(msg, "parent_tool_use_id", None)
        if parent:
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    name = getattr(block, "name", None)
                    if name:
                        self._emit_helper(event="tool", subagent_id=parent, tool=TOOL_NAMES.get(name, name))
            return
        if self._starting:
            # Appling's own messages are echoed first (replay-user-messages);
            # a turn without that echo is one Claude started for a report.
            echoed = isinstance(msg, UserMessage) and isinstance(msg.content, str)
            if self._current is not None:
                # A new turn began before the last one's result: close the
                # last one, or Appling stays busy with it for good.
                self._abandon(self._current)
            self._current = self._open_turn(msg.content if echoed else None)
            self._starting = False
            if echoed:
                return
        if self._current is None:
            self._current = self._open_turn(None)
        turn = self._current
        if isinstance(msg, StreamEvent):
            self._stream(turn, msg)
            return
        if isinstance(msg, AssistantMessage):
            self._assistant(turn, msg)
        elif isinstance(msg, UserMessage):
            self._tool_results(turn, msg)
        elif isinstance(msg, ResultMessage):
            self._current = None
            self._finish(turn, msg)

    def _emit_helper(self, **data) -> None:
        if self._hooks is not None:
            self._hooks.emit("helper", **data)

    def _open_turn(self, first: str | None) -> _Turn:
        """Which turn is starting: Appling's next waiting message, or a report
        turn the Claude program began on its own."""
        if first is not None and not first.lstrip().startswith(REPORT_PREFIX) and self._pending:
            return self._pending.pop(0)
        if first is None and self._pending and not self._reports:
            return self._pending.pop(0)  # no echo and no report waiting: still ours
        turn = _Turn(self._hooks)
        if first:
            goal, summary = self._report_parts(first)
        else:
            goal, summary = self._reports.pop(0) if self._reports else ("", "")
        begin = getattr(self._hooks, "begin_external_turn", None)
        # "[…" marks a report in the chat, like Hermes' helper reports.
        title = f"[A helper finished: {goal or 'background task'}]"
        started = begin("helper_done", f"{title}\n\n{summary}".strip(), title[:300]) if begin else None
        if started is False:
            turn.ignored = True  # the owner pressed Stop: don't act on reports
            client = self._client
            if client is not None:
                asyncio.get_running_loop().create_task(client.interrupt())
        elif started:
            turn.external = started
        else:
            turn.merged = True
        return turn

    def _report_parts(self, text: str) -> tuple[str, str]:
        """The helper's goal and summary from the CLI's <task-notification>."""
        def tag(name: str) -> str:
            m = re.search(rf"<{name}>(.*?)</{name}>", text, re.S)
            return m.group(1).strip() if m else ""

        call_id = tag("tool-use-id")
        summary = tag("summary") or tag("result")
        goal = self._goals.get(call_id, "") or summary
        return goal[:300], _preview(summary, 1200)

    def _stream(self, turn: _Turn, msg) -> None:
        event = msg.event or {}
        if event.get("type") == "message_start" and turn.streamed_any:
            turn.need_gap = True
        delta = event.get("delta") or {}
        if event.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
            piece = str(delta.get("text") or "")
            if piece:
                if turn.need_gap:
                    turn.emit("delta", text="\n\n")
                    turn.need_gap = False
                turn.emit("delta", text=piece)
                turn.streamed_any = True

    def _assistant(self, turn: _Turn, msg) -> None:
        from claude_agent_sdk import TextBlock, ToolUseBlock

        for block in msg.content:
            if isinstance(block, ToolUseBlock):
                turn.tool_names[block.id] = block.name
                if block.name in AGENT_TOOLS:
                    goal = str(block.input.get("description") or block.input.get("prompt") or "")[:300]
                    self._agents[block.id] = goal
                    self._goals[block.id] = goal
                    turn.emit("tool", phase="start", id=block.id, name="delegate_task", args=_preview(block.input))
                    self._emit_helper(event="start", subagent_id=block.id, goal=goal)
                else:
                    turn.emit("tool", phase="start", id=block.id, name=TOOL_NAMES.get(block.name, block.name),
                              args=_preview(block.input))
            elif isinstance(block, TextBlock):
                turn.texts.append(block.text)

    def _tool_results(self, turn: _Turn, msg) -> None:
        from claude_agent_sdk import ToolResultBlock

        if isinstance(msg.content, str):
            return  # a helper report folded into this turn; its helper event came already
        for block in msg.content:
            if not isinstance(block, ToolResultBlock):
                continue
            name = turn.tool_names.get(block.tool_use_id, "")
            if block.tool_use_id in self._agents and block.tool_use_id not in self._backgrounded:
                goal = self._agents.pop(block.tool_use_id)
                self._emit_helper(event="complete", subagent_id=block.tool_use_id, goal=goal,
                                  status="failed" if block.is_error else "completed",
                                  summary=_preview(_result_text(block.content), 1200))
            elif block.is_error and block.tool_use_id in self._agents:
                self._agents.pop(block.tool_use_id, None)  # never started
                self._emit_helper(event="complete", subagent_id=block.tool_use_id, goal="",
                                  status="failed", summary=_preview(_result_text(block.content), 1200))
            turn.emit("tool", phase="done", id=block.tool_use_id, name=TOOL_NAMES.get(name, name),
                      result=_preview(_result_text(block.content)))

    def _finish(self, turn: _Turn, msg) -> None:
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
        interrupted = self._interrupted and turn.future is not None
        error = None
        if msg.is_error and not interrupted and not turn.ignored:
            # The CLI's own words ("You've hit your session limit · resets …").
            error = str(msg.result or "").strip() or f"Claude engine: {msg.subtype}"
        if self.store is not None and msg.session_id:
            state = self.store.state()
            self.store.update_state(claude_session=msg.session_id, claude_chat=state.get("chat_id"))
        reply = (msg.result or (turn.texts[-1] if turn.texts else "")).strip()
        if reply and not turn.streamed_any and not msg.is_error:
            turn.emit("delta", text=reply)
        if turn.future is not None:
            if turn.carry:
                reply = f"{turn.carry}\n\n{reply}".strip()
            if not turn.future.done():
                turn.future.set_result((reply, usage, error, interrupted))
        elif turn.external is not None:
            end = getattr(self._hooks, "end_external_turn", None)
            if end is not None:
                end(turn.external, reply=reply, usage=usage, error=error)
        elif turn.merged and reply:
            if self._pending:
                self._pending[0].carry = f"{self._pending[0].carry}\n\n{reply}".strip()
            else:
                self._carry = f"{self._carry}\n\n{reply}".strip()

    def _abandon(self, turn: _Turn, error: str | None = None) -> None:
        """End a turn the Claude program will send no result for, with what
        it said so far."""
        reply = (turn.texts[-1] if turn.texts else "").strip()
        if turn.future is not None:
            if not turn.future.done():
                turn.future.set_result((f"{turn.carry}\n\n{reply}".strip(), {}, error, self._interrupted))
        elif turn.external is not None:
            end = getattr(self._hooks, "end_external_turn", None)
            if end is not None:
                end(turn.external, reply=f"{turn.carry}\n\n{reply}".strip(), error=error)
        elif turn.merged and reply:
            self._carry = f"{self._carry}\n\n{reply}".strip()

    STOP_GRACE = 15.0  # seconds the Claude program gets to answer a Stop

    def _stop_turn(self) -> None:
        """Stop pressed: a report turn has nobody waiting on it, so end it now
        rather than trust the Claude program to answer the interrupt. Appling's
        own turn gets a short grace to end properly, then is ended anyway."""
        turn = self._current
        if turn is None and self._pending:
            turn = self._pending[0]  # sent, but the Claude program never began it
        if turn is None:
            return
        if turn.future is None:
            self._current = None
            turn.ignored = True
            self._abandon(turn)
        else:
            asyncio.get_running_loop().call_later(self.STOP_GRACE, self._end_if_still_open, turn)

    def _end_if_still_open(self, turn: _Turn) -> None:
        if turn.future is None or turn.future.done():
            return
        if self._current is turn:
            self._current = None
        if turn in self._pending:
            self._pending.remove(turn)
        self._abandon(turn)

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
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._stop_turn)

    def stop_helpers(self) -> int:
        """Stop every helper, including ones running in the background."""
        running = len(self._agents)
        client, loop = self._client, self._loop
        if client is not None and loop is not None:
            for task_id in list(self._task_ids.values()):
                try:
                    asyncio.run_coroutine_threadsafe(client.stop_task(task_id), loop).result(10)
                except Exception:
                    logger.debug("could not stop helper %s", task_id, exc_info=True)
        if running:
            self.interrupt()
        return running

    def helpers(self) -> list[dict]:
        return [{"id": k, "goal": v, "started": None} for k, v in list(self._agents.items())]

    def close(self) -> None:
        client, self._client = self._client, None
        reader, self._reader = self._reader, None
        if reader is not None and self._loop is not None:
            self._loop.call_soon_threadsafe(reader.cancel)
        if client is not None and self._loop is not None:
            try:
                asyncio.run_coroutine_threadsafe(client.disconnect(), self._loop).result(15)
            except Exception:
                pass
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._loop = None
        self._hooks = None
