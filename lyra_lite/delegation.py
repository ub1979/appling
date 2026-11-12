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


def dispatch_project_tasks(store, agent, args: dict) -> str:
    """Enforce Appling's review sequence and resolve trusted per-agent settings."""
    from lyra_lite import review, settings
    from lyra_lite.agents import agent_for_goal
    from tools.delegate_tool import (
        _recover_tasks_from_json_string, _strip_model_hidden_task_fields, delegate_task,
    )

    tasks = args.get("tasks")
    recovered, error = _recover_tasks_from_json_string(tasks)
    if error:
        return json.dumps({"error": error})
    tasks = recovered if recovered is not None else tasks
    tasks = _strip_model_hidden_task_fields(tasks)
    single = not tasks
    batch = [{k: args[k] for k in ("goal", "context", "role", "model") if k in args}] if single else tasks
    if not isinstance(batch, list) or any(not isinstance(task, dict) for task in batch):
        return json.dumps({"error": "Provide a list of agent tasks."})
    state = store.state()
    root = store.root
    update = review.active_update(root, state)
    identities = [agent_for_goal(str(task.get("goal") or "")) for task in batch]
    if "task-planner" in identities:
        batch = [{**task, "context": (str(task.get("context") or "") +
            "\nPlanning inspection: use source, documentation and CLI help to verify interfaces. "
            "Do not start live provider/agent sessions, adversarial prompt probes, destructive tests, or "
            "reads of unrelated host files as part of planning. These require a separately authorized "
            "diagnostic task. A command approval prompt is not a substitute for that authorization. "
            "Record unverified runtime behavior as a planned implementation/QA check or an explicit blocker.")}
            if agent_id == "task-planner" else task for task, agent_id in zip(batch, identities)]
        single = False  # Preserve the planning context for single-task dispatch too.
    requirements = review.requirements_revision(root)
    needs_prototype = review.visual_project(root, state)
    prototype = review.prototype_revision(root) if needs_prototype else None
    approval_required = bool(update or state.get("requirements_review") or state.get("requirements_approved"))
    approved = (
        not state.get("requirements_review")
        and requirements
        and requirements == state.get("requirements_approved")
        and (not needs_prototype or (prototype and prototype == state.get("prototype_approved")))
    )
    report = review.change_report(root, update, requirements) if update and requirements else None
    ready = report is not None and review.change_review_ready(report)
    for agent_id in identities:
        # Design prepares the clickable prototype that the owner must review.
        # Requiring that review before design can start creates a circular gate.
        if agent_id in {"req-engineer", "researcher", "ui-designer"}:
            continue
        if approval_required and not approved:
            if requirements and state.get("requirements_approved") and requirements != state["requirements_approved"]:
                reason = "The requirements content changed after approval. Present the revised draft for review."
            elif needs_prototype and prototype and state.get("prototype_approved") and prototype != state["prototype_approved"]:
                reason = "The prototype changed after approval. Open its current review checkpoint."
            else:
                reason = "An approval is still pending. Open the missing review checkpoint with its actual controls."
            return json.dumps({"error": "Finish the owner review of the clickable prototype (when applicable) "
                                        "and requirements before handing off downstream work. " + reason})
        if update and agent_id != "change-manager" and not ready:
            return json.dumps({"error": "Change management must finish its impact review and resolve any "
                                        "owner decisions before planning or implementation."})

    if update and "change-manager" in identities:
        if len(batch) != 1:
            return json.dumps({"error": "Run Change management on its own before starting other agents."})
        report_path = report.relative_to(root).as_posix()
        task = batch[0]
        task_context = task.get("context") or ""
        batch = [{**task, "role": "leaf", "context": (
            f"{task_context}\n\nRead requirements.md, the current source and tests, the Project Brain and "
            f"progress ledger, and the previous requirements at {update.get('baseline_requirements') or 'no saved path'}. "
            "Check the impact on existing features, interfaces, data/migrations, dependencies and tests. "
            f"Write your findings to {report_path}. First line: 'Status: Ready' only when there are no "
            "unresolved owner decisions, otherwise 'Status: Needs input'. Include the conflicts, trade-offs, "
            "recommended options, and specific questions in the report and your reply. Apply any owner "
            "decisions in the handoff before reassessing. Do not edit product code or write the implementation plan."
        )}]
        single = False
    elif ready and any(agent_id not in {"req-engineer", "researcher"} for agent_id in identities):
        report_path = report.relative_to(root).as_posix()
        batch = [
            {**task, "context": f"{task.get('context') or ''}\nRead the approved change review at {report_path}."}
            for task in batch
        ]
        single = False

    preferences = settings.agent_model_overrides()
    runtimes = []
    legacy_models = state.get("models") or {}
    for agent_id in identities:
        try:
            selection = settings.resolve_agent_model(agent_id, preferences, legacy_models)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        runtimes.append(selection)
    return delegate_task(
        goal=args.get("goal"), context=args.get("context"), tasks=None if single else batch,
        model=args.get("model"), max_iterations=args.get("max_iterations"), role=args.get("role"),
        background=True, parent_agent=agent, task_runtimes=runtimes,
    )
