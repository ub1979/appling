"""The owner's chat survives engine context compression and old projects."""

from __future__ import annotations

import time
import threading
from pathlib import Path

from lyra_lite.engines.base import TurnResult
from lyra_lite.runner import ProjectRunner
from lyra_lite.store import ProjectStore


class CompressingEngine:
    """Every third turn the engine compresses its history to a summary."""

    name = "scripted"

    def __init__(self):
        self.turns = 0
        self.seen_history: list[list[dict]] = []

    def run_turn(self, text, history, hooks):
        self.turns += 1
        self.seen_history.append(list(history))
        msgs = history + [{"role": "user", "content": text}, {"role": "assistant", "content": f"reply {self.turns}"}]
        if self.turns == 3:
            msgs = [{"role": "user", "content": "[summary of earlier work]"}] + msgs[-2:]
        return TurnResult(reply=f"reply {self.turns}", messages=msgs)

    def interrupt(self): ...
    def close(self): ...


def _wait(runner: ProjectRunner, engine: CompressingEngine, turns: int) -> None:
    deadline = time.time() + 10
    while time.time() < deadline:
        if engine.turns >= turns and not runner.snapshot()["running"] and not runner.snapshot()["queue"]:
            return
        time.sleep(0.02)
    raise TimeoutError


def test_compression_shrinks_engine_history_but_never_the_owners_chat(tmp_path: Path):
    engine = CompressingEngine()
    runner = ProjectRunner(ProjectStore(tmp_path / "p"), lambda store, key: engine)
    try:
        for i in range(1, 5):
            runner.submit(f"message {i}")
            _wait(runner, engine, i)
        # The engine continued from its compressed history, including the latest turns.
        assert engine.seen_history[3][0]["content"] == "[summary of earlier work]"
        assert engine.seen_history[3][-1]["content"] == "reply 3"
        # The owner still sees every message.
        shown = [e["content"] for e in runner.store.transcript()]
        assert shown == [x for i in range(1, 5) for x in (f"message {i}", f"reply {i}")]
    finally:
        runner.shutdown()


def test_missing_transcript_is_rebuilt_from_the_activity_log(tmp_path: Path):
    store = ProjectStore(tmp_path / "p").init()
    store.append_event("turn_start", turn="a", kind="user", text="old chat")
    store.append_event("turn_end", turn="a", status="done", reply="old reply")
    store.append_event("chat_started", chat_id="x")
    store.append_event("turn_start", turn="b", kind="user", text="hello")
    store.append_event("turn_end", turn="b", status="done", reply="hi there")
    store.append_event("turn_start", turn="c", kind="helper_done", text="[report]")
    store.append_event("turn_end", turn="c", status="done", reply="all done")
    runner = ProjectRunner(store, lambda s, k: CompressingEngine())
    try:
        assert [e["content"] for e in store.transcript()] == ["hello", "hi there", "[report]", "all done"]
    finally:
        runner.shutdown()


def test_answered_interview_is_visible_during_a_turn_and_after_reload(tmp_path):
    from lyra_lite.server import display_messages

    store = ProjectStore(tmp_path / "interview").init()
    store.update_state(turn={"id": "active", "text": "Build a dashboard", "started": 1.0, "kind": "user"})
    item = store.add_inbox("question", question="Which data?", created=2.0)
    store.close_inbox(item["id"], "answered", "CSV and PostgreSQL")
    secret = store.add_inbox("secret", question="Paste token", created=3.0)
    store.close_inbox(secret["id"], "answered", "private-key")
    shown = display_messages(store.conversation())
    assert [e["content"] for e in shown] == ["Build a dashboard", "Which data?", "CSV and PostgreSQL"]
    assert shown[0]["active"]
    store.append_transcript([
        {"role": "user", "content": "Build a dashboard", "ts": 1.0},
        {"role": "assistant", "content": "Next we will build the prototype.", "ts": time.time() + 1},
    ])
    store.update_state(turn=None)
    reopened = ProjectStore(store.root)
    shown = display_messages(reopened.conversation())
    assert [e["content"] for e in shown][:3] == ["Build a dashboard", "Which data?", "CSV and PostgreSQL"]
    assert len(shown) == 4
    reopened.archive_chat()
    assert reopened.conversation() == []


def test_agent_report_keeps_its_origin_in_the_saved_conversation():
    from lyra_lite.server import display_messages

    report = display_messages([{"role": "user", "kind": "helper_done", "content": "Discovery complete"}])
    assert report == [{"role": "user", "kind": "system", "content": "Discovery complete"}]


def test_intermediate_explanation_is_durable_before_the_turn_finishes(tmp_path):
    ready, release = threading.Event(), threading.Event()

    class ExplainingEngine(CompressingEngine):
        def run_turn(self, text, history, hooks):
            hooks.emit("interim", text="Here is the draft for review.", already_streamed=True)
            ready.set()
            assert release.wait(10)
            return TurnResult(reply="Now choose an option.", messages=history)

    store = ProjectStore(tmp_path / "explanations")
    runner = ProjectRunner(store, lambda s, key: ExplainingEngine())
    try:
        runner.submit("Build a task list")
        assert ready.wait(10)
        reopened = ProjectStore(store.root)
        assert [m["content"] for m in reopened.conversation()] == [
            "Build a task list", "Here is the draft for review."]
        assert reopened.messages() == []  # UI persistence never mutates cached model context.
        release.set()
        deadline = time.monotonic() + 10
        while runner.snapshot()["running"] and time.monotonic() < deadline:
            time.sleep(.02)
        assert [m["content"] for m in reopened.conversation()] == [
            "Build a task list", "Here is the draft for review.", "Now choose an option."]
    finally:
        release.set()
        runner.shutdown()
