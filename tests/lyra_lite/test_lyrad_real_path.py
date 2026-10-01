"""Lyra Lite end to end: real daemon, real Hermes engine, real sockets.

The only fake is the model: a scripted OpenAI-compatible server on a local
port, reached through Hermes' normal custom-provider path.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import yaml

from tests.fakes.fake_openai_server import FakeOpenAIServer, text_step, tool_step

REPO = Path(__file__).resolve().parents[2]
TOKEN = "test-token"
HEADERS = {"x-lyra-token": TOKEN}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    hermes_home = Path(os.environ["HERMES_HOME"])
    hermes_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    for var, value in {
        "GIT_AUTHOR_NAME": "Lyra Test", "GIT_AUTHOR_EMAIL": "lyra@test.invalid",
        "GIT_COMMITTER_NAME": "Lyra Test", "GIT_COMMITTER_EMAIL": "lyra@test.invalid",
    }.items():
        monkeypatch.setenv(var, value)
    return {"home": home, "hermes_home": hermes_home}


def _write_config(hermes_home: Path, base_url: str) -> None:
    config = {
        "model": {"default": "fake-model", "provider": "custom",
                  "base_url": base_url, "api_key": "fake-key"},
        "approvals": {"mode": "manual", "timeout": 60},
        "memory": {"memory_enabled": False, "user_profile_enabled": False},
        "skills": {"creation_nudge_interval": 0},
        "compression": {"enabled": False},
        "display": {"interim_assistant_messages": False},
    }
    (hermes_home / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")


class Daemon:
    def __init__(self, env: dict):
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.env = {**os.environ, "HOME": str(env["home"]),
                    "HERMES_HOME": str(env["hermes_home"])}
        self.proc: subprocess.Popen | None = None

    def start(self) -> "Daemon":
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "lyra_lite", "--no-open", "--port", str(self.port),
             "--token", TOKEN],
            cwd=REPO, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                if httpx.get(f"{self.base}/api/projects", headers=HEADERS, timeout=1).status_code == 200:
                    return self
            except httpx.HTTPError:
                pass
            if self.proc.poll() is not None:
                raise RuntimeError(self.proc.stdout.read().decode(errors="replace"))
            time.sleep(0.2)
        raise TimeoutError("lyrad did not start")

    def kill(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGKILL)
            self.proc.wait(10)

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.kill()

    def post(self, path: str, body: dict) -> httpx.Response:
        return httpx.post(f"{self.base}{path}", json=body, headers=HEADERS, timeout=10)

    def get(self, path: str) -> httpx.Response:
        return httpx.get(f"{self.base}{path}", headers=HEADERS, timeout=10)


def _new_project(daemon: Daemon, env: dict, name: str = "Pocket") -> tuple[str, Path]:
    path = env["home"] / "Lyra Projects" / name
    res = daemon.post("/api/projects", {"path": str(path), "create": True})
    assert res.status_code == 200, res.text
    return res.json()["id"], path


def _events(path: Path) -> list[dict]:
    file = path / ".lyra" / "events.jsonl"
    if not file.exists():
        return []
    return [json.loads(line) for line in file.read_text().splitlines() if line.strip()]


def _wait_event(path: Path, pred, timeout: float = 60) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for evt in _events(path):
            if pred(evt):
                return evt
        time.sleep(0.1)
    raise TimeoutError(f"no matching event; saw {_events(path)}")


def test_reply_streams_over_sse_and_is_saved(env):
    with FakeOpenAIServer([text_step("Hello owner, what shall we build?")]) as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env)
            (path / ".sdlc").mkdir()
            (path / ".sdlc" / "progress.md").write_text("# Progress\n")

            seen: list[dict] = []
            done = threading.Event()

            def follow():
                with httpx.stream("GET", f"{daemon.base}/api/projects/{pid}/stream",
                                  params={"offset": 0, "token": TOKEN}, timeout=None) as res:
                    for line in res.iter_lines():
                        if line.startswith("data: "):
                            evt = json.loads(line[6:])
                            seen.append(evt)
                            if evt["type"] == "turn_end":
                                done.set()
                                return

            reader = threading.Thread(target=follow, daemon=True)
            reader.start()
            assert daemon.post(f"/api/projects/{pid}/messages", {"text": "hi"}).status_code == 200
            assert done.wait(90), [e["type"] for e in seen]

            streamed = "".join(e["text"] for e in seen if e["type"] == "delta")
            assert streamed == "Hello owner, what shall we build?"
            end = seen[-1]
            assert end["status"] == "done"
            assert end["checkpoint"], "turn-end checkpoint should commit the project"

            project = daemon.get(f"/api/projects/{pid}").json()
            assert [m["role"] for m in project["messages"]] == ["user", "assistant"]
            assert project["messages"][1]["content"] == "Hello owner, what shall we build?"
            assert project["running"] is False

            # The model saw Lyra's rules and the project folder.
            system = llm.main_requests()[0]["messages"][0]["content"]
            assert "Lyra" in system and str(path) in system
        finally:
            daemon.stop()


def test_approval_waits_in_inbox_and_runs_in_project_folder(env):
    command = "python3 -c 'open(\"approved.txt\",\"w\").write(\"yes\")'"
    script = [tool_step("terminal", {"command": command}), text_step("Done.")]
    with FakeOpenAIServer(script) as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env)
            daemon.post(f"/api/projects/{pid}/messages", {"text": "make the file"})

            ask = _wait_event(path, lambda e: e["type"] == "inbox")
            item = ask["item"]
            assert item["kind"] == "approval" and "approved.txt" in item["command"]
            assert not (path / "approved.txt").exists()

            inbox = daemon.get(f"/api/projects/{pid}").json()["inbox"]
            assert [i["id"] for i in inbox] == [item["id"]]

            res = daemon.post(f"/api/projects/{pid}/inbox/{item['id']}", {"answer": "once"})
            assert res.status_code == 200, res.text

            end = _wait_event(path, lambda e: e["type"] == "turn_end")
            assert end["status"] == "done"
            assert (path / "approved.txt").read_text() == "yes"
            saved = json.loads((path / ".lyra" / "inbox" / f"{item['id']}.json").read_text())
            assert saved["status"] == "answered" and saved["answer"] == "once"
        finally:
            daemon.stop()


def test_killed_mid_turn_keeps_history_and_recovers(env):
    script = [text_step("First answer."), text_step("never delivered")]
    with FakeOpenAIServer(script) as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        pid, path = _new_project(daemon, env)
        try:
            daemon.post(f"/api/projects/{pid}/messages", {"text": "first"})
            _wait_event(path, lambda e: e["type"] == "turn_end")

            llm.step_delay = 30  # the next model call hangs
            daemon.post(f"/api/projects/{pid}/messages", {"text": "second request"})
            _wait_event(path, lambda e: e["type"] == "turn_start" and e["text"] == "second request")
            time.sleep(1)
        finally:
            daemon.kill()

        daemon = Daemon(env).start()
        try:
            project = daemon.get(f"/api/projects/{pid}").json()
            assert project["running"] is False
            texts = [(m["role"], m["content"]) for m in project["messages"]]
            assert texts[0] == ("user", "first")
            assert texts[1] == ("assistant", "First answer.")
            assert texts[2] == ("user", "second request")
            assert texts[3][0] == "assistant" and "restarted" in texts[3][1]
            assert any(e["type"] == "turn_end" and e["status"] == "lost_on_restart"
                       for e in _events(path))
        finally:
            daemon.stop()


def test_new_projects_are_refused_inside_lyra(env):
    with FakeOpenAIServer([]) as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        try:
            res = daemon.post("/api/projects", {"path": str(REPO / "new-app"), "create": True})
            assert res.status_code == 400
            assert not (REPO / "new-app").exists()
            assert daemon.get("/api/projects").status_code == 200
            assert httpx.get(f"{daemon.base}/api/projects", timeout=5).status_code == 401
        finally:
            daemon.stop()
