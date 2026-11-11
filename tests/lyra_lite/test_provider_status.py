"""Provider failures travel from the core through helper callbacks to saved UI state."""
from types import SimpleNamespace

from agent.conversation_loop import _notify_provider_status
from lyra_lite.engines.hermes import HermesEngine
from lyra_lite.store import ProjectStore
from tools.delegate_tool import _build_child_progress_callback


def test_helper_retry_persists_across_refresh_and_clears_on_recovery(tmp_path):
    store = ProjectStore(tmp_path).init()
    engine = HermesEngine(workspace=str(tmp_path), session_key="test", store=store)
    child_progress = _build_child_progress_callback(
        0, "Requirements review", SimpleNamespace(tool_progress_callback=engine._on_progress),
        subagent_id="child-1", model="test-model")
    def child_status(kind, text):
        child_progress("subagent.provider_status", preview=text)
    agent = SimpleNamespace(provider="custom", model="test-model", status_callback=child_status)
    _notify_provider_status(agent, "error", reason="rate_limit")
    _notify_provider_status(agent, "retrying", reason="rate_limit", wait_seconds=600,
                            attempt=1, max_attempts=3)
    status = ProjectStore(tmp_path).state()["provider_statuses"]["child-1"]
    assert status["state"] == "retrying"
    assert status["goal"] == "Requirements review"
    assert status["model"] == agent.model
    assert status["retry_at"] > 0
    assert status["attempt"] == 1
    _notify_provider_status(agent, "recovered")
    assert store.state()["provider_statuses"] == {}


def test_main_failure_and_paused_project_ignore_late_helper_events(tmp_path):
    store = ProjectStore(tmp_path).init()
    engine = HermesEngine(workspace=str(tmp_path), session_key="test", store=store)
    agent = SimpleNamespace(provider="custom", model="main-model", status_callback=engine._on_status)
    _notify_provider_status(agent, "error", reason="auth")
    assert store.state()["provider_statuses"]["main"]["reason"] == "auth"
    store.update_state(paused=True, provider_statuses={})
    _notify_provider_status(agent, "retrying", reason="auth", wait_seconds=10)
    assert store.state()["provider_statuses"] == {}


def test_broken_ui_callback_does_not_interrupt_model_retry():
    def broken(*args):
        raise RuntimeError("UI disconnected")
    _notify_provider_status(SimpleNamespace(status_callback=broken), "retrying")
