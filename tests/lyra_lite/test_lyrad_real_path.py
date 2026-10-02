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
import shutil
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


def _write_config(hermes_home: Path, base_url: str, **extra) -> None:
    config = {
        "model": {"default": "fake-model", "provider": "custom",
                  "base_url": base_url, "api_key": "fake-key"},
        "approvals": {"mode": "manual", "timeout": 60},
        "memory": {"memory_enabled": False, "user_profile_enabled": False},
        "skills": {"creation_nudge_interval": 0},
        "compression": {"enabled": False},
        "display": {"interim_assistant_messages": False},
        **extra,
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


@pytest.mark.parametrize("batch", [False, True], ids=["single", "parallel-batch"])
def test_agents_risky_command_waits_in_inbox_and_runs_in_project_folder(env, batch):
    command = "python3 -c 'open(\"approved.txt\",\"w\").write(\"yes\")'"
    call = ({"tasks": [{"goal": "HELPER-AP run the setup script"}, {"goal": "HELPER-OK say hello"}], "background": True}
            if batch else {"goal": "HELPER-AP run the setup script", "background": True})
    parent = [tool_step("delegate_task", call), text_step("An agent is on it."), text_step("Done.")]
    helper = [tool_step("terminal", {"command": command}, "call_ap"), text_step("Ran it.")]
    sides = {"HELPER-AP": helper, "HELPER-OK": [text_step("Hello.")]}
    with FakeOpenAIServer(parent, side_scripts=sides) as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env)
            daemon.post(f"/api/projects/{pid}/messages", {"text": "make the file"})

            ask = _wait_event(path, lambda e: e["type"] == "inbox", 90)
            item = ask["item"]
            assert item["kind"] == "approval" and "approved.txt" in item["command"]
            assert not (path / "approved.txt").exists()

            inbox = daemon.get(f"/api/projects/{pid}").json()["inbox"]
            assert [i["id"] for i in inbox] == [item["id"]]

            res = daemon.post(f"/api/projects/{pid}/inbox/{item['id']}", {"answer": "once"})
            assert res.status_code == 200, res.text

            report = _wait_event(path, lambda e: e["type"] == "turn_start" and e["kind"] == "helper_done", 90)
            _wait_event(path, lambda e: e["type"] == "turn_end" and e["turn"] == report["turn"], 60)
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


def test_background_helper_reports_back_as_a_new_turn(env):
    def run(path: Path):
        target = path / "hello.txt"
        script = [
            tool_step("delegate_task", {"goal": f"HELPER-1 write the word hello into {target}",
                                        "background": True}),
            text_step("An agent is on it."),
            text_step("The agent finished: hello.txt is ready."),
        ]
        helper = [tool_step("write_file", {"path": str(target), "content": "hello"}, "call_h1"),
                  text_step("Wrote hello.txt")]
        return script, {"HELPER-1": helper}

    with FakeOpenAIServer([]) as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env)
            (path / ".sdlc").mkdir()
            (path / ".sdlc" / "progress.md").write_text("# Progress\n")
            llm.script, llm.side_scripts = run(path)

            daemon.post(f"/api/projects/{pid}/messages", {"text": "please make hello.txt"})
            report = _wait_event(path, lambda e: e["type"] == "turn_start" and e["kind"] == "helper_done", 120)
            end = _wait_event(path, lambda e: e["type"] == "turn_end" and e["turn"] == report["turn"], 60)

            assert (path / "hello.txt").read_text() == "hello"
            assert end["reply"] == "The agent finished: hello.txt is ready."
            kinds = {e.get("event") for e in _events(path) if e["type"] == "helper"}
            assert {"start", "complete"} <= kinds, kinds
            log = subprocess.run(["git", "log", "--format=%s"], cwd=path, capture_output=True,
                                 text=True).stdout
            assert "checkpoint" in log.lower()

            project = daemon.get(f"/api/projects/{pid}").json()
            assert project["helpers"] == []
            assert project["messages"][-1]["content"] == "The agent finished: hello.txt is ready."
        finally:
            daemon.stop()


def test_helper_cut_off_by_a_restart_is_still_reported(env):
    script = [
        tool_step("delegate_task", {"goal": "HELPER-2 slow job", "background": True}),
        text_step("An agent is on it."),
        text_step("That agent was cut off; I will redo its job."),
    ]
    hang = {**text_step("too late"), "delay": 60}
    with FakeOpenAIServer(script, side_scripts={"HELPER-2": [hang]}) as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        pid, path = _new_project(daemon, env)
        try:
            daemon.post(f"/api/projects/{pid}/messages", {"text": "start the slow job"})
            _wait_event(path, lambda e: e["type"] == "turn_end")
            _wait_event(path, lambda e: e["type"] == "helper" and e.get("event") in {"start", "spawn_requested"})
            assert daemon.get(f"/api/projects/{pid}").json()["helpers"], "helper should be listed as running"
        finally:
            daemon.kill()

        daemon = Daemon(env).start()
        try:
            report = _wait_event(path, lambda e: e["type"] == "turn_start" and e["kind"] == "helper_done", 60)
            assert "unknown" in report["text"].lower() or "exited" in report["text"].lower(), report["text"]
            end = _wait_event(path, lambda e: e["type"] == "turn_end" and e["turn"] == report["turn"], 60)
            assert end["reply"] == "That agent was cut off; I will redo its job."
        finally:
            daemon.stop()


def test_stop_also_stops_background_helpers(env):
    script = [
        tool_step("delegate_task", {"goal": "HELPER-3 long job", "background": True}),
        text_step("An agent is on it."),
        text_step("Stopped as you asked."),
    ]
    slow = [{**tool_step("terminal", {"command": "sleep 2"}, "c3"), "delay": 3}] * 20
    with FakeOpenAIServer(script, side_scripts={"HELPER-3": slow}) as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env)
            daemon.post(f"/api/projects/{pid}/messages", {"text": "start the long job"})
            _wait_event(path, lambda e: e["type"] == "turn_end")
            _wait_event(path, lambda e: e["type"] == "helper" and e.get("event") in {"start", "spawn_requested"})

            assert daemon.post(f"/api/projects/{pid}/stop", {}).status_code == 200
            stop = _wait_event(path, lambda e: e["type"] == "stop_requested")
            assert stop["helpers_stopped"] == 1

            deadline = time.time() + 45
            while daemon.get(f"/api/projects/{pid}").json()["helpers"] and time.time() < deadline:
                time.sleep(0.5)
            assert daemon.get(f"/api/projects/{pid}").json()["helpers"] == []

            # The stopped helper's report is held, not acted on...
            _wait_event(path, lambda e: e["type"] == "queued" and e["item"]["kind"] == "helper_done")
            time.sleep(2)
            assert sum(e["type"] == "turn_start" for e in _events(path)) == 1
            assert daemon.get(f"/api/projects/{pid}").json()["paused"] is True

            # ...until the owner writes again; then it rides along in one turn.
            daemon.post(f"/api/projects/{pid}/messages", {"text": "ok, carry on later"})
            turn = _wait_event(path, lambda e: e["type"] == "turn_start" and e.get("display") == "ok, carry on later")
            assert "HELPER-3" in turn["text"]
            _wait_event(path, lambda e: e["type"] == "turn_end" and e["turn"] == turn["turn"])
            shown = daemon.get(f"/api/projects/{pid}").json()["messages"]
            assert shown[-2] == {"role": "user", "content": "ok, carry on later", "kind": "chat"}, shown[-3:]
            assert shown[-3]["kind"] == "system"
        finally:
            daemon.stop()


def test_watchdog_keeps_going_until_the_owner_is_needed(env):
    script = [
        text_step("Built wave 1."),
        text_step("Built wave 2."),
        text_step("## What I need from you\n1. Approve the preview."),
        text_step("should never be used"),
    ]
    with FakeOpenAIServer(script) as llm:
        _write_config(env["hermes_home"], llm.base_url,
                      lyra_lite={"watchdog": {"check_seconds": 0.5, "idle_minutes": 0}})
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env)
            (path / ".sdlc").mkdir()
            (path / ".sdlc" / "progress.md").write_text(
                "## Phase ledger\n| Phase | Status |\n|---|---|\n| Remaining development | running |\n")
            daemon.post(f"/api/projects/{pid}/messages", {"text": "build the app"})
            _wait_event(path, lambda e: e["type"] == "turn_end"
                        and "What I need from you" in (e.get("reply") or ""), 60)
            time.sleep(3)
            starts = [e for e in _events(path) if e["type"] == "turn_start"]
            assert [e["kind"] for e in starts] == ["user", "watchdog", "watchdog"]
            assert len(llm.main_requests()) == 3
        finally:
            daemon.stop()


def test_changed_rules_are_offered_and_applied(env):
    with FakeOpenAIServer([text_step("Hello.")]) as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env)
            daemon.post(f"/api/projects/{pid}/messages", {"text": "hi"})
            _wait_event(path, lambda e: e["type"] == "turn_end")
            assert daemon.get(f"/api/projects/{pid}").json()["rules_outdated"] is False

            state_file = path / ".lyra" / "state.json"
            state = json.loads(state_file.read_text())
            state["rules_hash"] = "older-rules"
            state_file.write_text(json.dumps(state))
            assert daemon.get(f"/api/projects/{pid}").json()["rules_outdated"] is True

            assert daemon.post(f"/api/projects/{pid}/apply-rules", {}).status_code == 200
            assert daemon.get(f"/api/projects/{pid}").json()["rules_outdated"] is False
        finally:
            daemon.stop()


def test_frozen_mid_turn_like_a_sleeping_laptop_then_finishes(env):
    script = [{**text_step("Finished after the nap."), "delay": 2}]
    with FakeOpenAIServer(script) as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env)
            daemon.post(f"/api/projects/{pid}/messages", {"text": "do the thing"})
            _wait_event(path, lambda e: e["type"] == "turn_start")
            daemon.proc.send_signal(signal.SIGSTOP)
            time.sleep(6)
            daemon.proc.send_signal(signal.SIGCONT)
            end = _wait_event(path, lambda e: e["type"] == "turn_end", 60)
            assert end["status"] == "done" and end["reply"] == "Finished after the nap."
            assert daemon.get(f"/api/projects/{pid}").json()["running"] is False
        finally:
            daemon.stop()


def test_new_project_sends_team_and_brief_and_team_changes_reach_lyra(env):
    script = [text_step("Hi! I'm Lyra. Who is the calculator for?"), text_step("Team noted.")]
    with FakeOpenAIServer(script) as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        try:
            path = env["home"] / "Lyra Projects" / "Calc"
            res = daemon.post("/api/projects", {"path": str(path), "create": True, "style": "mvp",
                                                "team": ["sw-developer", "not-an-agent"],
                                                "brief": "I want a scientific calculator"})
            assert res.status_code == 200, res.text
            pid = res.json()["id"]
            assert res.json()["team"] == ["req-engineer", "task-planner", "sw-developer"]
            start = _wait_event(path, lambda e: e["type"] == "turn_start")
            assert start["text"].startswith("IDRAK_INTERNAL_SETUP_BEGIN")
            assert '"sw-developer"' in start["text"] and "scientific calculator" in start["text"]
            assert start["display"] == "I want a scientific calculator"
            _wait_event(path, lambda e: e["type"] == "turn_end")

            assert daemon.post(f"/api/projects/{pid}/team",
                               {"team": ["req-engineer", "task-planner", "qa-engineer"]}).status_code == 200
            team_turn = _wait_event(path, lambda e: e["type"] == "turn_start" and e["kind"] == "team")
            assert "IDRAK_INTERNAL_SKILLS_UPDATE_BEGIN" in team_turn["text"]
            _wait_event(path, lambda e: e["type"] == "turn_end" and e["turn"] == team_turn["turn"])

            shown = daemon.get(f"/api/projects/{pid}").json()["messages"]
            assert shown[0] == {"role": "user", "content": "I want a scientific calculator", "kind": "chat"}
            assert shown[2]["kind"] == "auto" and "Quality assurance" in shown[2]["content"]
            catalog = daemon.get("/api/catalog").json()
            assert {a["id"] for a in catalog["agents"] if a["required"]} == {"req-engineer", "task-planner"}
            assert httpx.get(f"{daemon.base}/avatars/req-engineer.webp", timeout=5).status_code == 200
        finally:
            daemon.stop()


def test_open_app_serves_the_project_page_but_never_hidden_files(env):
    with FakeOpenAIServer([]) as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env)
            assert daemon.get(f"/api/projects/{pid}/preview").json()["available"] is False
            assert daemon.post(f"/api/projects/{pid}/preview/open", {}).status_code == 409
            (path / "index.html").write_text("<h1>Calc</h1>")
            (path / "src").mkdir()
            (path / "src" / "app.mjs").write_text("export const x = 1;")
            (path / ".env").write_text("SECRET=1")
            assert daemon.get(f"/api/projects/{pid}/preview").json() == {"available": True, "build": False}

            url = daemon.post(f"/api/projects/{pid}/preview/open", {}).json()["url"]
            origin = url.split("/?")[0]
            assert httpx.get(origin + "/", timeout=5).status_code == 401  # only via Lyra's link
            with httpx.Client(base_url=origin, timeout=5, follow_redirects=True) as browser:
                page = browser.get(url)
                assert page.status_code == 200 and "Calc" in page.text and "lyra=" not in str(page.url)
                module = browser.get("/src/app.mjs")
                assert module.headers["content-type"].startswith("text/javascript")
                assert browser.get("/.env").status_code == 404
                assert browser.get("/.lyra/state.json").status_code == 404
                (env["home"] / "secret.txt").write_text("TOPSECRET")
                for escape in ("/../../secret.txt", "/%2e%2e/%2e%2e/secret.txt", "/..%2f..%2fsecret.txt"):
                    assert "TOPSECRET" not in browser.get(escape).text, escape
        finally:
            daemon.stop()


BUILD_SCRIPT = """
import fs from 'node:fs';
fs.appendFileSync('builds.log', 'x');
const src = fs.readFileSync('src/main.js', 'utf8');
if (src.includes('BROKEN')) { console.error('src/main.js: unexpected token'); process.exit(1); }
fs.mkdirSync('dist/assets', { recursive: true });
fs.writeFileSync('dist/assets/app.js', src);
fs.writeFileSync('dist/index.html', '<script type="module" src="/assets/app.js"></script><h1>Built</h1>');
"""


@pytest.mark.skipif(shutil.which("npm") is None, reason="needs Node.js")
def test_open_app_builds_a_site_and_serves_it_from_the_root(env):
    """A built site asks for /assets/... from the root of its address; Open app
    must build it when stale and serve it where those paths work."""
    with FakeOpenAIServer([]) as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env)
            (path / "package.json").write_text(json.dumps({"name": "site", "private": True, "type": "module",
                                                           "scripts": {"build": "node build.mjs"}}))
            (path / "build.mjs").write_text(BUILD_SCRIPT)
            (path / "node_modules").mkdir()
            (path / "src").mkdir()
            (path / "src" / "main.js").write_text("console.log('v1')")
            (path / "index.html").write_text("<script type=module src=/src/main.js></script>")  # source, not the app
            assert daemon.get(f"/api/projects/{pid}/preview").json() == {"available": True, "build": True}

            url = daemon.post(f"/api/projects/{pid}/preview/open", {}).json()["url"]
            origin = url.split("/?")[0]
            with httpx.Client(base_url=origin, timeout=5, follow_redirects=True) as browser:
                assert "Built" in browser.get(url).text
                asset = browser.get("/assets/app.js")  # the absolute path the page asks for
                assert asset.status_code == 200 and "v1" in asset.text
                assert "Built" in browser.get("/pricing").text  # app routes fall back to the page

                # Up to date: no rebuild. Source changed: rebuilt before opening.
                daemon.post(f"/api/projects/{pid}/preview/open", {})
                assert (path / "builds.log").read_text() == "x"
                time.sleep(1.1)
                (path / "src" / "main.js").write_text("console.log('v2')")
                daemon.post(f"/api/projects/{pid}/preview/open", {})
                assert (path / "builds.log").read_text() == "xx"
                assert "v2" in browser.get("/assets/app.js").text

            time.sleep(1.1)
            (path / "src" / "main.js").write_text("BROKEN")
            res = daemon.post(f"/api/projects/{pid}/preview/open", {})
            assert res.status_code == 409 and "unexpected token" in res.json()["detail"]
        finally:
            daemon.stop()


def _tool_names(request: dict) -> set[str]:
    return {t.get("function", {}).get("name") for t in request.get("tools") or []}


def test_lyra_has_no_shell_but_her_agents_do(env):
    def scripts(path: Path):
        target = path / "made-by-agent.txt"
        parent = [tool_step("delegate_task", {"goal": f"HELPER-SH create {target}", "background": True}),
                  text_step("An agent is on it."), text_step("Done.")]
        helper = [tool_step("terminal", {"command": f"echo ok > '{target}'"}, "call_sh"),
                  text_step("Created it.")]
        return parent, {"HELPER-SH": helper}

    with FakeOpenAIServer([]) as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env)
            llm.script, llm.side_scripts = scripts(path)
            daemon.post(f"/api/projects/{pid}/messages", {"text": "make the file"})
            report = _wait_event(path, lambda e: e["type"] == "turn_start" and e["kind"] == "helper_done", 120)
            _wait_event(path, lambda e: e["type"] == "turn_end" and e["turn"] == report["turn"], 60)

            lyra_tools = _tool_names(llm.main_requests()[0])
            assert "delegate_task" in lyra_tools and "read_file" in lyra_tools
            assert not lyra_tools & {"terminal", "process", "execute_code"}, lyra_tools
            def first_user(r):
                return next((json.dumps(m.get("content")) for m in r["messages"] if m.get("role") == "user"), "")

            helper_requests = [r for r in llm.main_requests() if "HELPER-SH" in first_user(r)]
            helper_tools = _tool_names(helper_requests[0])
            assert "terminal" in helper_tools
            assert (path / "made-by-agent.txt").read_text().strip() == "ok"
        finally:
            daemon.stop()


def test_large_tool_output_is_cut_down_in_lyras_conversation(env):
    with FakeOpenAIServer([]) as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env)
            (path / "big.txt").write_text("".join(f"needle line {i} {'x' * 80}\n" for i in range(400)))
            llm.script = [tool_step("search_files", {"pattern": "needle", "path": str(path)}), text_step("Seen.")]
            daemon.post(f"/api/projects/{pid}/messages", {"text": "look"})
            _wait_event(path, lambda e: e["type"] == "turn_end")
            follow_up = llm.main_requests()[1]["messages"]
            tool_result = [m for m in follow_up if m.get("role") == "tool"][-1]["content"]
            assert len(tool_result) < 9_000, len(tool_result)
        finally:
            daemon.stop()


def test_build_profile_reaches_lyra_in_the_setup_message(env):
    with FakeOpenAIServer([text_step("Hi!")]) as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        try:
            path = env["home"] / "Lyra Projects" / "Tiny"
            res = daemon.post("/api/projects", {"path": str(path), "create": True, "team": [],
                                                "profile": "personal", "brief": "a to-do list"})
            assert res.json()["profile"] == "personal"
            start = _wait_event(path, lambda e: e["type"] == "turn_start")
            assert '"build_profile": "personal"' in start["text"]
        finally:
            daemon.stop()


def _first_user_message(request: dict) -> str:
    return next(json.dumps(m.get("content")) for m in request["messages"] if m.get("role") == "user")


def test_hermes_shared_memory_never_reaches_lyra_but_project_recall_does(env):
    memories = env["hermes_home"] / "memories"
    memories.mkdir(parents=True, exist_ok=True)
    (memories / "MEMORY.md").write_text("OTHER-PROJECT-SECRET: the YouTube app uses OAuth.\n")
    (memories / "USER.md").write_text("OTHER-PROJECT-PROFILE: works on YouTube analytics.\n")
    script = [text_step("Noted, semicolons."),
              tool_step("project_recall", {"query": "CSV separator"}), text_step("You chose semicolons.")]
    with FakeOpenAIServer(script) as llm:
        _write_config(env["hermes_home"], llm.base_url,
                      memory={"memory_enabled": True, "user_profile_enabled": True})
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env)
            daemon.post(f"/api/projects/{pid}/messages", {"text": "The CSV export must use semicolons as separator."})
            _wait_event(path, lambda e: e["type"] == "turn_end")
            daemon.post(f"/api/projects/{pid}/messages", {"text": "What separator did I pick?"})
            _wait_event(path, lambda e: e["type"] == "turn_end" and "semicolons" in (e.get("reply") or "") and "chose" in e["reply"])

            first = llm.main_requests()[0]
            assert "OTHER-PROJECT" not in json.dumps(first), "shared Hermes memory leaked into the project"
            tools = _tool_names(first)
            assert "project_recall" in tools and not tools & {"memory", "session_search"}
            recall_result = [m for m in llm.main_requests()[-1]["messages"] if m.get("role") == "tool"][-1]["content"]
            assert "Owner: The CSV export must use semicolons" in recall_result
        finally:
            daemon.stop()


def test_focus_note_rides_along_only_when_the_state_changes(env):
    with FakeOpenAIServer([text_step("One."), text_step("Two."), text_step("Three.")]) as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env)
            (path / ".sdlc").mkdir()
            ledger = path / ".sdlc" / "progress.md"
            ledger.write_text("## Phase ledger\n| Phase | Status |\n|---|---|\n| Development | running — CSV export left |\n")
            for n, text in enumerate(["first", "second"], 1):
                daemon.post(f"/api/projects/{pid}/messages", {"text": text})
                _wait_event(path, lambda e, n=n: e["type"] == "turn_end" and sum(
                    1 for x in _events(path) if x["type"] == "turn_end") >= n)
            ledger.write_text("## Phase ledger\n| Phase | Status |\n|---|---|\n| Development | verified |\n| QA | running |\n")
            daemon.post(f"/api/projects/{pid}/messages", {"text": "third"})
            _wait_event(path, lambda e: e["type"] == "turn_end" and e.get("reply") == "Three.")

            def latest_user(request):
                return [m for m in request["messages"] if m.get("role") == "user"][-1]["content"]

            sent = [latest_user(r) for r in llm.main_requests()]
            assert "[Project focus" in sent[0] and "CSV export left" in sent[0]
            assert sent[1] == "second"  # unchanged state: no repeat
            assert "[Project focus" in sent[2] and "QA" in sent[2]
            shown = [m["content"] for m in daemon.get(f"/api/projects/{pid}").json()["messages"]]
            assert "first" in shown and not any("[Project focus" in m for m in shown)
        finally:
            daemon.stop()


def test_about_me_reaches_lyra_in_every_project(env):
    with FakeOpenAIServer([text_step("Hi.")]) as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        try:
            saved = daemon.post("/api/settings", {"about_me": "ABOUT-ME: explain simply, Android user."}).json()
            assert saved["about_me"].startswith("ABOUT-ME")
            pid, path = _new_project(daemon, env)
            daemon.post(f"/api/projects/{pid}/messages", {"text": "hello"})
            _wait_event(path, lambda e: e["type"] == "turn_end")
            assert "ABOUT-ME: explain simply" in json.dumps(llm.main_requests()[0]["messages"][0])
        finally:
            daemon.stop()
