"""How the Claude engine tells turns apart as the Claude program's messages
arrive: every turn that starts must end, so Appling never stays busy."""

from __future__ import annotations

import asyncio

import pytest

sdk = pytest.importorskip("claude_agent_sdk")

from lyra_lite.engines.claude import ClaudeEngine, _Turn  # noqa: E402


class _Hooks:
    def __init__(self):
        self.started: list[dict] = []
        self.ended: list[tuple[dict, str, str | None]] = []
        self.busy = False

    def emit(self, type_, **data):
        pass

    def begin_external_turn(self, kind, text, display=None):
        if self.busy:
            return None
        self.busy = True
        turn = {"id": f"t{len(self.started)}", "text": text}
        self.started.append(turn)
        return turn

    def end_external_turn(self, turn, *, reply, usage=None, error=None):
        self.busy = False
        self.ended.append((turn, reply, error))


def _engine():
    engine = ClaudeEngine(workspace=".", session_key="k")
    engine._hooks = _Hooks()
    return engine


def _rate_limit():
    return sdk.RateLimitEvent(rate_limit_info=sdk.RateLimitInfo(status="allowed_warning"),
                              uuid="u", session_id="s")


def _report_turn(engine, words):
    engine._route(sdk.SystemMessage(subtype="init", data={}))
    engine._route(sdk.AssistantMessage(content=[sdk.TextBlock(text=words)], model="m"))
    engine._route(sdk.ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1,
                                    is_error=False, num_turns=1, session_id="s", result=words))


def test_a_rate_limit_notice_while_idle_starts_no_turn():
    engine = _engine()
    engine._route(_rate_limit())
    assert engine._current is None
    assert engine._hooks.started == []

    _report_turn(engine, "REPORT")
    assert [reply for _, reply, _ in engine._hooks.ended] == ["REPORT"]
    assert not engine._hooks.busy


def test_a_turn_left_without_a_result_is_closed_when_the_next_one_starts():
    engine = _engine()
    engine._route(sdk.SystemMessage(subtype="init", data={}))
    engine._route(sdk.AssistantMessage(content=[sdk.TextBlock(text="HALF")], model="m"))
    # No result for that one; the Claude program starts another turn.
    _report_turn(engine, "NEXT")
    replies = [reply for _, reply, _ in engine._hooks.ended]
    assert replies == ["HALF", "NEXT"]
    assert len(engine._hooks.started) == 2
    assert not engine._hooks.busy


def test_stop_ends_a_report_turn_even_if_the_claude_program_stays_silent():
    engine = _engine()
    engine._route(sdk.SystemMessage(subtype="init", data={}))
    engine._route(sdk.AssistantMessage(content=[sdk.TextBlock(text="WORKING")], model="m"))
    assert engine._hooks.busy
    engine._stop_turn()
    assert engine._current is None
    assert not engine._hooks.busy


def test_stop_ends_the_owners_turn_even_if_the_claude_program_stays_silent():
    async def run():
        engine = _engine()
        engine.STOP_GRACE = 0.05
        turn = _Turn(engine._hooks, "hi", asyncio.get_running_loop().create_future())
        engine._pending.append(turn)
        engine._route(sdk.SystemMessage(subtype="init", data={}))
        engine._route(sdk.UserMessage(content="hi"))
        engine._route(sdk.AssistantMessage(content=[sdk.TextBlock(text="PARTIAL")], model="m"))
        engine._interrupted = True
        engine._stop_turn()
        reply, _usage, _error, interrupted = await asyncio.wait_for(turn.future, 2)
        return reply, interrupted, engine._current

    reply, interrupted, current = asyncio.run(run())
    assert (reply, interrupted, current) == ("PARTIAL", True, None)
