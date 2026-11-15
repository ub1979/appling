"""Native Codex execution with durable threads and Appling's owner controls."""
from __future__ import annotations

import hashlib
import json
import os
import queue
import threading
from pathlib import Path

from lyra_lite.engines.base import TurnResult
from lyra_lite.engines.codex_rpc import CodexRPC
from lyra_lite.engines.review_requests import ReviewRequests
from lyra_lite.store import _atomic_write_json, _read_json


def _tool(name, description, properties, required=()):
    return {"type": "function", "name": name, "description": description,
            "inputSchema": {"type": "object", "properties": properties, "required": list(required),
                            "additionalProperties": False}}


TOOLS = [
    _tool("clarify", "Ask the owner one question or open the exact prototype, requirements or plan approval checkpoint.",
          {"question": {"type": "string"}, "choices": {"type": "array", "items": {"type": "string"}}}, ("question",)),
    _tool("skill_view", "Read the project's concise instructions for an agent role.",
          {"name": {"type": "string"}}, ("name",)),
    _tool("project_recall", "Search only this project's earlier owner decisions and reports.",
          {"query": {"type": "string"}}, ("query",)),
    _tool("delegate_task", "Assign a selected role. Development leads may launch up to three isolated coding leaves with disjoint owned_paths.",
          {"goal": {"type": "string"}, "context": {"type": "string"}, "agent": {"type": "string"},
           "tasks": {"type": "array", "items": {"type": "object", "properties": {
               "goal": {"type": "string"}, "context": {"type": "string"}, "agent": {"type": "string"}},
               "required": ["goal"], "additionalProperties": False}}}),
]


def role_instructions(role: str) -> str:
    text = (Path(__file__).resolve().parents[1] / "rules/codex-roles.md").read_text()
    sections = text.split("\n## ")
    selected = next((s for s in sections[1:] if s.splitlines()[0] == role), None)
    return sections[0] + "\n\n" + (selected or next(s for s in sections[1:] if s.startswith("other\n")))


def usage_delta(total: dict, before: dict) -> dict:
    def difference(key):
        return max(0, int(total.get(key) or 0) - int(before.get(key) or 0))
    cached = difference("cachedInputTokens")
    written = difference("cacheWriteInputTokens")
    return {"input": max(0, difference("inputTokens") - cached - written), "cache_read": cached,
            "cache_write": written, "output": difference("outputTokens"),
            "reasoning": difference("reasoningOutputTokens")}


class CodexEngine(ReviewRequests):
    name = "codex"

    def __init__(self, *, workspace, session_key, system_prompt="", skills=None, store=None,
                 role="coordinator", parent=None, command=None):
        self.workspace = str(Path(workspace).resolve())
        self.session_key = session_key
        self.system_prompt = system_prompt
        self.store = store
        self.role = role
        self.parent = parent
        self.command = command
        self._rpc = None
        self._hooks = None
        self._turn = None
        self._stopped = threading.Event()
        self._children = {}
        self._children_lock = threading.RLock()
        self._request_lock = threading.RLock()
        self._request_id = None
        self._resolved_requests = set()
        self._waiting_inboxes = {}
        self._state_file = (store.dir if store else Path(workspace) / ".lyra") / "codex" / (
            hashlib.sha256(session_key.encode()).hexdigest()[:24] + ".json")
        self._session = _read_json(self._state_file, {})
        from lyra_lite.settings import resolve_agent_model, agent_model_overrides
        self.selection = resolve_agent_model(role, agent_model_overrides(), {})
        from lyra_lite.engines.browser_tools import BrowserTools
        self._browser = BrowserTools(self)

    @property
    def _interrupt_requested(self):
        return self._stopped.is_set()

    def _save(self, **fields):
        self._session.update(fields)
        _atomic_write_json(self._state_file, self._session)

    def _connect(self):
        if self._rpc is not None:
            return False
        with self._request_lock:
            self._resolved_requests.clear()
            self._waiting_inboxes.clear()
        self._rpc = CodexRPC(cwd=self.workspace, command=self.command, on_notification=self._control_notification, env={**os.environ, **self._browser.env})
        from lyra_lite.settings import _section
        cfg = _section()
        if cfg.get("require_api_key"):
            account = self._rpc.request("account/read", {}).get("account") or {}
            if account.get("type") != "apiKey":
                raise RuntimeError("This Appling deployment requires Codex API-key authentication. Run codex login --with-api-key.")
        tools = TOOLS if self.role in {"coordinator", "sw-developer"} else TOOLS[:3]
        # Disable unmanaged subagents. All leaves must use our worktree/Stop guards.
        config = {"features.multi_agent": False, "features.collab": False,
                  "model_reasoning_effort": self.selection["effort"]}
        prompt = self.system_prompt + self._browser.instructions
        if self.role != "coordinator":
            prompt += "\n\n" + role_instructions(self.role)
        fingerprint = hashlib.sha256(json.dumps([prompt, tools, config, self.selection], sort_keys=True).encode()).hexdigest()
        previous = self._session.get("thread_id")
        if previous and self._session.get("fingerprint") == fingerprint:
            result = self._rpc.request("thread/resume", {"threadId": previous, "excludeTurns": True})
            self._save(thread_id=result["thread"]["id"])
            # A previous client died mid-turn. Interrupt instead of replaying it.
            if self._session.get("turn_id"):
                try:
                    self._rpc.request("turn/interrupt", {"threadId": previous, "turnId": self._session["turn_id"]})
                except RuntimeError:
                    pass  # A completed turn is already durable in Codex.
                self._save(turn_id=None)
            return False
        result = self._rpc.request("thread/start", {
            "cwd": self.workspace, "model": self.selection["model"],
            "developerInstructions": prompt, "approvalPolicy": "on-request", "approvalsReviewer": "user",
            "sandbox": "workspace-write", "config": config, "dynamicTools": tools,
        })
        self._save(thread_id=result["thread"]["id"], previous_thread_id=previous, turn_id=None, fingerprint=fingerprint, usage={})
        return True

    def run_turn(self, text, history, hooks):
        self._hooks = hooks
        if self.parent is not None and self.parent._stopped.is_set():
            return TurnResult("", list(history), completed=False, interrupted=True)
        self._stopped.clear()
        messages = list(history) + [{"role": "user", "content": text}]
        final = ""
        before = dict(self._session.get("usage") or {})
        try:
            fresh = self._connect()
            before = dict(self._session.get("usage") or {})
            if fresh and history:
                # Only a new/migrated thread needs a continuity brief. Existing
                # Codex threads retain their native tools, compaction and history.
                brief = [{"role": m["role"], "content": m.get("content", "")} for m in history
                         if m.get("role") in {"user", "assistant"} and m.get("content")][-12:]
                text = "Previous conversation for continuity; project files are authoritative:\n" + json.dumps(brief, ensure_ascii=False)[-32000:] + "\n\nCurrent message:\n" + text
            if self._stopped.is_set():
                return TurnResult("", messages, completed=False, interrupted=True)
            result = self._rpc.request("turn/start", {"threadId": self._session["thread_id"],
                "input": [{"type": "text", "text": text}], "effort": self.selection["effort"]})
            self._turn = result["turn"]["id"]
            self._save(turn_id=self._turn)
            if self._stopped.is_set():
                self.interrupt()
            while True:
                try:
                    event = self._rpc.events.get(timeout=1)
                except queue.Empty:
                    if self._stopped.is_set():
                        raise RuntimeError("Codex was stopped before acknowledging turn completion.")
                    continue
                if "error" in event and "method" not in event:
                    raise RuntimeError(event["error"]["message"])
                method, params = event.get("method", ""), event.get("params") or {}
                if params.get("threadId") not in (None, self._session["thread_id"]):
                    if "id" in event:
                        self._rpc.reject(event["id"])
                    continue
                if params.get("turnId") not in (None, self._turn):
                    if "id" in event:
                        self._rpc.reject(event["id"])
                    continue
                if "id" in event:
                    self._request_id = event["id"]
                    try:
                        self._request(event)
                    finally:
                        self._request_id = None
                elif method == "item/agentMessage/delta":
                    hooks.emit("delta", text=str(params.get("delta") or ""))
                elif method in {"item/started", "item/completed"}:
                    item = params.get("item") or {}
                    if item.get("type") == "agentMessage" and method == "item/completed":
                        if item.get("phase") == "commentary":
                            hooks.emit("interim", text=item.get("text", ""), already_streamed=True)
                        else:
                            final = str(item.get("text") or "")
                    elif item.get("type") in {"commandExecution", "fileChange", "dynamicToolCall", "mcpToolCall", "webSearch"}:
                        if "browser.cjs" in str(item.get("command") or ""):
                            self._browser.used = True
                        name = {"commandExecution": "terminal", "fileChange": "patch"}.get(item["type"], item.get("tool") or item["type"])
                        hooks.emit("tool", phase="start" if method == "item/started" else "done",
                                   id=item.get("id", ""), name=name,
                                   args=str(item.get("command") or item.get("arguments") or "")[:300],
                                   result=str(item.get("aggregatedOutput") or item.get("status") or "")[:300])
                elif method == "thread/tokenUsage/updated":
                    self._save(usage=(params.get("tokenUsage") or {}).get("total") or {})
                elif method == "turn/completed" and (params.get("turn") or {}).get("id") == self._turn:
                    turn = params["turn"]
                    status = turn.get("status")
                    error = (turn.get("error") or {}).get("message") if isinstance(turn.get("error"), dict) else None
                    self._save(turn_id=None)
                    if final:
                        messages.append({"role": "assistant", "content": final})
                    return TurnResult(final, messages, completed=status == "completed", interrupted=status == "interrupted",
                                      error=error or ("Codex turn failed" if status == "failed" else None),
                                      usage=usage_delta(self._session.get("usage", {}), before))
                elif method == "error":
                    hooks.emit("status", kind="codex_error", text=str((params.get("error") or {}).get("message") or "Codex reported an error"))
        except Exception as exc:
            if self._rpc:
                self._rpc.close()
                self._rpc = None
            return TurnResult(final, messages, completed=False, interrupted=self._stopped.is_set(),
                              error=None if self._stopped.is_set() else f"{type(exc).__name__}: {exc}",
                              usage=usage_delta(self._session.get("usage", {}), before))
        finally:
            self._turn = None

    def _request(self, event):
        method, params = event["method"], event.get("params") or {}
        request_id = event["id"]
        if method == "item/tool/call":
            try:
                value = self._call_tool(params["tool"], params.get("arguments") or {})
                result = {"contentItems": [{"type": "inputText", "text": str(value)}], "success": True}
            except Exception as exc:
                result = {"contentItems": [{"type": "inputText", "text": f"{type(exc).__name__}: {exc}"}], "success": False}
            self._respond(request_id, result)
        elif method in {"item/commandExecution/requestApproval", "item/fileChange/requestApproval", "item/permissions/requestApproval"}:
            choices = ["once", "deny"]
            if "acceptForSession" in params.get("availableDecisions", ["acceptForSession"]):
                choices.insert(1, "session")
            answer = self._ask_blocking("approval", timeout=None, on_timeout="deny",
                command=str(params.get("command") or params.get("grantRoot") or "Codex permission request"),
                description=str(params.get("reason") or "") + ("\n" + json.dumps(params["permissions"]) if params.get("permissions") else ""),
                choices=choices)
            accepted = answer in choices and answer in {"once", "session"} and not self._stopped.is_set()
            result = ({"permissions": params.get("permissions", {}) if accepted else {}, "scope": "session" if accepted and answer == "session" else "turn"}
                      if method == "item/permissions/requestApproval" else {"decision": ("acceptForSession" if answer == "session" else "accept") if accepted else "decline"})
            self._respond(request_id, result)
        elif method in {"item/tool/requestUserInput", "tool/requestUserInput"}:
            answers = {}
            for q in params.get("questions", []):
                if self._stopped.is_set():
                    answers[q["id"]] = {"answers": []}
                else:
                    answer = (self._ask_blocking("secret", timeout=None, on_timeout="", question=q["question"], env_var=q["id"])
                              if q.get("isSecret") else self._on_clarify(q["question"], [o["label"] for o in q.get("options") or []]))
                    answers[q["id"]] = {"answers": [answer] if answer else []}
            self._respond(request_id, {"answers": answers})
        else:
            self._rpc.reject(request_id)

    def _respond(self, request_id, result):
        with self._request_lock:
            if request_id in self._resolved_requests:
                return
        self._rpc.respond(request_id, result)

    def _control_notification(self, event):
        """Release owner waits even while the turn thread handles a host tool."""
        params = event.get("params") or {}
        if params.get("threadId") != self._session.get("thread_id"):
            return
        with self._request_lock:
            if event.get("method") == "serverRequest/resolved":
                ids = [params.get("requestId")]
            elif (event.get("method") == "turn/completed"
                  and (params.get("turn") or {}).get("id") == self._turn):
                ids = list(self._waiting_inboxes)
            else:
                return
            self._resolved_requests.update(ids)
        for request_id in ids:
            self._expire_request(request_id)

    def _expire_request(self, request_id):
        with self._request_lock:
            item_id = self._waiting_inboxes.pop(request_id, None)
        if item_id is not None and self._hooks:
            self._hooks.expire(item_id)

    def _call_tool(self, name, args):
        if self._stopped.is_set():
            raise RuntimeError("Work stopped by the owner")
        if name == "clarify":
            return self._on_clarify(str(args.get("question") or ""), args.get("choices") or [])
        if name == "skill_view":
            role = str(args.get("name") or "").split(":")[-1]
            if role == "req-engineer" and self.store is not None:
                self.store.update_state(requirements_review=True, requirements_started=True)
            return role_instructions(role)
        if name == "project_recall":
            from lyra_lite.memory import ProjectMemory, format_results
            query = str(args.get("query") or "").strip()
            if not query:
                raise ValueError("Give a few words to search for")
            return format_results(query, ProjectMemory(self.store.root).search(query, limit=6))
        if name == "delegate_task" and self.role in {"coordinator", "sw-developer"}:
            from lyra_lite.engines.codex_jobs import dispatch
            return dispatch(self, args)
        raise ValueError("Unknown or unavailable host tool")

    def interrupt(self):
        self._stopped.set()
        self.stop_helpers()
        self._browser.close(self.workspace)
        if self._rpc and self._turn:
            try:
                self._rpc.request("turn/interrupt", {"threadId": self._session["thread_id"], "turnId": self._turn}, timeout=5)
            except RuntimeError:
                self._rpc.close()
                self._rpc = None

    def stop_helpers(self):
        with self._children_lock:
            children = list(self._children.values())
        for child in children:
            child.interrupt()
        return len(children)

    def helpers(self):
        with self._children_lock:
            children = list(self._children.items())
        return [{"id": key, "goal": child.goal, "started": child.started} for key, child in children]

    def close(self):
        self.interrupt()
        self._browser.close(self.workspace)
        with self._children_lock:
            children = list(self._children.values())
        for child in children:
            child.close()
        if self._rpc:
            self._rpc.close()
            self._rpc = None
