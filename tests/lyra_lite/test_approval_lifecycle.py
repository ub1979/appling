"""Real permission waits and runner inboxes, without calling a model."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import time

import pytest

from lyra_lite.engines.base import TurnResult
from lyra_lite.engines.hermes import HermesEngine
from lyra_lite.runner import ProjectRunner
from lyra_lite.store import ProjectStore

COMMAND = "python3 -c 'open(\"approval-test.txt\",\"w\").write(\"ok\")'"


@pytest.fixture(autouse=True)
def approval(monkeypatch):
    # Import after conftest has installed the temporary HERMES_HOME; never
    # inherit the developer's permanent allowlist during test collection.
    from tools import approval

    monkeypatch.setattr(approval, "_permanent_approved", set())
    monkeypatch.setattr(approval, "_session_approved", {})
    return approval


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.setattr("lyra_lite.runner.checkpoint", lambda *a, **kw: None)
    runner = ProjectRunner(ProjectStore(tmp_path), lambda *_: None)
    yield runner
    runner.shutdown()


def _inbox(runner, count=1):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        items = runner.store.inbox(status="open")
        if len(items) == count:
            return items
        time.sleep(0.01)
    raise AssertionError(runner.store.inbox())


def _finish_owner_turn(runner):
    runner._finish_turn({"id": "owner", "kind": "user", "text": "status?"},
                        TurnResult(reply="Still working.", messages=[]))


def test_claude_permission_survives_unrelated_owner_turn(runner):
    sdk = pytest.importorskip("claude_agent_sdk")
    from lyra_lite.engines.claude import ClaudeEngine

    async def run():
        engine = ClaudeEngine(workspace=str(runner.root), session_key=runner.session_key())
        engine._hooks = runner._hooks
        runner._hooks.turn_id = "owner"
        pending = asyncio.create_task(engine._can_use_tool("Bash", {"command": COMMAND}, None))
        try:
            item, = await asyncio.to_thread(_inbox, runner)
            _finish_owner_turn(runner)
            assert runner.store.inbox_item(item["id"])["status"] == "open"
            assert runner.answer(item["id"], "once")
            assert isinstance(await asyncio.wait_for(pending, 5), sdk.PermissionResultAllow)
        finally:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)

    asyncio.run(run())


@pytest.mark.parametrize("action", ["stop", "shutdown", "cancel", "timeout"])
def test_claude_wait_cleanup_denies_and_removes_card(runner, monkeypatch, action):
    sdk = pytest.importorskip("claude_agent_sdk")
    from lyra_lite.engines.claude import ClaudeEngine

    async def run():
        engine = ClaudeEngine(workspace=str(runner.root), session_key=runner.session_key())
        engine._hooks = runner._hooks
        if action == "timeout":
            monkeypatch.setattr("lyra_lite.engines.claude.permissions.APPROVAL_TIMEOUT_S", 0.2)
        pending = asyncio.create_task(engine._can_use_tool("Bash", {"command": COMMAND}, None))
        try:
            if action != "timeout":
                await asyncio.to_thread(_inbox, runner)
            if action == "stop":
                runner.stop_turn()
            elif action == "shutdown":
                runner.shutdown()
            elif action == "cancel":
                pending.cancel()
            if action == "cancel":
                with pytest.raises(asyncio.CancelledError):
                    await pending
            else:
                assert isinstance(await asyncio.wait_for(pending, 5), sdk.PermissionResultDeny)
            assert runner.store.inbox(status="open") == []
            item, = runner.store.inbox()
            assert not runner.answer(item["id"], "once")
        finally:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)

    asyncio.run(run())


@pytest.fixture
def hermes(runner, monkeypatch, approval):
    monkeypatch.setattr(approval, "_get_approval_timeout", lambda: 10)
    engine = HermesEngine(workspace=str(runner.root), session_key=runner.session_key())
    engine._hooks = runner._hooks
    yield engine
    approval.unregister_gateway_notify(engine.session_key)


def _wait_hermes(engine, command):
    from tools import approval
    from tools.interrupt import set_interrupt

    set_interrupt(False)
    return approval._await_gateway_decision(
        engine.session_key, engine._on_approval,
        {"command": command, "description": "test approval", "pattern_key": "test"},
    )


def test_hermes_timeout_removes_card(runner, hermes, monkeypatch, approval):
    monkeypatch.setattr(approval, "_get_approval_timeout", lambda: 0)
    result = _wait_hermes(hermes, "timed out")
    assert not result["resolved"]
    assert runner.store.inbox(status="open") == []
    assert not approval.has_blocking_approval(hermes.session_key)
    item, = runner.store.inbox()
    assert not runner.answer(item["id"], "once")


def test_hermes_cards_resolve_their_own_wait_out_of_order(runner, hermes):
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(_wait_hermes, hermes, "first")
        first_card, = _inbox(runner)
        second = pool.submit(_wait_hermes, hermes, "second")
        cards = {c["command"]: c for c in _inbox(runner, 2)}
        assert runner.answer(cards["second"]["id"], "once")
        assert second.result(5)["choice"] == "once"
        assert not first.done()
        assert runner.answer(first_card["id"], "deny")
        assert first.result(5)["choice"] == "deny"


def test_hermes_permission_survives_owner_turn_then_stop_denies_it(runner, hermes):
    runner._hooks.turn_id = "owner"
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(_wait_hermes, hermes, "background helper")
        item, = _inbox(runner)
        _finish_owner_turn(runner)
        assert runner.store.inbox_item(item["id"])["status"] == "open"
        runner.stop_turn()
        assert pending.result(5)["choice"] == "deny"
        assert runner.store.inbox(status="open") == []


def test_late_permission_after_stop_is_denied_without_open_card(runner, hermes):
    runner.stop_turn()
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(_wait_hermes, hermes, "arrived during Stop").result(5)
    assert result["choice"] == "deny"
    assert runner.store.inbox(status="open") == []


def test_expired_hermes_card_cannot_answer_a_new_request(runner, hermes, monkeypatch, approval):
    monkeypatch.setattr(approval, "_get_approval_timeout", lambda: 0)
    _wait_hermes(hermes, "expired")
    expired, = runner.store.inbox()
    monkeypatch.setattr(approval, "_get_approval_timeout", lambda: 10)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(_wait_hermes, hermes, "new request")
        current, = _inbox(runner)
        assert not runner.answer(expired["id"], "once")
        assert not pending.done()
        assert runner.answer(current["id"], "deny")
        assert pending.result(5)["choice"] == "deny"


@pytest.mark.parametrize("action", ["interrupt", "unregister"])
def test_hermes_native_wait_termination_cleans_inbox(runner, hermes, action, approval):
    def wait():
        from tools.interrupt import set_interrupt
        set_interrupt(action == "interrupt")
        try:
            def notify(data):
                cleanup = hermes._on_approval(data)
                if action == "unregister":
                    approval.unregister_gateway_notify(hermes.session_key)
                return cleanup
            return approval._await_gateway_decision(hermes.session_key, notify, {"command": "test"})
        finally:
            set_interrupt(False)

    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(wait).result(5)
    assert result["choice"] not in {"once", "session", "always"}
    assert runner.store.inbox(status="open") == []
