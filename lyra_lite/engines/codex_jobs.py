"""Codex role sessions and bounded, ownership-checked coding waves."""
from __future__ import annotations

import json
import time
import uuid
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


def _run(parent, task, *, role, workspace, session_key):
    from lyra_lite.engines.codex import CodexEngine
    child = CodexEngine(workspace=str(workspace), session_key=session_key,
                        system_prompt=parent.system_prompt, store=parent.store,
                        role=role, parent=parent, command=parent.command)
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
            if available(parent.store.root):
                hosts = AppHosts()
                try:
                    preview = hosts.open(parent.store.root)
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


def dispatch(parent, args):
    batch = args.get("tasks") or [args]
    if not isinstance(batch, list) or not 1 <= len(batch) <= 3:
        raise ValueError("Assign 1–3 tasks at a time.")
    if any(not isinstance(t, dict) or not isinstance(t.get("goal"), str) or not t["goal"].strip() for t in batch):
        raise ValueError("Each task needs a goal.")
    if parent.role == "sw-developer":
        # Genuine parallel coding is permitted only through DevelopmentWave.
        from lyra_lite.settings import _section
        cfg = _section().get("parallel_development") or {}
        if cfg.get("enabled") is False:
            raise ValueError("Parallel development is disabled; finish directly in the development session.")
        try:
            limit = min(3, max(1, int(cfg.get("max_workers", 3))))
        except (TypeError, ValueError):
            limit = 3
        def execute(prepared, records):
            def run(pair):
                index, (task, record) = pair
                return _run(parent, task, role="coding-leaf", workspace=record["workspace"],
                            session_key=parent.session_key + ":leaf:" + uuid.uuid4().hex)
            with ThreadPoolExecutor(max_workers=limit, thread_name_prefix="appling-codex-leaf") as pool:
                results = list(pool.map(run, enumerate(zip(prepared, records))))
            return json.dumps({"results": results})
        return DevelopmentWave(parent.store.root, limit).dispatch(parent, {"tasks": batch}, executor=execute)
    if parent.role != "coordinator":
        raise ValueError("Leaf agents cannot delegate.")
    identities = [t.get("agent") or agent_for_goal(t["goal"]) for t in batch]
    selected = set(parent.store.state().get("team") or []) | {"req-engineer", "task-planner"}
    if any(role not in selected or role not in LABELS for role in identities):
        raise ValueError("Assign an explicit agent from the owner's selected team.")
    if "req-engineer" in identities:
        raise ValueError("Run the requirements interview in Appling's owner conversation with skill_view and clarify.")
    _review_guard(parent.store, identities)
    results = []
    # Different roles share project files. They run in dependency order; only
    # disjoint coding leaves run concurrently in isolated worktrees.
    for task, role in zip(batch, identities):
        if parent._stopped.is_set():
            break
        if role == "change-manager":
            state = parent.store.state()
            update = review.active_update(parent.store.root, state)
            if update:
                report = review.change_report(parent.store.root, update, review.requirements_revision(parent.store.root))
                task = {**task, "context": str(task.get("context") or "") + f"\nWrite the impact review to {report}. Previous requirements: {update.get('baseline_requirements')}."}
        result = _run(parent, task, role=role, workspace=parent.store.root,
                      session_key=parent.session_key + ":role:" + role)
        results.append(result)
        if result["status"] != "completed":
            break
    return json.dumps({"results": results})
