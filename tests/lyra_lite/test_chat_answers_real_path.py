"""Picked feedback reaches the model through the real daemon and clarify tool."""
import json
import threading

import pytest

from lyra_lite.review import PROTOTYPE_CHOICES
from tests.fakes.fake_openai_server import FakeOpenAIServer, text_step, tool_step
from tests.lyra_lite.test_chat_answers import FEEDBACK
from tests.lyra_lite.test_lyrad_real_path import (
    Daemon, _new_project, _wait_event, _write_config, env,  # noqa: F401
)


class GatedQuestion(FakeOpenAIServer):
    def __init__(self, script, gated):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.gated = gated
        super().__init__(script)

    def next_step(self, body):
        step = super().next_step(body)
        if step.get("tool") == "clarify" and self.gated:
            self.entered.set()
            assert self.release.wait(30), "test did not release the question"
        return step


@pytest.mark.parametrize("kind,early", [("question", False), ("question", True), ("prototype", False)])
def test_main_composer_feedback_reaches_active_clarify(env, kind, early):
    choices = list(PROTOTYPE_CHOICES) if kind == "prototype" else []
    with GatedQuestion([
        tool_step("clarify", {"question": "What should change?", "choices": choices}),
        text_step("Picked feedback received."),
    ], gated=early) as llm:
        _write_config(env["hermes_home"], llm.base_url, lyra_lite={"watchdog": {"enabled": False}})
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env, "Picked prototype")
            (path / "prototypes").mkdir()
            (path / "prototypes/index.html").write_text('<select id="dateMeaning"><option>Order date</option></select>')
            prefix = f"/api/projects/{pid}"
            assert daemon.post(prefix + "/messages", {"text": "Review my prototype"}).is_success
            if early:
                assert llm.entered.wait(15)
                response = daemon.post(prefix + "/messages", {"text": FEEDBACK})
                assert "queued" in response.json()
                llm.release.set()
            else:
                item = _wait_event(path, lambda e: e["type"] == "inbox" and e["item"]["kind"] == kind)["item"]
                response = daemon.post(prefix + "/messages", {"text": FEEDBACK})
                assert response.json() == {"answered": item["id"]}
            _wait_event(path, lambda e: e["type"] == "turn_end" and e.get("reply") == "Picked feedback received.", 30)
            snapshot = daemon.get(prefix).json()
            assert snapshot["queue"] == [] and snapshot["inbox"] == []
            assert any(FEEDBACK in m["content"] for m in snapshot["messages"] if m["role"] == "user")
            requests = llm.main_requests()
            result = next(m for m in requests[-1]["messages"] if m.get("role") == "tool" and m.get("tool_call_id") == "call_1")
            answer = json.loads(result["content"])["user_response"]
            assert answer == ("Request changes\n\nOwner feedback:\n" if kind == "prototype" else "") + FEEDBACK
            # The reply remains a tool result in the existing conversation;
            # it does not inject a synthetic user turn or rewrite its prefix.
            assert requests[-1]["messages"][:len(requests[0]["messages"])] == requests[0]["messages"]
            if kind == "prototype":
                state = json.loads((path / ".lyra/state.json").read_text())
                assert not state.get("prototype_approved")
                assert state.get("prototype_needs_changes")
        finally:
            llm.release.set()
            daemon.stop()
