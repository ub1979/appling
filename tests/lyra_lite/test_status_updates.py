"""Status timers are display-only, and never confuse liveness with progress."""
import copy

import pytest

from lyra_lite.server import display_messages
from lyra_lite.status_updates import StatusUpdates
from lyra_lite.store import ProjectStore


def test_five_minute_notes_persist_without_changing_cached_history_or_state(tmp_path):
    store = ProjectStore(tmp_path).init()
    store.save_messages([{"role": "user", "content": "Build it"}])
    reporter = StatusUpdates(store)
    snap = {"chat_id": store.state()["chat_id"], "helpers": [{"goal": "sw-developer: Build", "started": 10}]}
    state, history = store.state_path.read_bytes(), store.messages_path.read_bytes()
    store.append_event("helper", event="tool", tool="patch", ts=250)
    assert reporter.tick(snap, now=309) is None
    first = reporter.tick(snap, now=310)
    assert "editing a file, 1m 0s ago" in first
    assert reporter.tick(snap, now=311) is None
    store.append_event("helper", event="progress", ts=609, api_calls=42)
    second = reporter.tick(snap, now=610)
    assert "No new tool activity" in second  # heartbeats are not new progress
    assert store.state_path.read_bytes() == state
    assert store.messages_path.read_bytes() == history
    assert [m["kind"] for m in display_messages(store.conversation())] == ["status", "status"]
    assert ProjectStore(tmp_path).transcript() == store.transcript()


@pytest.mark.parametrize("condition", [{"paused": True}, {"inbox": [{"kind": "question"}]}, {"helpers": []}])
def test_no_status_for_idle_paused_or_owner_waits(tmp_path, condition):
    store = ProjectStore(tmp_path).init()
    reporter = StatusUpdates(store)
    snap = {"chat_id": store.state()["chat_id"], "helpers": [{"goal": "QA", "started": 10}]}
    assert reporter.tick({**snap, **condition}, now=1000) is None
    assert store.transcript() == []


def test_disable_chat_reset_and_provider_wait(tmp_path):
    store = ProjectStore(tmp_path).init()
    reporter = StatusUpdates(store)
    snap = {"chat_id": store.state()["chat_id"], "running": True, "turn": {"started": 10}}
    assert reporter.tick(snap, {"enabled": False}, now=310) is None
    snap["provider_statuses"] = {"main": {"state": "retrying"}}
    assert reporter.tick(snap, now=310) is None
    assert "waiting on an AI connection" in reporter.tick(snap, now=610)
    original = copy.deepcopy(snap)
    assert reporter.tick(snap, now=611) is None
    assert snap == original
    snap["chat_id"] = "new-chat"
    snap["turn"] = {"started": 611}
    assert reporter.tick(snap, now=612) is None


def test_status_failure_cannot_disable_the_existing_keep_going_watchdog(tmp_path, monkeypatch):
    from lyra_lite.server import Lyra

    app = Lyra()
    checked = []

    class Runner:
        root = tmp_path

        def status_tick(self, settings):
            raise OSError("Display history unavailable")

        def watchdog_tick(self, settings):
            checked.append(True)
            app._stop.set()

    app.runners["project"] = Runner()
    monkeypatch.setattr("lyra_lite.server.lyra_settings", lambda: {"watchdog": {"check_seconds": 0.001}})
    app._watchdog_loop()
    assert checked == [True]


def test_queued_worker_is_not_reported_as_executing_or_waiting_for_ai(tmp_path):
    store = ProjectStore(tmp_path).init()
    reporter = StatusUpdates(store)
    snap = {'chat_id': store.state()['chat_id'], 'helpers': [{'goal': 'qa-engineer: Check', 'started': 10}]}
    store.append_event('helper', event='queued', subagent_id='qa', status='queued', ts=10)
    note = reporter.tick(snap, now=310)
    assert 'waiting for a shared worker slot' in note
    assert 'AI connection' not in note
    store.append_event('helper', event='start', subagent_id='qa', ts=311)
    assert 'waiting for a shared worker slot' not in reporter.tick(snap, now=610)
