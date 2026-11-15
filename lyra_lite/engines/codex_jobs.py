"""Codex role sessions and bounded, ownership-checked coding waves."""
from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from lyra_lite import review
from lyra_lite.agents import LABELS, agent_for_goal
from lyra_lite.development import DevelopmentWave


class ChildHooks:
    def __init__(self, parent, child_id, goal):
        self.parent, self.child_id, self.goal = parent, child_id, goal

    def emit(self, type_, **data):
        fields = {"subagent_id": self.child_id, "parent_id": self.parent.session_key, "goal": self.goal}
        if type_ == "tool":
            self.parent._hooks.emit("helper", event="tool", tool=data.get("name"), **fields)
        elif type_ in {"status", "interim"}:
            self.parent._hooks.emit("helper", event="progress", preview=str(data.get("text") or "")[:300], **fields)
        elif type_ == "helper":
            # Preserve descendant identities through every level.
            self.parent._hooks.emit(type_, **data)

    def ask(self, kind, on_answer, **fields):
        fields["requester"] = {"subagent_id": self.child_id, "goal": self.goal,
                               "label": LABELS.get(agent_for_goal(self.goal), "Agent")}
        return self.parent._hooks.ask(kind, on_answer, **fields)

    def expire(self, item_id):
        self.parent._hooks.expire(item_id)


def _run(parent, task, *, role, workspace, session_key, worker=False, read_only=False):
    from lyra_lite.engines.codex import CodexEngine
    child = CodexEngine(workspace=str(workspace), session_key=session_key,
                        system_prompt=parent.system_prompt, store=parent.store,
                        role=role, parent=parent, command=parent.command, worker=worker, read_only=read_only)
    child.goal, child.started = task["goal"], time.time()
    child_id = session_key
    with parent._children_lock:
        if parent._stopped.is_set():
            return {"status": "interrupted", "exit_reason": "interrupted", "summary": "Stopped before launch"}
        parent._children[child_id] = child
    hooks = ChildHooks(parent, child_id, child.goal)
    parent._hooks.emit("helper", event="start", subagent_id=child_id, parent_id=parent.session_key,
                       goal=child.goal, model=child.selection["model"])
    hosts = None
    try:
        if role == "qa-engineer":
            from lyra_lite.preview import AppHosts, PreviewError, available
            if available(Path(workspace)):
                hosts = AppHosts()
                try:
                    preview = hosts.open(Path(workspace))
                    task = {**task, "context": str(task.get("context") or "") +
                            f"\nThe host has opened the local app preview: {preview['url']}. "
                            "Use this URL for real browser QA; no separate server or file URL is needed."}
                except PreviewError as exc:
                    task = {**task, "context": str(task.get("context") or "") + f"\nHost preview unavailable: {exc}. Report the real blocker."}
        if role == "sw-developer":
            review.record_plan_execution(parent.store, "sw-developer: " + child.goal)
        result = child.run_turn(task["goal"] + "\n\n" + str(task.get("context") or ""), [], hooks)
        status = "failed" if result.error else "interrupted" if result.interrupted else "completed" if result.completed else "incomplete"
        # Keep the full report on disk; cap only the inline handoff. No lifetime
        # billed-token heuristic is used to decide current context capacity.
        from lyra_lite.store import _atomic_write_json
        path = parent.store.dir / "codex" / "reports" / (uuid.uuid4().hex + ".json")
        record = {"goal": child.goal, "status": status, "exit_reason": status,
                  "summary": result.reply, "error": result.error, "usage": result.usage}
        _atomic_write_json(path, record)
        parent._hooks.emit("helper", event="complete", subagent_id=child_id, parent_id=parent.session_key,
                           goal=child.goal, status=status, summary=result.reply[:1200], usage=result.usage,
                           duration_seconds=round(time.time() - child.started, 2))
        return {**record, "summary": result.reply[:16000], "report": str(path)}
    finally:
        child.close()
        if hosts is not None:
            hosts.stop_all()
        with parent._children_lock:
            parent._children.pop(child_id, None)


def _review_guard(store, identities):
    state, root = store.state(), store.root
    update = review.active_update(root, state)
    requirements = review.requirements_revision(root)
    for role in identities:
        if role in {"req-engineer", "researcher", "ui-designer"}:
            continue
        if (state.get("requirements_review") or not requirements
                or requirements != state.get("requirements_approved")):
            raise ValueError("Finish the owner's requirements approval before downstream work.")
        if review.visual_project(root, state) and review.prototype_revision(root) != state.get("prototype_approved"):
            raise ValueError("Finish the owner's current prototype approval first.")
        if update and role != "change-manager":
            report = review.change_report(root, update, requirements)
            if not review.change_review_ready(report):
                raise ValueError("Change management must finish its impact review before planning or development.")
        if role in {"sw-developer", "website-builder", "debugger", "oop-restructurer", "qa-engineer", "code-reviewer"}:
            plan = review.implementation_plan(root)
            if (not state.get("plan_approved") or state.get("plan_requirements") != requirements
                    or (not review.plan_execution_started(state) and (not plan or plan["revision"] != state["plan_approved"]))):
                raise ValueError("Approve the current implementation plan before implementation or final QA.")


def _decision(parent, tasks, chosen, requested, reason, *, parallel):
    from lyra_lite.engines.worker_pool import WORKERS, worker_limit
    from lyra_lite.agents import LABELS
    label = LABELS.get(parent.role, "Appling")
    text = (f"{label}: using {chosen} worker{'s' if chosen != 1 else ''} for {len(tasks)} task{'s' if len(tasks) != 1 else ''} "
            f"(shared limit {worker_limit()}, including role leads). {reason}")
    if chosen and len(tasks) > chosen:
        text += " Remaining tasks run as slots become free."
    parent.store.append_transcript([{"role": "assistant", "kind": "status", "content": text, "ts": time.time()}])
    parent.store.append_event("status_update", text=text)
    parent.store.append_event("worker_plan", requested=requested, chosen=chosen, tasks=len(tasks),
                              reason=reason, parallel=parallel, role=parent.role, pool=WORKERS.snapshot())


def _context(task):
    value = task.get("context") or ""
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (ValueError, TypeError):
        parsed = None
    parsed = dict(parsed) if isinstance(parsed, dict) else {"instructions": str(value)}
    for key in ("owned_paths", "read_only"):
        if key in task:
            parsed[key] = task[key]
    return parsed


def dispatch(parent, args):
    from lyra_lite.engines.worker_pool import WORKERS, MAX_WORKERS, worker_limit
    if not parent.can_delegate:
        raise ValueError("Leaf workers cannot delegate.")
    batch = args.get("tasks") or [args]
    if not isinstance(batch, list) or not 1 <= len(batch) <= MAX_WORKERS:
        raise ValueError(f"Assign 1–{MAX_WORKERS} independent tasks per batch.")
    if any(not isinstance(t, dict) or not isinstance(t.get("goal"), str) or not t["goal"].strip() for t in batch):
        raise ValueError("Each task needs a goal.")
    coordinator = parent.role == "coordinator"
    identities = [t.get("agent") or (agent_for_goal(t["goal"]) if coordinator else parent.role) for t in batch]
    selected = set(parent.store.state().get("team") or []) | {"req-engineer", "task-planner"}
    # A running lead was already authorized by its owner; its helpers keep that
    # role. No helper may introduce an unselected team member.
    if coordinator and any(role not in selected or role not in LABELS for role in identities):
        raise ValueError("Assign an explicit agent from the owner's selected team.")
    if not coordinator and any(role != parent.role for role in identities):
        raise ValueError("Role helpers must keep their lead's selected role.")
    if "req-engineer" in identities and not (coordinator and args.get("parallel") is True
                                                 and all(_context(t).get("read_only") is True for t, r in zip(batch, identities) if r == "req-engineer")):
        raise ValueError("The owner interview stays in Appling's main conversation. Requirements helpers must be parallel read-only investigation.")
    _review_guard(parent.store, identities)
    reason = str(args.get("reason") or "").strip()
    if len(batch) > 1 and not reason:
        raise ValueError("Explain why these tasks are independent and how many workers are useful in reason.")
    reason = reason[:1200] or "One coherent role assignment; dependent work stays together."
    requested = args.get("workers", min(len(batch), worker_limit()))
    if isinstance(requested, bool) or not isinstance(requested, int) or not 1 <= requested <= MAX_WORKERS:
        raise ValueError(f"Choose workers between 1 and {MAX_WORKERS}.")
    parallel = (args.get("parallel") is True or not coordinator
                or (len(batch) == 1 and _context(batch[0]).get("read_only") is True))
    # Existing role handoffs remain serial unless explicitly declared independent.
    if not parallel:
        with WORKERS.reserve(1, parent._stopped, wait=True) as slots:
            count = slots.count
            if not count:
                return json.dumps({"error": "Stopped before an agent slot became free."})
            _decision(parent, batch, 1, requested, reason, parallel=False)
            results = []
            for task, role in zip(batch, identities):
                if parent._stopped.is_set():
                    break
                if role == "change-manager":
                    update = review.active_update(parent.store.root, parent.store.state())
                    if update:
                        report = review.change_report(parent.store.root, update, review.requirements_revision(parent.store.root))
                        task = {**task, "context": str(task.get("context") or "") + f"\nWrite the impact review to {report}. Previous requirements: {update.get('baseline_requirements')}."}
                result = _run(parent, task, role=role, workspace=parent.store.root,
                              session_key=parent.session_key + ":role:" + role)
                results.append(result)
                if result["status"] != "completed":
                    break
            return json.dumps({"results": results})
    # Nested calls never wait while holding the lead's slot: reserve currently
    # available capacity atomically, or return to the lead for direct work.
    with WORKERS.reserve(min(requested, len(batch)), parent._stopped, wait=coordinator) as slots:
        count = slots.count
        if not count:
            _decision(parent, batch, 0, requested, "All shared slots are occupied; no new workers started. Continue directly.", parallel=True)
            return json.dumps({"error": "No shared worker slots are free. Continue directly; retry delegation only when capacity changes.",
                               "pool": WORKERS.snapshot()})
        prepared = [{**t, "context": json.dumps(_context(t))} for t in batch]
        # Retain the existing setting for owners who explicitly disabled coding fan-out.
        from lyra_lite.settings import _section
        if parent.role == "sw-developer" and (_section().get("parallel_development") or {}).get("enabled") is False:
            raise ValueError("Parallel development is disabled; finish directly in the development session.")
        started = time.monotonic()
        observed = {"active": 0, "peak": 0}
        observed_lock = threading.Lock()
        def execute(tasks, records):
            _decision(parent, batch, count, requested, reason, parallel=True)
            jobs = queue.Queue()
            for entry in enumerate(zip(tasks, records)):
                jobs.put(entry)
            results = [None] * len(tasks)
            def run():
                try:
                    while not parent._stopped.is_set():
                        try:
                            index, (task, record) = jobs.get_nowait()
                        except queue.Empty:
                            break
                        with observed_lock:
                            observed["active"] += 1
                            observed["peak"] = max(observed["peak"], observed["active"])
                        try:
                            results[index] = _run(parent, task, role=identities[index], workspace=record["workspace"],
                                                  session_key=parent.session_key + ":worker:" + uuid.uuid4().hex,
                                                  worker=True, read_only=record.get("read_only", False))
                        finally:
                            with observed_lock:
                                observed["active"] -= 1
                finally:
                    slots.release()
            with ThreadPoolExecutor(max_workers=count, thread_name_prefix="appling-worker") as pool:
                futures = [pool.submit(run) for _ in range(count)]
                for future in futures:
                    future.result()
            return json.dumps({"results": [r or {"status": "interrupted", "exit_reason": "interrupted"} for r in results]})
        raw = DevelopmentWave(parent.store.root, MAX_WORKERS).dispatch(parent, {"tasks": prepared}, executor=execute)
        result = json.loads(raw)
        usage = {}
        for row in result.get("results", []):
            for key, value in row.get("usage", {}).items():
                usage[key] = usage.get(key, 0) + value
        parent.store.append_event("worker_wave_end", workers=count, tasks=len(batch), role=parent.role,
                                  elapsed_seconds=round(time.monotonic() - started, 2), peak_workers=observed["peak"], usage=usage,
                                  error=result.get("error"), recovery=result.get("recovery"))
        return raw
