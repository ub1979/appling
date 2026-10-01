"""The Claude engine end to end: real daemon, real Claude Code CLI (bundled
with the Claude Agent SDK), real sockets; only the model is scripted."""

from __future__ import annotations

import json
import time

import pytest
import yaml

pytest.importorskip("claude_agent_sdk")

from tests.fakes.fake_anthropic_server import FakeAnthropicServer, text_step, tool_step  # noqa: E402
from tests.fakes.fake_openai_server import FakeOpenAIServer  # noqa: E402
from tests.fakes.fake_openai_server import text_step as openai_text  # noqa: E402
from tests.lyra_lite.test_lyrad_real_path import (  # noqa: E402
    Daemon, _events, _new_project, _wait_event, _write_config, env,  # noqa: F401
)


def _use_claude(daemon, pid, claude_url):
    res = daemon.post(f"/api/projects/{pid}/settings", {
        "engine": "claude",
        "claude": {"base_url": claude_url, "auth_token": "fake", "model": "claude-fake"},
    })
    assert res.status_code == 200, res.text
    assert res.json()["engine"] == "claude"
    assert "auth_token" not in res.json()["claude"]


def test_claude_engine_streams_edits_and_runs_safe_commands(env):
    with FakeOpenAIServer([]) as hermes_llm, FakeAnthropicServer([]) as claude:
        _write_config(env["hermes_home"], hermes_llm.base_url)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env)
            (path / ".sdlc").mkdir()
            (path / ".sdlc" / "progress.md").write_text("# Progress\n")
            claude.script = [
                tool_step("Write", {"file_path": str(path / "hello.txt"), "content": "hi"}),
                tool_step("Bash", {"command": "ls hello.txt > listing.txt"}),
                text_step("Wrote hello.txt and listed it."),
            ]
            _use_claude(daemon, pid, claude.base_url)
            daemon.post(f"/api/projects/{pid}/messages", {"text": "make hello.txt"})
            end = _wait_event(path, lambda e: e["type"] == "turn_end", 120)

            assert end["status"] == "done", end
            assert end["reply"] == "Wrote hello.txt and listed it."
            assert (path / "hello.txt").read_text() == "hi"
            assert (path / "listing.txt").read_text().strip() == "hello.txt"
            assert end["checkpoint"]
            assert not [e for e in _events(path) if e["type"] == "inbox"]
            streamed = "".join(e["text"] for e in _events(path) if e["type"] == "delta")
            assert streamed.endswith("Wrote hello.txt and listed it.")
            tools = [e["name"] for e in _events(path) if e["type"] == "tool" and e["phase"] == "start"]
            assert tools == ["write_file", "terminal"]
            system = str(claude.main_requests()[0]["system"])
            assert "Running on Claude Code" in system and str(path) in system
        finally:
            daemon.stop()


def test_claude_engine_asks_before_risky_commands(env):
    with FakeOpenAIServer([]) as hermes_llm, FakeAnthropicServer([]) as claude:
        _write_config(env["hermes_home"], hermes_llm.base_url)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env)
            claude.script = [
                tool_step("Bash", {"command": "python3 -c 'open(\"risky.txt\",\"w\").write(\"ok\")'"}),
                text_step("Done."),
            ]
            _use_claude(daemon, pid, claude.base_url)
            daemon.post(f"/api/projects/{pid}/messages", {"text": "do the risky thing"})
            item = _wait_event(path, lambda e: e["type"] == "inbox", 120)["item"]
            assert item["kind"] == "approval" and "risky.txt" in item["command"]
            assert not (path / "risky.txt").exists()
            daemon.post(f"/api/projects/{pid}/inbox/{item['id']}", {"answer": "once"})
            end = _wait_event(path, lambda e: e["type"] == "turn_end", 120)
            assert end["status"] == "done"
            assert (path / "risky.txt").read_text() == "ok"
        finally:
            daemon.stop()


def test_claude_engine_agents_show_as_helpers(env):
    with FakeOpenAIServer([]) as hermes_llm, FakeAnthropicServer([]) as claude:
        _write_config(env["hermes_home"], hermes_llm.base_url)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env)
            target = path / "agent.txt"
            claude.script = [
                tool_step("Agent", {"description": "Write agent.txt",
                                    "prompt": f"HELPER-C write {target}",
                                    "subagent_type": "general-purpose"}),
                text_step("The agent wrote agent.txt."),
            ]
            claude.side_scripts = {"HELPER-C": [
                tool_step("Write", {"file_path": str(target), "content": "from agent"}),
                text_step("Wrote it."),
            ]}
            _use_claude(daemon, pid, claude.base_url)
            daemon.post(f"/api/projects/{pid}/messages", {"text": "use an agent"})
            end = _wait_event(path, lambda e: e["type"] == "turn_end", 120)
            assert end["reply"] == "The agent wrote agent.txt."
            assert target.read_text() == "from agent"
            helper = [e for e in _events(path) if e["type"] == "helper"]
            assert [h["event"] for h in helper if h["event"] != "tool"] == ["start", "complete"]
            assert helper[-1]["status"] == "completed"
            assert daemon.get(f"/api/projects/{pid}").json()["helpers"] == []
        finally:
            daemon.stop()


def test_switching_engines_mid_chat_carries_the_conversation(env):
    with FakeOpenAIServer([openai_text("Hermes says the plan is ready.")]) as hermes_llm, \
            FakeAnthropicServer([text_step("Claude continues the plan.")]) as claude:
        _write_config(env["hermes_home"], hermes_llm.base_url)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env)
            daemon.post(f"/api/projects/{pid}/messages", {"text": "make a plan"})
            _wait_event(path, lambda e: e["type"] == "turn_end")
            _use_claude(daemon, pid, claude.base_url)
            daemon.post(f"/api/projects/{pid}/messages", {"text": "continue"})
            end = _wait_event(path, lambda e: e["type"] == "turn_end" and e["reply"].startswith("Claude"), 120)
            assert end["status"] == "done"
            first = str(claude.main_requests()[0]["messages"])
            assert "Hermes says the plan is ready." in first
            shown = [m["content"] for m in daemon.get(f"/api/projects/{pid}").json()["messages"]]
            assert shown == ["make a plan", "Hermes says the plan is ready.", "continue",
                             "Claude continues the plan."]
        finally:
            daemon.stop()


def test_claude_engine_without_a_key_explains_what_to_do(env):
    with FakeOpenAIServer([]) as hermes_llm:
        _write_config(env["hermes_home"], hermes_llm.base_url)
        daemon = Daemon(env)
        daemon.env.pop("ANTHROPIC_API_KEY", None)
        daemon.start()
        try:
            pid, path = _new_project(daemon, env)
            assert daemon.post("/api/settings", {"claude": {"route": "api"}}).json()["claude"]["route"] == "api"
            assert daemon.post(f"/api/projects/{pid}/settings", {"engine": "claude"}).status_code == 200
            daemon.post(f"/api/projects/{pid}/messages", {"text": "hello"})
            end = _wait_event(path, lambda e: e["type"] == "turn_end", 60)
            assert end["status"] == "error"
            assert "ANTHROPIC_API_KEY" in end["error"] and "Your Claude plan" in end["error"]
            time.sleep(0.5)
        finally:
            daemon.stop()


def test_lyra_wide_engine_setting_moves_projects_unless_they_chose_their_own(env):
    hermes_replies = [openai_text("Hermes here."), openai_text("Hermes again.")]
    with FakeOpenAIServer(hermes_replies) as hermes_llm, FakeAnthropicServer([text_step("Claude here.")]) as claude:
        _write_config(env["hermes_home"], hermes_llm.base_url)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env)
            assert daemon.get("/api/settings").json()["engine"] == "hermes"
            daemon.post(f"/api/projects/{pid}/messages", {"text": "one"})
            _wait_event(path, lambda e: e["type"] == "turn_end" and e["reply"] == "Hermes here.")

            saved = daemon.post("/api/settings", {"engine": "claude", "claude": {
                "base_url": claude.base_url, "auth_token": "fake", "model": "claude-fake"}}).json()
            assert saved["engine"] == "claude" and saved["claude"]["has_token"] is True
            assert "auth_token" not in saved["claude"]
            assert daemon.get(f"/api/projects/{pid}").json()["engine"] == "claude"
            daemon.post(f"/api/projects/{pid}/messages", {"text": "two"})
            _wait_event(path, lambda e: e["type"] == "turn_end" and e["reply"] == "Claude here.")

            # This project picks Hermes for itself; Lyra's default stays Claude.
            assert daemon.post(f"/api/projects/{pid}/settings", {"engine": "hermes"}).status_code == 200
            daemon.post(f"/api/projects/{pid}/messages", {"text": "three"})
            _wait_event(path, lambda e: e["type"] == "turn_end" and e["reply"] == "Hermes again.")
            assert daemon.get("/api/settings").json()["engine"] == "claude"
            back = daemon.post(f"/api/projects/{pid}/settings", {"engine": "default"}).json()
            assert back["engine"] == "claude" and back["engine_override"] is False

            config = yaml.safe_load((env["hermes_home"] / "config.yaml").read_text())
            assert config["lyra_lite"]["engine"] == "claude"
            assert config["model"]["base_url"] == hermes_llm.base_url  # Hermes model untouched
        finally:
            daemon.stop()


def test_model_list_and_choice_use_hermes_own_settings(env):
    with FakeOpenAIServer([]) as hermes_llm:
        _write_config(env["hermes_home"], hermes_llm.base_url)
        daemon = Daemon(env).start()
        try:
            options = daemon.get("/api/settings/models").json()
            assert isinstance(options["providers"], list)
            assert daemon.get("/api/settings").json()["hermes"]["model"] == "fake-model"
            assert daemon.post("/api/settings/model", {"provider": "", "model": ""}).status_code == 400
        finally:
            daemon.stop()


def test_claude_engine_loads_lyra_playbooks_as_native_skills(env):
    with FakeOpenAIServer([]) as hermes_llm, FakeAnthropicServer([]) as claude:
        _write_config(env["hermes_home"], hermes_llm.base_url)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env)
            claude.script = [tool_step("Skill", {"skill": "ultimate-builder:req-engineer"}),
                             text_step("Who will use the app?")]
            _use_claude(daemon, pid, claude.base_url)
            daemon.post(f"/api/projects/{pid}/messages", {"text": "I want a gym tracker"})
            end = _wait_event(path, lambda e: e["type"] == "turn_end", 120)
            assert end["status"] == "done"
            first = claude.main_requests()[0]
            assert any(t.get("name") == "Skill" for t in first.get("tools", []))
            assert "ultimate-builder:req-engineer" in json.dumps(first)
            # The requirements playbook itself came back to the model.
            assert "decide for me" in json.dumps(claude.main_requests()[1]["messages"]).lower()
            assert not [e for e in _events(path) if e["type"] == "inbox"]  # Skill needs no approval
        finally:
            daemon.stop()
