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
