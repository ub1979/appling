"""Duplicate detection preserves independent work and the live-job boundary."""
import copy
import json

import pytest

from lyra_lite.delegation import DelegationGuard


@pytest.fixture
def running(monkeypatch):
    records = []
    monkeypatch.setattr("tools.async_delegation.list_async_delegations", lambda: records)
    return records


def _record(running, args, key="job", session="project"):
    running.append({"delegation_id": key, "session_key": session, "status": "running",
                    "goals": [args.get("goal", "QA")]})
    return json.dumps({"status": "dispatched", "delegation_id": key})


def test_same_task_across_single_and_batch_reuses_job_and_mixed_batch_is_not_partially_sent(running):
    guard = DelegationGuard("project")
    task = {"goal": "QA", "context": "Reusable frontend"}
    sent = []

    def send(args):
        sent.append(args)
        return _record(running, args)

    guard.dispatch(task, send)
    for tasks in ([dict(task, role="leaf")], [task, {"goal": "Different work"}]):
        result = json.loads(guard.dispatch({"tasks": tasks}, send))
        assert result["status"] == "already_running" and result["delegation_ids"] == ["job"]
    assert sent == [task]


@pytest.mark.parametrize("difference", [
    {"goal": "Development"}, {"context": "Reusable backend"}, {"model": "another-model"},
    {"role": "orchestrator"},
])
def test_distinct_work_is_allowed(running, difference):
    guard = DelegationGuard("project")
    task = {"goal": "QA", "context": "Reusable frontend"}
    guard.dispatch(task, lambda args: _record(running, args))
    result = guard.dispatch({**task, **difference}, lambda args: _record(running, args, key="other"))
    assert json.loads(result)["delegation_id"] == "other"


@pytest.mark.parametrize("status", ["completed", "error", "interrupted"])
def test_finished_work_can_be_dispatched_again(running, status):
    guard = DelegationGuard("project")
    task = {"goal": "QA"}
    guard.dispatch(task, lambda args: _record(running, args))
    running[0]["status"] = status
    assert guard.reminder() == ""
    result = guard.dispatch(task, lambda args: _record(running, args, key="retest"))
    assert json.loads(result)["delegation_id"] == "retest"


def test_rebuild_restores_batch_and_only_considers_its_own_live_jobs(running):
    task = {"goal": "QA", "context": "Reusable"}
    history = [{"role": "assistant", "tool_calls": [{"id": "call", "function": {
        "name": "delegate_task", "arguments": json.dumps({"tasks": [task]})}}]},
        {"role": "tool", "tool_call_id": "call", "content": _record(running, task)}]
    original = copy.deepcopy(history)
    guard = DelegationGuard("project")
    guard.restore(history)
    assert history == original
    assert "QA" in guard.reminder() and "job" in guard.reminder()
    result = guard.dispatch(task, lambda _: pytest.fail("duplicate dispatched"))
    assert json.loads(result)["status"] == "already_running"

    other = DelegationGuard("other-project")
    other.restore(history)
    assert other.reminder() == ""
    result = other.dispatch(task, lambda args: _record(running, args, key="other", session="other-project"))
    assert json.loads(result)["status"] == "dispatched"


@pytest.mark.parametrize(("effort", "reasoning"), [
    ("high", {"enabled": True, "effort": "high"}),
    ("off", {"enabled": False}),
])
def test_agent_model_effort_is_resolved_with_its_own_provider(monkeypatch, effort, reasoning):
    from lyra_lite.settings import model_runtime

    calls = []

    def resolve(**kwargs):
        calls.append(kwargs)
        return {"provider": "custom", "api_key": "local-key", "base_url": "http://localhost/v1"}

    monkeypatch.setattr("hermes_cli.runtime_provider.resolve_runtime_provider", resolve)
    selection = {"provider": "custom:local", "model": "chosen-model", "effort": effort}
    result = model_runtime(selection)
    assert calls == [{"requested": "custom:local", "target_model": "chosen-model"}]
    assert result["provider"] == "custom:local"
    assert result["model"] == "chosen-model"
    assert result["reasoning"] == reasoning


def test_reloading_requirements_holds_planning_even_when_the_previous_draft_matches(tmp_path):
    from lyra_lite.delegation import dispatch_project_tasks
    from lyra_lite.review import requirements_revision
    from lyra_lite.store import ProjectStore

    (tmp_path / "requirements.md").write_text("# Current scope\nKeep orders editable.\n")
    store = ProjectStore(tmp_path).init()
    store.update_state(requirements_review=True, requirements_approved=requirements_revision(tmp_path))
    result = json.loads(dispatch_project_tasks(store, None, {"goal": "task-planner: Schedule new work"}))
    assert "Finish the owner review" in result["error"]
