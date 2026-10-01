"""The owner's chat survives engine context compression and old projects."""

from __future__ import annotations

import time
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
