"""Exercise real app-server pipes, durable context, controls and Git integration."""
import json
import sys
import threading
from pathlib import Path

import pytest

from lyra_lite.engines.codex import CodexEngine, usage_delta
from lyra_lite.engines.codex_jobs import dispatch
from lyra_lite.store import ProjectStore
from lyra_lite.development import git
from lyra_lite import review

FAKE = Path(__file__).resolve().parents[1] / "fakes/fake_codex_app_server.py"


class Hooks:
    def __init__(self, answer="deny"):
        self.events, self.cards, self.expired = [], [], []
        self.answer = answer
        self.asked = threading.Event()
    def emit(self, type_, **data):
        self.events.append({"type": type_, **data})
    def ask(self, kind, on_answer, **fields):
        self.cards.append({"kind": kind, **fields})
        self.asked.set()
        if self.answer is not None:
            on_answer(self.answer)
        return "card"
    def expire(self, item_id):
        self.expired.append(item_id)


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CODEX_STATE", str(tmp_path / "peer-state.json"))
    monkeypatch.setenv("FAKE_CODEX_LOG", str(tmp_path / "peer-log.jsonl"))
    for key, value in {"GIT_AUTHOR_NAME": "Test", "GIT_COMMITTER_NAME": "Test",
                       "GIT_AUTHOR_EMAIL": "test@example.invalid", "GIT_COMMITTER_EMAIL": "test@example.invalid"}.items():
        monkeypatch.setenv(key, value)
    store = ProjectStore(tmp_path / "project").init()
    instance = CodexEngine(workspace=str(store.root), session_key="test:chat", store=store,
                           system_prompt="Keep the project safe", command=[sys.executable, str(FAKE)])
    yield instance
    instance.close()


def records(engine):
    return [json.loads(s) for s in (engine.store.root.parent / "peer-log.jsonl").read_text().splitlines()]


def test_native_turn_streams_and_reuses_context_across_reconnect(engine):
    hooks = Hooks()
    first = engine.run_turn("hello", [], hooks)
    assert first.completed and first.reply == "Hello from native Codex"
    assert any(e["type"] == "delta" for e in hooks.events)
    assert first.usage["input"] == 400 and first.usage["cache_read"] == 600
    thread = engine._session["thread_id"]
    engine.close()
    second = engine.run_turn("next", first.messages, hooks)
    assert second.completed and engine._session["thread_id"] == thread
    calls = records(engine)
    assert len([c for c in calls if c.get("method") == "thread/start"]) == 1
    assert any(c.get("method") == "thread/resume" for c in calls)
    starts = [c for c in calls if c.get("method") == "turn/start"]
    assert starts[-1]["params"]["input"] == [{"type": "text", "text": "next"}]
    initial = next(c for c in calls if c.get("method") == "thread/start")["params"]
    assert initial["cwd"] == str(engine.store.root)
    assert initial["developerInstructions"].startswith("Keep the project safe")
    assert initial["sandbox"] == "workspace-write" and initial["approvalPolicy"] == "on-request"
    assert initial["config"]["features.multi_agent"] is False


@pytest.mark.parametrize("answer,decision", [("once", "accept"), ("session", "acceptForSession"), ("deny", "decline"), ("always", "decline")])
def test_approval_maps_explicit_once_and_fails_closed(engine, answer, decision):
    hooks = Hooks(answer)
    result = engine.run_turn("approval", [], hooks)
    assert result.completed
    response = next(c for c in records(engine) if c.get("id") == "approval-1" and "method" not in c)
    assert response["result"] == {"decision": decision}
    assert hooks.cards[0]["choices"][0] == "once"
    assert "always" not in hooks.cards[0]["choices"]


def test_stop_unblocks_pending_approval_and_interrupts(engine):
    hooks = Hooks(None)
    results = []
    worker = threading.Thread(target=lambda: results.append(engine.run_turn("approval", [], hooks)))
    worker.start()
    assert hooks.asked.wait(5)
    engine.interrupt()
    worker.join(5)
    assert not worker.is_alive()
    assert hooks.expired == ["card"]
    assert results[0].interrupted
    assert any(c.get("method") == "turn/interrupt" for c in records(engine))


def test_disconnect_reports_failure_without_replaying_work(engine):
    result = engine.run_turn("disconnect", [], Hooks())
    assert not result.completed and "disconnected" in result.error
    assert len([c for c in records(engine) if c.get("method") == "turn/start"]) == 1


def test_unknown_server_request_is_rejected(engine):
    assert engine.run_turn("unknown", [], Hooks()).completed
    response = next(c for c in records(engine) if c.get("id") == "unknown-1" and "method" not in c)
    assert response["error"]["code"] == -32601


def test_unselected_agent_and_unapproved_development_are_blocked(engine):
    engine._hooks = Hooks()
    with pytest.raises(ValueError, match="selected team"):
        dispatch(engine, {"agent": "security-auditor", "goal": "Audit"})
    engine.store.update_state(team=["sw-developer"])
    with pytest.raises(ValueError, match="requirements approval"):
        dispatch(engine, {"agent": "sw-developer", "goal": "Develop"})


def test_native_workers_write_disjoint_worktrees_and_integrate(engine):
    root = engine.store.root
    git(root, "init")
    (root / "contract.txt").write_text("frozen")
    git(root, "add", "contract.txt")
    git(root, "commit", "-m", "Baseline")
    engine.role = "sw-developer"
    engine._hooks = Hooks()
    result = json.loads(dispatch(engine, {"tasks": [
        {"goal": "write a.txt", "context": json.dumps({"owned_paths": ["a.txt"]})},
        {"goal": "write b.txt", "context": json.dumps({"owned_paths": ["b.txt"]})},
    ]}))
    assert "error" not in result, result
    assert (root / "a.txt").read_text() == (root / "b.txt").read_text()
    assert git(root, "status", "--porcelain") == ""
    worker_events = [e for e in engine._hooks.events if e.get("event") == "start"]
    assert len(worker_events) == 2 and len({e["subagent_id"] for e in worker_events}) == 2
    assert all(e["parent_id"] == engine.session_key for e in worker_events)
    assert engine.helpers() == []


def test_usage_uses_current_totals_delta_not_lifetime_context():
    before = {"inputTokens": 500000, "cachedInputTokens": 300000, "outputTokens": 2000}
    total = {"inputTokens": 510000, "cachedInputTokens": 306000, "outputTokens": 2100}
    assert usage_delta(total, before) == {"input": 4000, "cache_read": 6000, "cache_write": 0, "output": 100, "reasoning": 0}


def test_resolved_server_request_releases_card_without_owner_action(engine):
    hooks = Hooks(None)
    result = engine.run_turn("resolved", [], hooks)
    assert result.completed and result.reply == "Request no longer pending"
    assert hooks.expired
    assert not any(c.get("id") == "approval-1" and "method" not in c for c in records(engine))
