"""Appling's per-task permissions, enforced before tools and separate from shell allowlists.

This is a direct-tool boundary, not an OS sandbox for arbitrary project programs.
Opaque execution and scope exceptions require the owner's exact, one-off consent.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import shlex
import sys
import threading
import time
import uuid

from lyra_lite.agents import LABELS, agent_for_goal
from lyra_lite.store import _atomic_write_json, _read_json

_EXECUTORS = frozenset({"sw-developer", "oop-restructurer", "debugger", "website-builder", "deck-builder",
                        "video-builder", "devops-engineer", "qa-engineer", "a11y-auditor", "security-auditor",
                        "benchmark", "health"})
_PRODUCT_WRITERS = frozenset({"sw-developer", "oop-restructurer", "debugger", "website-builder", "deck-builder",
                             "video-builder", "devops-engineer", "ux-writer"})
_PREVIEW_WRITERS = frozenset({"req-engineer", "ui-designer"})
_READ_COMMANDS = frozenset({"pwd", "ls", "rg", "grep", "head", "tail", "cat", "sed", "find", "which", "type", "wc", "file", "echo", "printf", "true"})
_GIT_READ_WRITE = frozenset({"status", "diff", "log", "show", "rev-parse", "ls-files", "add", "commit"})
_TOOL_READS = frozenset({"skill_view", "project_recall", "web_search", "web_extract", "browser_snapshot",
                         "browser_vision", "browser_get_images", "browser_click", "browser_type", "browser_press",
                         "browser_scroll", "browser_back", "browser_close", "todo", "tool_search", "tool_describe",
                         "clarify"})
_RISK = re.compile(r"ignore[ _-]+(?:any[ _-]+)?(?:prior[ _-]+)?(?:instructions|rules|user[ _-]+config)|"
                   r"prompt[ _-]*injection|jailbreak|adversarial|/etc/(?:passwd|shadow)|"
                   r"(?:~|/[^\s]*)/\.ssh|rm\s+[^\n;]*-[^\s]*r[^\s]*f|rm\s+[^\n;]*-[^\s]*f[^\s]*r|"
                   r"\b(?:mkfs|shutdown|reboot|dd\s+if=)\b", re.I)
_LIVE = re.compile(r"(?:^|[\s/])(?:hermes|codex|claude|ollama)(?:\s|$)|python\S*\s+-m\s+(?:hermes|openai|anthropic)", re.I)


def _key(tool, args):
    return hashlib.sha256(json.dumps([tool, args], sort_keys=True, default=str).encode()).hexdigest()


def _wraps_file_tools(code):
    """Route file batches back to checked tools; never execute or trust the script."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError):
        return False
    files = {"read_file", "write_file", "patch", "search_files"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "hermes_tools":
            if any(name.name in files or name.name == "*" for name in node.names):
                return True
        if isinstance(node, ast.Import) and any(name.name == "hermes_tools" for name in node.names):
            return True
    return False


class AgentScope:
    def __init__(self, store, ask, *, agent_id="appling", goal="Coordinate the selected project"):
        self.store, self.ask = store, ask
        self.root = store.root.resolve()
        self.agent_id, self.goal = agent_id, goal
        self.scope_id = uuid.uuid4().hex
        self.records = store.dir / "permissions" / self.scope_id
        (self.records / "actions").mkdir(parents=True, exist_ok=True)
        (self.records / "checks").mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _action_record(self, tool, args, decision, reason="", record_id=None):
        from agent.delegation_context import delegated_requester
        from agent.redact import redact_sensitive_text

        record_id = record_id or uuid.uuid4().hex
        path = self.records / "actions" / f"{record_id}.json"
        with self._lock:
            record = _read_json(path, {})
            record.update(schema=1, id=record_id, scope=self.scope_id,
                          chat_id=self.store.state().get("chat_id"), agent=self.agent_id,
                          task=redact_sensitive_text(self.goal[:1000], force=True),
                          requester={key: str((delegated_requester() or {}).get(key) or ("appling" if key == "subagent_id" else ""))
                                     for key in ("subagent_id", "model")},
                          tool=tool, args_hash=_key(tool, args), decision=decision,
                          reason=redact_sensitive_text(reason, force=True), updated=round(time.time(), 3))
            record.setdefault("created", record["updated"])
            record["remaining"] = 1 if decision == "approved_once" else 0
            if tool in {"terminal", "execute_code"}:
                record["execution_hash"] = _key(tool, {"command" if tool == "terminal" else "code": args.get("command" if tool == "terminal" else "code")})
            _atomic_write_json(path, record)
        self.store.append_event("scope_action", permission=record_id, agent=self.agent_id, tool=tool, decision=decision)
        return record_id

    def _check_path(self, tool, tool_call_id):
        return self.records / "checks" / f"{_key(tool, tool_call_id)}.json"

    def for_task(self, goal):
        return AgentScope(self.store, self.ask, agent_id=agent_for_goal(str(goal)) or "unknown", goal=str(goal))

    def check_runtime(self, api_mode):
        if api_mode == "codex_app_server":
            raise RuntimeError("This native Codex runtime executes tools outside Appling's scope checks. "
                               "Choose the Codex Responses model connection in Settings for constrained agent work. No task was started.")

    def dispatch_task(self, agent, args):
        from lyra_lite.delegation import dispatch_project_tasks
        return dispatch_project_tasks(self.store, agent, args)

    def _path(self, value, task_id):
        from tools.file_tools import _resolve_path_for_task
        return Path(str(_resolve_path_for_task(str(value), task_id or "default"))).expanduser().resolve()

    def _inside(self, path):
        return path == self.root or self.root in path.parents

    def _readable(self, path):
        roots = (self.root, Path(__file__).resolve().parents[1], Path(sys.prefix).resolve())
        sensitive = any(part in {".ssh", "id_rsa", "id_ed25519", "credentials.json", "auth.json"}
                        or (part.startswith(".env") and part not in {".env.example", ".env.sample"})
                        for part in path.parts)
        return not sensitive and any(path == root or root in path.parents for root in roots)

    def _writable(self, path):
        if not self._inside(path):
            return False
        relative = path.relative_to(self.root)
        parts = relative.parts
        if not parts:
            return False
        if self.agent_id in _PRODUCT_WRITERS:
            return True
        if parts[0] in {"docs", ".sdlc"} or path.suffix.lower() in {".md", ".rst", ".txt"}:
            return True
        if self.agent_id in _PREVIEW_WRITERS and parts[0] in {"prototypes", "assets"}:
            return True
        return self.agent_id in _EXECUTORS and (
            parts[0] in {"tests", "test", "e2e", "__tests__"} or re.search(r"\.(?:test|spec)\.", path.name))

    def _command_reason(self, command, args, task_id):
        if _RISK.search(command):
            return "This is a destructive, adversarial, or host-file diagnostic action. It needs separate permission."
        if re.search(r"\$(?:[A-Za-z_0-9{(]|[?!*@#-])|`|<<|(?:^|\s)(?:bash|sh|zsh|eval|exec)\s", command):
            return "This command contains opaque shell execution or expansion that cannot be checked against the assigned scope."
        try:
            tokens = list(shlex.shlex(command, posix=True, punctuation_chars=";&|<>"))
        except ValueError:
            return "The command cannot be safely parsed for a scope check."
        if not tokens:
            return None
        chunks, current = [], []
        for token in tokens:
            if token in {";", "&&", "||", "|"}:
                if current: chunks.append(current)
                current = []
            elif token in {">", ">>", "<", "&", "&>"}:
                return "Shell redirection or background execution needs explicit scope permission."
            else:
                current.append(token)
        if current: chunks.append(current)
        for chunk in chunks:
            if any((token in {"..", ".env", "auth.json", "credentials.json"}
                    or token.startswith(("/", "~/", "../", "./")) or "/" in token)
                   and not token.startswith("-") and not self._readable(self._path(token, task_id))
                   for token in chunk):
                return "This command references a path outside the project and installed runtime sources."
            program = Path(chunk[0]).name
            words = chunk[1:]
            if program == "cd":
                if len(words) != 1 or not self._inside(self._path(words[0], task_id)):
                    return "Changing the working directory outside the assigned project needs permission."
                continue
            if words and words[-1] == "--help" and all(re.fullmatch(r"[A-Za-z][\w-]*", word) for word in words[:-1]):
                if program in {"hermes", "codex", "claude", "ollama", "git", "npm", "python", "python3", "pytest"}:
                    continue
            if _LIVE.search(" ".join(chunk)):
                return "Starting a separate AI/provider session or probe needs separate owner permission."
            if program in _READ_COMMANDS:
                if (program == "sed" and any(w.startswith("-i") for w in words)) or (program == "find" and any(w in {"-exec", "-execdir", "-delete"} for w in words)):
                    return "This inspection command can modify files or execute another program."
                continue
            if program == "git":
                if "-C" in words:
                    index = words.index("-C")
                    if index + 1 >= len(words) or not self._inside(self._path(words[index + 1], task_id)):
                        return "Git operations outside this project need permission."
                    words = words[:index] + words[index + 2:]
                subcommand = next((w for w in words if not w.startswith("-")), "")
                if subcommand in _GIT_READ_WRITE and not any(
                    w.startswith(("--exec", "--config-env", "--git-dir", "--work-tree", "-c"))
                    or w in {"--no-verify", "--amend", "--ext-diff", "--textconv"} for w in words
                ):
                    continue
            if program in {"mkdir", "touch"}:
                paths = [word for word in words if not word.startswith("-")]
                if paths and all(self._writable(self._path(word, task_id)) for word in paths):
                    continue
            if self.agent_id in _EXECUTORS:
                if program in {"pytest", "ruff", "mypy", "tsc"}:
                    continue
                if program in {"python", "python3"} and len(words) >= 2 and words[0] == "-m" and words[1] in {"pytest", "compileall", "unittest"}:
                    continue
                if program in {"npm", "pnpm", "yarn", "bun"} and words:
                    if words[0] in {"install", "ci"} and not any(w in {"-g", "--global", "--prefix", "--cwd"} for w in words):
                        continue
                    script = words[1] if words[0] == "run" and len(words) > 1 else words[0]
                    if re.fullmatch(r"(?:test|build|lint|typecheck|check|fmt|format)(?::[\w-]+)?", script) and not any(w in {"--eval", "-e", "exec", "dlx"} for w in words):
                        # Catch direct probe commands hidden in a package script.
                        manifest = self.root / "package.json"
                        try:
                            script_text = json.loads(manifest.read_text()).get("scripts", {}).get(script, "")
                        except (OSError, ValueError):
                            script_text = ""
                        if _RISK.search(script_text) or _LIVE.search(script_text):
                            return "The project script starts an AI session or a diagnostic probe."
                        continue
                if program == "run_tests.sh" and self._inside(self._path(chunk[0], task_id)):
                    continue
            return f"Running {program} is outside {LABELS.get(self.agent_id, 'this agent')}'s normal inspected commands."
        return None

    def reason(self, tool, args, task_id=""):
        if tool in {"read_file", "search_files", "write_file", "patch"}:
            paths = [args.get("path") or "."]
            if tool == "patch" and args.get("mode") == "patch":
                paths = []
                for line in str(args.get("patch") or "").splitlines():
                    match = re.match(r"\*\*\*\s*(?:Add|Update|Delete)\s+File:\s*(.+)", line)
                    if match: paths.append(match[1])
                    move = re.match(r"\*\*\*\s*Move\s+File:\s*(.+?)\s*->\s*(.+)", line)
                    if move: paths.extend(move.groups())
                if not paths:
                    return "!The patch paths cannot be checked. Use explicit V4A file headers before any file is changed."
            for value in paths:
                path = self._path(value, task_id)
                if tool in {"write_file", "patch"}:
                    if self._inside(path) and path.relative_to(self.root).parts[:1] in {(".lyra",), (".git",)}:
                        return "!Agents cannot edit Appling's own approvals, permissions, or Git internals. Use the application controls."
                    if not self._readable(path):
                        return "Writing a host or credential file needs permission."
                    if not self._writable(path):
                        return "This file change is outside the agent's role or selected workspace."
                elif not self._readable(path):
                    return "Reading this host or credential file is outside the selected project and assigned inspection."
            return None
        if tool == "terminal":
            if args.get("workdir") and not self._inside(self._path(args["workdir"], task_id)):
                return "Running a command outside the selected project needs permission."
            return self._command_reason(str(args.get("command") or ""), args, task_id)
        if tool == "execute_code":
            if _wraps_file_tools(str(args.get("code") or "")):
                return ("!Retry these file operations now using read_file, search_files, write_file or patch directly. "
                        "Do not wrap file tools in execute_code or ask the owner to approve routine file edits. "
                        "Each direct operation will use the normal role and workspace checks. "
                        "No script was executed and no owner decision is needed for this retry.")
            return "Arbitrary script execution can start processes or access host files; review this exact script first."
        if tool == "browser_console":
            code = str(args.get("code") or args.get("expression") or args.get("script") or "")
            if code:
                return "Browser script execution needs permission. Use browser snapshots for ordinary inspection."
            return None
        if tool == "browser_navigate":
            url = str(args.get("url") or "")
            return None if url.startswith(("https://", "http://")) else "Local-file or executable browser navigation needs permission."
        if tool == "delegate_task":
            return None  # Each child inherits an independent role guard.
        if tool in _TOOL_READS:
            return None
        return "This tool is outside the agent's default project work and needs explicit permission."

    def __call__(self, tool, args, *, task_id="", tool_call_id="", **metadata):
        if tool == "tool_call":
            from tools.tool_search import resolve_underlying_call
            tool, args, error = resolve_underlying_call(args)
            if error or not tool:
                return "BLOCKED: the underlying tool call could not be checked."
        result = self._check(tool, args, task_id=task_id)
        with self._lock:
            _atomic_write_json(self._check_path(tool, tool_call_id), {
                "schema": 1, "tool": tool, "tool_call_id": tool_call_id,
                "args_hash": _key(tool, args), "validated": result is None,
                "consumed": False, "updated": round(time.time(), 3),
            })
        return result

    def final_check(self, tool, args, *, task_id="", tool_call_id=""):
        with self._lock:
            path = self._check_path(tool, tool_call_id)
            checked = _read_json(path, {})
            if checked.get("validated") and not checked.get("consumed") and checked.get("args_hash") == _key(tool, args):
                checked.update(consumed=True, updated=round(time.time(), 3))
                _atomic_write_json(path, checked)
                return None
        # Execution middleware or a direct nested call supplied different
        # arguments: check the final arguments even when plugin hooks skip.
        return self._check(tool, args, task_id=task_id)

    def _check(self, tool, args, *, task_id=""):
        reason = self.reason(tool, args, task_id)
        if reason is None:
            self._action_record(tool, args, "within_scope")
            return None
        if reason.startswith("!"):
            self._action_record(tool, args, "blocked_by_policy", reason[1:])
            return "BLOCKED: " + reason[1:]
        record_id = self._action_record(tool, args, "pending", reason)
        action = str(args.get("command") or args.get("code") or json.dumps(args, ensure_ascii=False, indent=2))
        try:
            allowed = self.ask(label=LABELS.get(self.agent_id, "Appling" if self.agent_id == "appling" else "Agent"),
                               goal=self.goal, tool=tool, action=action, reason=reason, permission_id=record_id)
        except Exception:
            self._action_record(tool, args, "permission_unavailable", reason, record_id)
            raise
        if not allowed:
            self._action_record(tool, args, "not_permitted", reason, record_id)
            return "BLOCKED: the owner did not permit this exact action. Stay within the assigned work; do not retry or disguise it."
        self._action_record(tool, args, "approved_once", reason, record_id)
        return None

    def consume_consent(self, tool, content):
        key = _key(tool, {"command" if tool == "terminal" else "code": content})
        with self._lock:
            for path in sorted((self.records / "actions").glob("*.json")):
                record = _read_json(path, {})
                if record.get("decision") == "approved_once" and record.get("remaining") == 1 and record.get("execution_hash") == key:
                    record.update(remaining=0, decision="consumed", consumed_at=round(time.time(), 3))
                    _atomic_write_json(path, record)
                    self.store.append_event("scope_action", permission=record["id"], agent=self.agent_id, tool=tool, decision="consumed")
                    return True
            return False
