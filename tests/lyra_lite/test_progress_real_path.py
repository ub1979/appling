"""Stale ledgers through the real runner, Hermes runtime and historical ledger formats.

Only model responses are scripted on local provider servers. Watchdog ticks
are explicit so absence of a restart is asserted without a timed sleep.
"""

import json
import threading

import pytest

from lyra_lite.project_map import read_map
from lyra_lite.server import Lyra
from tests.fakes.fake_openai_server import FakeOpenAIServer, text_step, tool_step
from tests.lyra_lite.progress_cases import CLAUDE_DELIVERED, HERMES_DELIVERED, NEW_FEATURE
from tests.lyra_lite.test_lyrad_real_path import _events, _wait_event, _write_config, env  # noqa: F401


def _focus(request):
    text = "\n".join(str(m["content"]) for m in request["messages"] if m["role"] == "user")
    return text.rsplit("[Project focus", 1)[-1]


@pytest.mark.parametrize("ledger_style", ["hermes", "claude"])
def test_status_qualifiers_drive_real_focus_and_continuation(env, ledger_style):
    with FakeOpenAIServer([]) as llm:
        _write_config(env["hermes_home"], llm.base_url, lyra_lite={
            "watchdog": {"enabled": False},
        })
        app = Lyra()
        app.start()
        try:
            runner = app.add_project(str(env["home"] / "Status qualifiers"), create=True)
            root = runner.root
            (root / ".sdlc").mkdir()
            ledger = root / ".sdlc/progress.md"
            # Exercise the named-column formats emitted by the audited Hermes
            # and Claude projects, without a delivery row masking QA's state.
            if ledger_style == "hermes":
                table = ("| Date | Phase | Status | Notes |\n|---|---|---|---|\n"
                         "| 2026-10-27 | QA | {status} | Current result |\n")
            else:
                table = ("| # | Phase | Agent | Status | Evidence / notes |\n|---|---|---|---|---|\n"
                         "| 1 | QA | QA | {status} | Current result |\n")
            cases = [
                ("PASS — 0 open HIGH/CRITICAL", "done"),
                ("APPROVED, no open defects", "done"),
                ("verified, nothing pending", "done"),
                ("done, FAIL", "running"),
                ("completed — but tests failing", "running"),
                ("PASS — 0 open HIGH; 2 open MEDIUM", "running"),
                ("PASS; owner acceptance pending", "owner"),
                ("not fully fixed", "running"),
                ("not completely confirmed", "running"),
                ("fixed locally; awaiting owner acceptance", "owner"),
                ("fix confirmed; awaiting owner approval", "owner"),
                ("PASS locally; previously failing integration test still broken", "running"),
                ("PASS — previously open defects remain unresolved", "running"),
                ("fixed, no longer failing", "done"),
                ("PASS (previously failing test fixed)", "done"),
                ("PASS — previously open defect resolved", "done"),
                ("CONFIRMED at 039b438", "done"),
                ("partially complete", "pending"),
            ]
            for index, (status, expected) in enumerate(cases):
                ledger.write_text(table.format(status=status))
                runner.store.update_state(last_turn_end=1.0, last_reply="Checks recorded.")
                before = len(llm.main_requests())
                reply = f"STATUS-CASE-{index}"
                llm.script = [text_step(reply)]
                if expected == "running":
                    assert runner.watchdog_tick({"idle_minutes": 0}) == "idle with unfinished work"
                else:
                    for _ in range(3):
                        assert runner.watchdog_tick({"idle_minutes": 0}) == "no unfinished step in the ledger"
                    assert len(llm.main_requests()) == before
                    runner.submit("Report the current status.")
                end = _wait_event(root, lambda e: e["type"] == "turn_end" and e.get("reply") == reply, 120)
                assert end["status"] == "done", end
                assert read_map(root)["phases"][0]["state"] == expected
                prompt = _focus(llm.main_requests()[before])
                if expected == "done":
                    assert "Done: QA" in prompt and "Not done:" not in prompt
                else:
                    assert f"Not done: QA — {status}" in prompt
                assert ledger.read_text() == table.format(status=status)
            events = _events(root)
            assert len([e for e in events if e["type"] == "watchdog"]) == sum(
                expected == "running" for _, expected in cases)
            assert not [e for e in events if e["type"] == "helper"]
        finally:
            app.shutdown()


@pytest.mark.parametrize("ledger_style", ["hermes", "claude"])
def test_delivery_stays_idle_but_new_work_continues_to_one_qa_job(env, ledger_style):
    release_qa = threading.Event()
    with FakeOpenAIServer([]) as llm:
        _write_config(env["hermes_home"], llm.base_url, lyra_lite={
            # Use the normal result poller, but tick the watchdog ourselves.
            "watchdog": {"enabled": False},
        })
        next_step = llm.next_step

        def gated_step(body):
            step = next_step(body)
            if step.get("wait_for_qa"):
                assert release_qa.wait(90), "QA was not released"
            return step

        llm.next_step = gated_step
        app = Lyra()
        app.start()
        try:
            runner = app.add_project(str(env["home"] / "Progress audit"), create=True)
            root = runner.root
            (root / ".sdlc").mkdir()
            ledger = root / ".sdlc/progress.md"
            delivered = CLAUDE_DELIVERED if ledger_style == "claude" else HERMES_DELIVERED
            ledger.write_text(delivered)
            (root / ".sdlc/project-brain.md").write_text(
                "## Current state\nDevelopment is running.\n## Next actions\nRun QA again.\n")
            runner.store.update_state(last_turn_end=1.0, last_reply="Delivered.")

            # Idle, unpaused and keep-going enabled: the ledger is the only
            # reason this finished project must not start another turn.
            assert runner.snapshot()["engine"] == "hermes"
            for _ in range(8):
                assert runner.watchdog_tick({"idle_minutes": 0}) == "no unfinished step in the ledger"
            assert not llm.main_requests()
            assert not [e for e in _events(root) if e["type"] in {"watchdog", "turn_start", "helper"}]

            llm.script = [text_step("The delivered build is ready.")]
            runner.submit("What is the current status?")
            first = _wait_event(root, lambda e: e["type"] == "turn_end", 120)
            assert first["status"] == "done", first
            assert first["reply"] == "The delivered build is ready."
            prompt = _focus(llm.main_requests()[0])
            assert "Current step: Delivered" in prompt
            assert "Not done:" not in prompt and "Run QA again" not in prompt

            # A later feature is real unfinished work. Let its watchdog turn
            # write implementation, dispatch real background QA, then deliver.
            ledger.write_text(delivered + NEW_FEATURE)
            finished = delivered + NEW_FEATURE + "| Export QA | PASS | Checked |\n| Delivery | delivered | Accepted |\n"

            def write(path, content):
                return tool_step("write_file", {"path": str(path), "content": content})

            goal = "PROGRESS-QA: verify the export feature and record the result."
            dispatch = tool_step("delegate_task", {"goal": goal, "background": True})
            llm.script = [write(root / "export.txt", "export implemented"), dispatch,
                          text_step("NEW-QA-STARTED"), write(ledger, finished), text_step("NEW-FEATURE-DELIVERED")]
            llm.side_scripts = {"PROGRESS-QA": [
                {**write(root / "qa-result.md", "PASS"), "wait_for_qa": True}, text_step("Export QA passed."),
            ]}
            before = len(llm.main_requests())
            assert runner.watchdog_tick({"idle_minutes": 0}) == "idle with unfinished work"
            _wait_event(root, lambda e: e["type"] == "turn_end" and e.get("reply") == "NEW-QA-STARTED", 120)
            prompt = _focus(llm.main_requests()[before])
            assert "Not done: Export development — running" in prompt
            assert "Not done: Export QA — pending" in prompt
            assert "Not done: Development — running" not in prompt
            assert "Not done: Rev 2 build — running" not in prompt
            assert (root / "export.txt").read_text() == "export implemented"
            assert len(runner.helpers()) == 1
            assert runner.watchdog_tick({"idle_minutes": 0}) == "working"
            release_qa.set()
            end = _wait_event(root, lambda e: e["type"] == "turn_end" and e.get("reply") == "NEW-FEATURE-DELIVERED", 120)
            assert end["status"] == "done", end
            assert (root / "qa-result.md").read_text() == "PASS"
            assert ledger.read_text() == finished
            assert read_map(root)["delivery_complete"]
            assert runner.helpers() == []
            events_before = _events(root)
            calls_before = len(llm.main_requests())
            for _ in range(8):
                assert runner.watchdog_tick({"idle_minutes": 0}) == "no unfinished step in the ledger"
            assert len(llm.main_requests()) == calls_before
            assert _events(root) == events_before
            assert len([e for e in events_before if e["type"] == "watchdog"]) == 1
            assert len([e for e in events_before if e["type"] == "helper" and e["event"] == "start"]) == 1
            assert not [e for e in events_before if e["type"] == "turn_end" and e["status"] != "done"], json.dumps(events_before)
        finally:
            release_qa.set()
            app.shutdown()
