"""Remember in-flight Hermes dispatches without changing its tools or prompts."""
from __future__ import annotations

import json
import threading


def _object(value) -> dict:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _tasks(args: dict) -> list[dict]:
    tasks = args.get("tasks")
    if isinstance(tasks, str):
        try:
            tasks = json.loads(tasks)
        except ValueError:
            return []
    tasks = tasks if isinstance(tasks, list) and tasks else [args]
    return [{
        "goal": task["goal"].strip(),
        "context": task.get("context") or None,
        "model": task.get("model") or args.get("model") or None,
        "role": task.get("role") or args.get("role") or "leaf",
    } for task in tasks if isinstance(task, dict) and isinstance(task.get("goal"), str) and task["goal"].strip()]


class DelegationGuard:
    """Reuse an identical running task; completed work may be dispatched again.

    Full goal/context/model/role equality keeps independent jobs independent.
    History restores dispatch identities if the engine is rebuilt mid-chat.
    """

    def __init__(self, session_key: str):
        self.session_key = session_key
        self._dispatched: dict[str, list[dict]] = {}
        self._lock = threading.Lock()

    def _running(self) -> list[dict]:
        from tools.async_delegation import list_async_delegations

        return [r for r in list_async_delegations()
                if r.get("session_key") == self.session_key and r.get("status") == "running"]

    def _remember(self, args: dict, result: dict) -> None:
        if result.get("status") == "dispatched" and result.get("delegation_id"):
            self._dispatched[result["delegation_id"]] = _tasks(args)

    def restore(self, history: list[dict]) -> None:
        calls = {}
        with self._lock:
            for message in history:
                for call in message.get("tool_calls") or []:
                    fn = call.get("function") or {}
                    if fn.get("name") == "delegate_task":
                        calls[call.get("id")] = _object(fn.get("arguments"))
                if message.get("role") == "tool" and message.get("tool_call_id") in calls:
                    self._remember(calls[message["tool_call_id"]], _object(message.get("content")))

    def reminder(self) -> str:
        running = self._running()
        if not running:
            return ""
        jobs = [{"id": r["delegation_id"], "goals": r.get("goals") or [r.get("goal", "")]}
                for r in running]
        return ("\n\n[Appling: these helpers are already running for this conversation]\n"
                + json.dumps(jobs, ensure_ascii=False)
                + "\nAn earlier coordinator error does not stop them. Do not restart or duplicate "
                  "their work. Their results will arrive automatically; you can answer the owner "
                  "or continue unrelated work.\n")

    def dispatch(self, args: dict, send) -> str:
        with self._lock:
            active = {r["delegation_id"] for r in self._running()}
            self._dispatched = {k: v for k, v in self._dispatched.items() if k in active}
            requested = _tasks(args)
            matches = [key for key, tasks in self._dispatched.items()
                       if any(task in tasks for task in requested)]
            if matches:
                # Do not partially launch a mixed batch: the model can send
                # its unrelated tasks separately without duplicating these.
                return json.dumps({
                    "status": "already_running", "delegation_ids": matches,
                    "note": "No new workers started. These identical tasks are already running. "
                            "Their results will arrive automatically. If this batch also contains "
                            "unrelated tasks, submit only those separately.",
                })
            result = send(args)
            self._remember(args, _object(result))
            return result
