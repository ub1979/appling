"""Real HTTP/SSE daemon + Codex engine + executable protocol peer, no Hermes."""
import json
import os
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
HEADERS = {"x-lyra-token": "codex-test"}


def wait_for(read, predicate, seconds=10):
    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        last = read()
        if predicate(last):
            return last
        time.sleep(.03)
    raise AssertionError(f"Timed out; last state: {last}")


class Daemon:
    def __init__(self, env):
        self.env = env
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.proc = None
    def start(self):
        self.proc = subprocess.Popen([sys.executable, "-m", "lyra_lite", "--no-open", "--port", str(self.port), "--token", "codex-test"],
                                     cwd=REPO, env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        def probe():
            try:
                return self.get("/api/projects").status_code
            except httpx.HTTPError:
                return None
        wait_for(probe, lambda status: status == 200)
        return self
    def get(self, path):
        return httpx.get(self.url + path, headers=HEADERS, timeout=5)
    def post(self, path, body):
        return httpx.post(self.url + path, headers=HEADERS, json=body, timeout=5)
    def stop(self):
        if self.proc and self.proc.poll() is None:
            # The OS test guard intentionally blocks unrelated signals. This is
            # our exact Popen child; communicate a normal daemon shutdown.
            self.proc.terminate()
            self.proc.wait(timeout=10)


# These tests own real daemon children and must deliver termination signals.
pytestmark = pytest.mark.live_system_guard_bypass


@pytest.fixture
def daemon(tmp_path, monkeypatch):
    home = tmp_path / "owner"
    home.mkdir()
    apphome = tmp_path / "appling"
    apphome.mkdir()
    (apphome / "settings.json").write_text(json.dumps({"model": "fake-model"}))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = REPO / "tests/fakes/fake_codex_app_server.py"
    wrapper = bin_dir / "codex"
    wrapper.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(fake))}\n")
    wrapper.chmod(0o755)
    env = {**os.environ, "HOME": str(home), "APPLING_HOME": str(apphome),
           "FAKE_CODEX_STATE": str(tmp_path / "peer-state.json"), "FAKE_CODEX_LOG": str(tmp_path / "peer-log.jsonl"),
           "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]}
    instance = Daemon(env).start()
    yield instance, home
    instance.stop()


def new_project(daemon, home):
    root = home / "project"
    response = daemon.post("/api/projects", {"path": str(root), "create": True})
    assert response.status_code == 200, response.text
    pid = response.json()["id"]
    wait_for(lambda: daemon.get(f"/api/projects/{pid}").json(), lambda s: not s["running"])
    return pid, root


def test_codex_settings_real_turn_and_sse(daemon):
    app, home = daemon
    pid, root = new_project(app, home)
    settings = app.get("/api/settings").json()
    assert settings["engine"] == "codex" and "hermes" not in settings
    assert app.get("/api/settings/models").json()["providers"][0]["models"] == ["fake-model"]
    assert app.post("/api/settings/model", {"provider": "anthropic", "model": "no"}).status_code == 400
    response = app.post(f"/api/projects/{pid}/messages", {"text": "hello"})
    assert response.status_code == 200
    state = wait_for(lambda: app.get(f"/api/projects/{pid}").json(), lambda s: not s["running"] and not s["queue"])
    assert state["engine"] == "codex"
    assert any(m["content"] == "Hello from native Codex" for m in state["messages"])
    with httpx.stream("GET", app.url + f"/api/projects/{pid}/stream", params={"offset": 0}, headers=HEADERS, timeout=5) as stream:
        assert stream.status_code == 200
        seen = []
        for line in stream.iter_lines():
            if line.startswith("data: "):
                event = json.loads(line[6:]); seen.append(event)
                if event.get("type") == "turn_end":
                    break
        assert any(e.get("type") == "delta" for e in seen)
    assert not (home / ".hermes").exists()


def test_stop_denies_real_native_approval(daemon):
    app, home = daemon
    pid, root = new_project(app, home)
    assert app.post(f"/api/projects/{pid}/messages", {"text": "approval"}).status_code == 200
    state = wait_for(lambda: app.get(f"/api/projects/{pid}").json(), lambda s: bool(s["inbox"]))
    assert state["inbox"][0]["kind"] == "approval"
    assert app.post(f"/api/projects/{pid}/stop", {}).status_code == 200
    state = wait_for(lambda: app.get(f"/api/projects/{pid}").json(), lambda s: not s["running"])
    assert state["paused"] and state["inbox"] == []
    log = Path(app.env["FAKE_CODEX_LOG"]).read_text()
    assert '"decision": "decline"' in log and '"method": "turn/interrupt"' in log


def test_review_survives_daemon_restart_without_automatic_approval(daemon):
    app, home = daemon
    pid, root = new_project(app, home)
    (root / "prototypes").mkdir()
    (root / "prototypes/index.html").write_text("<button>Try</button>")
    payload = {"tool": "clarify", "arguments": {"question": "Review this prototype", "choices": ["Approve prototype", "Request changes"]}}
    assert app.post(f"/api/projects/{pid}/messages", {"text": "tool " + json.dumps(payload)}).status_code == 200
    state = wait_for(lambda: app.get(f"/api/projects/{pid}").json(), lambda s: bool(s["inbox"]))
    item = state["inbox"][0]
    assert item["kind"] == "prototype"
    app.stop()
    app.start()
    state = app.get(f"/api/projects/{pid}").json()
    assert state["review_recovery"]["id"] == item["id"]
    response = app.post(f"/api/projects/{pid}/review/reopen", {"item_id": item["id"]})
    assert response.status_code == 200, response.text
    saved = json.loads((root / ".lyra/state.json").read_text())
    assert not saved.get("prototype_approved")
