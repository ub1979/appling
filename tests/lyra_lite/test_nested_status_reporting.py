"""Real nested callbacks must reach the display without changing model history."""
from types import SimpleNamespace

from lyra_lite.engines.hermes import HermesEngine
from lyra_lite.status_updates import StatusUpdates
from lyra_lite.store import ProjectStore
from tools.delegate_tool import _build_child_progress_callback


def test_nested_activity_and_provider_identity_reach_status_reporter(tmp_path):
    store = ProjectStore(tmp_path).init()
    reporter = StatusUpdates(store)
    engine = HermesEngine(workspace=str(tmp_path), session_key="status-test", store=store)
    engine._hooks = SimpleNamespace(emit=store.append_event)
    outer = _build_child_progress_callback(0, "sw-developer: lead", SimpleNamespace(
        tool_progress_callback=engine._on_progress), subagent_id="lead")
    leaf = _build_child_progress_callback(0, "Implement archive", SimpleNamespace(
        tool_progress_callback=outer), subagent_id="leaf", parent_id="lead", depth=1)
    snap = {"chat_id": store.state()["chat_id"], "helpers": [{"goal": "sw-developer: lead", "started": 0}]}
    history = store.messages_path.read_bytes() if store.messages_path.exists() else None
    outer("subagent.start")
    leaf("subagent.spawn_requested")
    leaf("subagent.start")
    leaf("tool.started", "patch", "archive.ts")
    leaf("subagent.thinking", preview="Checking archive limits")
    leaf("subagent.provider_status", preview={"state": "retrying"})
    assert set(store.state()["provider_statuses"]) == {"leaf"}
    leaf("subagent.provider_status", preview={"state": "recovered"})
    events, _ = store.read_events(0)
    tools = [e for e in events if e.get("event") == "tool"]
    assert len(tools) == 1
    assert tools[0]["subagent_id"] == "leaf" and tools[0]["parent_id"] == "lead"
    timestamp = tools[0]["ts"]
    text = reporter.tick(snap, now=timestamp + 1)
    assert "1 subagent" in text and "editing a file, 0m 1s ago" in text
    assert "waiting for the AI" not in text
    assert (store.messages_path.read_bytes() if store.messages_path.exists() else None) == history
    leaf("subagent.complete", status="completed")
    text = reporter.tick(snap, now=timestamp + 301)
    assert "returned" in text


def test_quiet_tool_clock_never_infers_an_ai_wait(tmp_path):
    store = ProjectStore(tmp_path).init()
    reporter = StatusUpdates(store)
    store.append_event("helper", event="tool", tool="delegate_task", ts=1)
    store.append_event("helper", event="progress", subagent_id="lead", ts=420, api_calls=9)
    text = reporter.tick({"chat_id": store.state()["chat_id"],
                          "helpers": [{"goal": "sw-developer: lead", "started": 1}]}, now=428)
    assert "7m 7s ago" in text
    assert "waiting for the AI" not in text
    assert "heartbeat" in text
