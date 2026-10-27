"""Keep-going rules, and the runner acting on them with a scripted engine."""

from __future__ import annotations

import subprocess
import time
from dataclasses import replace
from pathlib import Path

import pytest

from lyra_lite import watchdog
from lyra_lite.engines.base import TurnResult
from lyra_lite.runner import ProjectRunner
from lyra_lite.store import ProjectStore
from tests.lyra_lite.progress_cases import CLAUDE_DELIVERED, HERMES_DELIVERED

BASE = watchdog.Facts(
    now=10_000.0, keep_going=True, paused=False, busy=False, queued=0, helpers=0,
    open_inbox=0, ledger_running=True, last_reply="Wave 2 is committed.",
    last_turn_end=10_000.0 - 3600, progress_mark="", nudges_today=0, no_progress=0,
    last_mark=None, gave_up=False,
)


def test_nudges_only_an_idle_project_with_unfinished_work():
    assert watchdog.decide(BASE) == (True, "idle with unfinished work")
    blockers = {
        "keep_going": False, "paused": True, "busy": True, "queued": 1, "helpers": 1,
        "open_inbox": 1, "ledger_running": False, "last_turn_end": None,
        "nudges_today": 8, "gave_up": True,
    }
    for field, value in blockers.items():
        go, reason = watchdog.decide(replace(BASE, **{field: value}))
        assert not go, (field, reason)
    assert not watchdog.decide(replace(BASE, last_turn_end=BASE.now - 60))[0]


@pytest.mark.parametrize("reply", [
    "Which colour do you prefer?",
    "## What I need from you\n1. Open Google Cloud…",
    "Please approve the requirements summary.",
])
def test_never_nudges_over_a_question_for_the_owner(reply):
    assert watchdog.awaits_owner(reply)
    assert not watchdog.decide(replace(BASE, last_reply=reply))[0]


class ScriptedEngine:
    name = "scripted"

    def __init__(self, store: ProjectStore, edit: bool):
        self.store, self.edit, self.turns = store, edit, []

    def run_turn(self, text, history, hooks):
        self.turns.append(text)
        if self.edit:
            (self.store.root / f"step{len(self.turns)}.txt").write_text(text)
        msgs = history + [{"role": "user", "content": text},
                          {"role": "assistant", "content": "Did the next step."}]
        return TurnResult(reply="Did the next step.", messages=msgs)

    def interrupt(self): ...
    def close(self): ...


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / ".sdlc").mkdir(parents=True)
    (root / ".sdlc" / "progress.md").write_text(
        "## Phase ledger\n| Phase | Status |\n|---|---|\n| Remaining development | running |\n")
    for args in (["init", "-q"], ["config", "user.email", "t@t.invalid"], ["config", "user.name", "T"]):
        subprocess.run(["git", *args], cwd=root, check=True)
    return root


def _wait_idle(runner: ProjectRunner, turns: int, engine: ScriptedEngine) -> None:
    deadline = time.time() + 20
    while time.time() < deadline:
        if len(engine.turns) >= turns and not runner.snapshot()["running"] and not runner.snapshot()["queue"]:
            return
        time.sleep(0.05)
    raise TimeoutError(engine.turns)


@pytest.mark.parametrize("edit", [True, False])
def test_runner_nudges_and_gives_up_without_progress(tmp_path, edit):
    root = _project(tmp_path)
    engines: list[ScriptedEngine] = []

    def factory(store, key):
        engines.append(ScriptedEngine(store, edit))
        return engines[-1]

    runner = ProjectRunner(ProjectStore(root), factory)
    try:
        runner.submit("build it")
        deadline = time.time() + 10
        while not engines and time.time() < deadline:
            time.sleep(0.05)
        _wait_idle(runner, 1, engines[0])
        settings = {"idle_minutes": 0}
        reasons = []
        for n in range(4):
            reasons.append(runner.watchdog_tick(settings, now=time.time() + 1))
            _wait_idle(runner, 1 + reasons.count("idle with unfinished work"), engines[0])
        nudges = [t for t in engines[0].turns if t == watchdog.NUDGE]
        if edit:
            # Each nudge moved the project (the turn checkpoint commits it).
            assert len(nudges) == 4
        else:
            assert "gave up: no progress" in reasons
            assert len(nudges) == 2
            # The owner writing again re-arms it.
            runner.submit("try again")
            _wait_idle(runner, 4, engines[0])
            assert runner.watchdog_tick(settings, now=time.time() + 1) == "idle with unfinished work"
    finally:
        runner.shutdown()


def test_a_question_reply_or_stop_holds_the_watchdog(tmp_path):
    root = _project(tmp_path)
    runner = ProjectRunner(ProjectStore(root), lambda store, key: ScriptedEngine(store, True))
    try:
        runner.store.update_state(last_turn_end=1.0, last_reply="Shall I continue with wave 3?")
        assert runner.watchdog_tick({"idle_minutes": 0}) == "last reply asks the owner"
        runner.store.update_state(last_reply="Done.", paused=True)
        assert runner.watchdog_tick({"idle_minutes": 0}) == "stopped by owner"
        runner.set_keep_going(False)
        runner.store.update_state(paused=False)
        assert runner.watchdog_tick({"idle_minutes": 0}) == "off"
    finally:
        runner.shutdown()


def test_reordered_progress_drives_focus_and_watchdog_without_reopening_closed_work(tmp_path):
    from lyra_lite.focus import focus_note

    root = _project(tmp_path)
    ledger = root / ".sdlc/progress.md"
    table = ("# Progress ledger\n| # | Phase | Agent | Status | Evidence / notes |\n"
             "|---|---|---|---|---|\n"
             "| 1 | Old work | Dev | resolved | fixed |\n"
             "| 2 | Old QA | QA | superseded | replacement verified |\n"
             "| 3 | Export | Dev | descoped | owner removed |\n"
             "| 4 | QA | QA | PASS | checked |\n")
    ledger.write_text(table)
    runner = ProjectRunner(ProjectStore(root), lambda store, key: ScriptedEngine(store, False))
    try:
        runner.store.update_state(last_turn_end=1.0, last_reply="Delivered.")
        assert "Not done:" not in focus_note(root)
        assert runner.watchdog_tick({"idle_minutes": 0}) == "no unfinished step in the ledger"
        ledger.write_text(table + "| 5 | New feature | Dev | running | in progress |\n")
        assert "Not done: New feature — running" in focus_note(root)
        assert runner.watchdog_tick({"idle_minutes": 0}) == "idle with unfinished work"
        # The nudge must finish before disposing of the test project.
        deadline = time.time() + 10
        while time.time() < deadline:
            if runner._engine is not None:
                _wait_idle(runner, 1, runner._engine)
                break
            time.sleep(0.01)
        assert runner._engine is not None
    finally:
        runner.shutdown()


@pytest.mark.parametrize("delivered", [CLAUDE_DELIVERED, HERMES_DELIVERED], ids=["claude-ledger", "hermes-ledger"])
def test_restored_project_does_not_restart_history_but_does_continue_reopened_qa(tmp_path, delivered):
    root = _project(tmp_path)
    ledger = root / ".sdlc/progress.md"
    ledger.write_text(delivered)
    # Reconstruct the runner from persisted project state, as after a restart.
    ProjectStore(root).init().update_state(last_turn_end=1.0, last_reply="Delivered.")
    engine = ScriptedEngine(ProjectStore(root), False)
    runner = ProjectRunner(ProjectStore(root), lambda store, key: engine)
    try:
        assert runner.watchdog_tick({"idle_minutes": 0}) == "no unfinished step in the ledger"
        assert engine.turns == []
        ledger.write_text(delivered + "\n## Regression\n| Phase | Status |\n|---|---|\n"
                          "| QA regression | reopened — new defect |\n")
        assert runner.watchdog_tick({"idle_minutes": 0}) == "idle with unfinished work"
        _wait_idle(runner, 1, engine)
        assert "Not done: QA regression — reopened" in engine.turns[0]
        assert "Not done: Development — running" not in engine.turns[0]
        assert "Not done: Rev 2 build — running" not in engine.turns[0]
    finally:
        runner.shutdown()
