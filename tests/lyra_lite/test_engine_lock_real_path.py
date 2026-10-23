"""Project engine ownership through real daemons, adapters and worker tools.

Only model replies are scripted; project state and global config are isolated.
"""
from __future__ import annotations

import json
import threading

import pytest

pytest.importorskip("claude_agent_sdk")

from tests.fakes.fake_anthropic_server import FakeAnthropicServer, _flat
from tests.fakes.fake_anthropic_server import text_step as ct, tool_step as cc
from tests.fakes.fake_openai_server import FakeOpenAIServer, _first_user_text
from tests.fakes.fake_openai_server import text_step as ht, tool_step as hc
from tests.lyra_lite.test_lyrad_real_path import (
    Daemon, _events, _new_project, _wait_event, _write_config, env,  # noqa: F401
)


class HeldHermes(FakeOpenAIServer):
    def __init__(self):
        self.entered, self.release = threading.Event(), threading.Event()
        super().__init__([])

    def next_step(self, body):
        step = super().next_step(body)
        if "QA-WORKER" in _first_user_text(body) and step.get("tool") == "write_file":
            self.entered.set()
            assert self.release.wait(60), "QA worker was not released"
        return step


class HeldClaude(FakeAnthropicServer):
    def __init__(self):
        self.entered, self.release = threading.Event(), threading.Event()
        super().__init__([])

    def next_step(self, body):
        step = super().next_step(body)
        first = _flat((body.get("messages") or [{}])[0].get("content"))
        if "QA-WORKER" in first and step.get("tool") == "Write":
            self.entered.set()
            assert self.release.wait(60), "QA worker was not released"
        return step


def _config(env, hermes, claude, engine):
    _write_config(env["hermes_home"], hermes.base_url, lyra_lite={
        "engine": engine, "claude": {
            "route": "custom", "base_url": claude.base_url,
            "auth_token": "fake", "model": "claude-fake",
        },
    })


def _say(daemon, pid, path, text, reply):
    assert daemon.post(f"/api/projects/{pid}/messages", {"text": text}).status_code == 200
    return _wait_event(path, lambda e: e["type"] == "turn_end" and e.get("reply") == reply, 60)


@pytest.mark.parametrize("engine", ["hermes", "claude"])
def test_engine_is_fixed_before_first_turn_through_new_chat_and_restart(env, engine):
    other = "claude" if engine == "hermes" else "hermes"
    with FakeOpenAIServer([]) as hermes, FakeAnthropicServer([]) as claude:
        _config(env, hermes, claude, engine)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env, "Original")
            assert daemon.get(f"/api/projects/{pid}").json()["engine_locked"]
            assert daemon.post("/api/settings", {"engine": other}).status_code == 200
            for choice in (other, "default", "", None):
                rejected = daemon.post(f"/api/projects/{pid}/settings", {"engine": choice})
                assert rejected.status_code == 409 and "locked" in rejected.json()["detail"]
            assert daemon.post(f"/api/projects/{pid}/settings", {"engine": "unknown"}).status_code == 400
            assert daemon.post(f"/api/projects/{pid}/settings", {"engine": engine}).status_code == 200

            current, following = (hermes, claude) if engine == "hermes" else (claude, hermes)
            step, other_step = (ht, ct) if engine == "hermes" else (ct, ht)
            current.script = [step("ORIGINAL"), step("CONTINUED"), step("NEW-CHAT"), step("REOPENED")]
            following.script = [other_step("NEW-PROJECT")]
            _say(daemon, pid, path, "remember this project", "ORIGINAL")
            new_pid, new_path = _new_project(daemon, env, "Following")
            assert daemon.get(f"/api/projects/{new_pid}").json()["engine"] == other
            _say(daemon, new_pid, new_path, "new project", "NEW-PROJECT")
            _say(daemon, pid, path, "continue", "CONTINUED")
            assert "ORIGINAL" in json.dumps(current.main_requests()[-1]["messages"])
            assert daemon.post(f"/api/projects/{pid}/new-chat", {}).status_code == 200
            _say(daemon, pid, path, "new chat", "NEW-CHAT")
            daemon.stop()
            daemon = Daemon(env).start()
            assert daemon.get(f"/api/projects/{pid}").json()["engine"] == engine
            assert daemon.get(f"/api/projects/{new_pid}").json()["engine"] == other
            _say(daemon, pid, path, "reopen", "REOPENED")
            saved = json.loads((path / ".lyra/state.json").read_text())
            assert saved["engine"] == engine and saved["engine_locked"]
        finally:
            daemon.stop()


@pytest.mark.parametrize("engine", ["hermes", "claude"])
def test_global_engine_change_keeps_qa_visible_and_delivers_one_completion(env, engine):
    other = "claude" if engine == "hermes" else "hermes"
    with HeldHermes() as hermes, HeldClaude() as claude:
        _config(env, hermes, claude, engine)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env, "QA lock")
            target = path / "qa-result.md"
            goal = f"QA-WORKER: independently verify the repaired feature; write PASS to {target}."
            hermes.script = [hc("delegate_task", {"goal": goal, "context": "Build profile: reusable.",
                                                   "background": True}), ht("STARTED"), ht("STILL-RUNNING"), ht("QA-COMPLETE")]
            hermes.side_scripts = {"QA-WORKER": [hc("write_file", {"path": str(target), "content": "PASS"}), ht("QA PASS")]}
            claude.script = [cc("Agent", {"description": "Independent QA", "subagent_type": "general-purpose",
                                           "prompt": goal + " Build profile: reusable."}), ct("STARTED"),
                             ct("STILL-RUNNING"), ct("QA-COMPLETE")]
            claude.side_scripts = {"QA-WORKER": [cc("Write", {"file_path": str(target), "content": "PASS"}), ct("QA PASS")]}
            current, unused = (hermes, claude) if engine == "hermes" else (claude, hermes)
            _say(daemon, pid, path, "start QA", "STARTED")
            assert current.entered.wait(15)
            before = daemon.get(f"/api/projects/{pid}").json()
            assert len(before["helpers"]) == 1
            assert daemon.post(f"/api/projects/{pid}/settings", {"engine": other}).status_code == 409
            assert daemon.post("/api/settings", {"engine": other}).status_code == 200
            _say(daemon, pid, path, "try now", "STILL-RUNNING")
            after = daemon.get(f"/api/projects/{pid}").json()
            assert after["engine"] == engine and after["helpers"] == before["helpers"]
            assert not target.exists() and not unused.main_requests()
            assert "STARTED" in json.dumps(current.main_requests()[-1]["messages"])
            current.release.set()
            _wait_event(path, lambda e: e["type"] == "turn_end" and e.get("reply") == "QA-COMPLETE", 60)
            assert target.read_text() == "PASS"
            assert daemon.get(f"/api/projects/{pid}").json()["helpers"] == []
            events = _events(path)
            assert len([e for e in events if e["type"] == "helper" and e["event"] == "start"]) == 1
            assert len([e for e in events if e["type"] == "turn_start" and e.get("kind") == "helper_done"]) == 1
        finally:
            hermes.release.set()
            claude.release.set()
            daemon.stop()
