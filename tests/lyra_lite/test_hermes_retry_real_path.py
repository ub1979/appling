"""Retry a real Hermes turn that fails after starting a real QA worker.

The local model server scripts both the provider error and a repeated dispatch;
the daemon, conversation, tools and background workers are real.
"""
import json
import threading

import pytest

from tests.fakes.fake_openai_server import FakeOpenAIServer, _first_user_text, text_step, tool_step
from tests.lyra_lite.test_lyrad_real_path import (
    Daemon, _events, _new_project, _wait_event, _write_config, env,  # noqa: F401
)


class FailingHermes(FakeOpenAIServer):
    def __init__(self):
        self.fail = False
        self.entered, self.release = threading.Event(), threading.Event()
        super().__init__([])

    def next_step(self, body):
        if self.fail and body.get("tools") and "QA-WORKER" not in _first_user_text(body):
            with self._lock:
                self.requests.append(body)
            return text_step("FAIL-REQUEST")
        step = super().next_step(body)
        if "QA-WORKER" in _first_user_text(body) and step.get("tool") == "write_file":
            self.entered.set()
            assert self.release.wait(60), "QA worker was not released"
        if step.get("text") == "FAIL-REQUEST":
            self.fail = True
        return step

    def _handler(self):
        parent = super()._handler()

        class Handler(parent):
            def _stream(self, step):
                if step.get("text") == "FAIL-REQUEST":
                    self._send(400, json.dumps({"error": {
                        "type": "invalid_request_error", "message": "Controlled failure after dispatch"}}))
                else:
                    super()._stream(step)

            def _send(self, code, body):
                if code == 200 and "FAIL-REQUEST" in body:
                    code, body = 400, json.dumps({"error": {
                        "type": "invalid_request_error", "message": "Controlled failure after dispatch"}})
                super()._send(code, body)
        return Handler


def _parent_requests(llm):
    return [r for r in llm.main_requests() if "QA-WORKER" not in _first_user_text(r)
            and "OTHER-WORKER" not in _first_user_text(r)]


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("reload_engine", [False, True])
def test_retry_remembers_running_qa_and_refuses_duplicate_but_allows_other_work(env, batch, reload_engine):
    with FailingHermes() as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env, "QA Retry")
            target = path / "qa-result.md"
            goal = f"QA-WORKER: independently verify the repair and write PASS to {target}."
            task = {"goal": goal, "context": "Build profile: reusable"}
            args = {"tasks": [task]} if batch else task
            llm.script = [tool_step("delegate_task", args), text_step("FAIL-REQUEST")]
            llm.side_scripts = {"QA-WORKER": [
                tool_step("write_file", {"path": str(target), "content": "PASS"}), text_step("QA PASS")]}
            daemon.post(f"/api/projects/{pid}/messages", {"text": "start independent QA"})
            _wait_event(path, lambda e: e["type"] == "turn_end" and e.get("status") == "error", 45)
            assert llm.entered.wait(10)
            snapshot = daemon.get(f"/api/projects/{pid}").json()
            assert len(snapshot["helpers"]) == 1
            original_id = snapshot["helpers"][0]["id"]
            history = [json.loads(line) for line in (path / ".lyra/messages.jsonl").read_text().splitlines()]
            assert goal in json.dumps(history) and original_id in json.dumps(history)
            dispatches = [m for m in history if m.get("role") == "tool" and original_id in str(m.get("content"))]
            assert len(dispatches) == 1
            call_ids = {tc["id"] for m in history for tc in m.get("tool_calls", [])}
            assert dispatches[0]["tool_call_id"] in call_ids
            failed_request = _parent_requests(llm)[-1]

            llm.fail = False
            llm.script = [tool_step("delegate_task", args, call_id="retry-qa"), text_step("QA STILL RUNNING")]
            if reload_engine:
                # The existing model-settings path rebuilds the adapter. Its
                # duplicate guard must restore dispatches from saved history.
                assert daemon.post("/api/settings/effort", {"effort": "high"}).status_code == 200
            before = len(_parent_requests(llm))
            daemon.post(f"/api/projects/{pid}/messages", {"text": "try now"})
            _wait_event(path, lambda e: e["type"] == "turn_end" and e.get("reply") == "QA STILL RUNNING")
            retry = _parent_requests(llm)[before]
            if not reload_engine:
                assert retry["messages"][:-1] == failed_request["messages"]
            assert "already running" in retry["messages"][-1]["content"]
            assert original_id in retry["messages"][-1]["content"]
            duplicate_reply = next(m for m in _parent_requests(llm)[before + 1]["messages"]
                                   if m.get("tool_call_id") == "retry-qa")
            assert json.loads(duplicate_reply["content"])["status"] == "already_running"
            assert daemon.get(f"/api/projects/{pid}").json()["helpers"] == snapshot["helpers"]

            # Parallel work with a different task still runs normally.
            other = path / "other.txt"
            llm.script = [tool_step("delegate_task", {"goal": f"OTHER-WORKER: write {other}"}, call_id="other"), text_step("OTHER STARTED"), text_step("OTHER DONE")]
            llm.side_scripts["OTHER-WORKER"] = [tool_step("write_file", {"path": str(other), "content": "done"}), text_step("Other done")]
            daemon.post(f"/api/projects/{pid}/messages", {"text": "do unrelated work"})
            _wait_event(path, lambda e: e["type"] == "turn_end" and e.get("reply") == "OTHER DONE")
            assert other.read_text() == "done" and not target.exists()
            assert len(daemon.get(f"/api/projects/{pid}").json()["helpers"]) == 1

            llm.script = [text_step("QA COMPLETE")]
            llm.release.set()
            _wait_event(path, lambda e: e["type"] == "turn_end" and e.get("reply") == "QA COMPLETE")
            assert target.read_text() == "PASS"
            assert daemon.get(f"/api/projects/{pid}").json()["helpers"] == []
            events = _events(path)
            assert len([e for e in events if e["type"] == "helper" and e["event"] == "start" and e.get("goal") == goal]) == 1
            assert len([e for e in events if e["type"] == "helper" and e["event"] == "reported" and e.get("subagent_id") == original_id]) == 1

            # A later legitimate retest is allowed after completion.
            llm.script = [tool_step("delegate_task", args, call_id="later-retest"), text_step("RETEST STARTED"), text_step("RETEST COMPLETE")]
            llm.side_scripts["QA-WORKER"] = [text_step("New retest passed")]
            daemon.post(f"/api/projects/{pid}/messages", {"text": "retest the new change"})
            _wait_event(path, lambda e: e["type"] == "turn_end" and e.get("reply") == "RETEST COMPLETE")
            assert len([e for e in _events(path) if e["type"] == "helper" and e["event"] == "start" and e.get("goal") == goal]) == 2
        finally:
            llm.release.set()
            daemon.stop()
