"""Website templates: library, private user templates, live demos, hand-off."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import httpx

from tests.fakes.fake_anthropic_server import FakeAnthropicServer, text_step
from tests.fakes.fake_openai_server import FakeOpenAIServer
from tests.fakes.fake_openai_server import text_step as openai_text
from tests.lyra_lite.test_lyrad_real_path import (  # noqa: F401
    TOKEN, Daemon, _events, _new_project, _wait_event, _write_config, env,
)

REPO = Path(__file__).resolve().parents[2]


def test_template_library_user_templates_and_live_demos(env):
    with FakeOpenAIServer([]) as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        try:
            web = daemon.get("/api/templates?kind=website").json()["templates"]
            ids = {t["id"] for t in web}
            assert {"cinematic-parallax", "product-launch-3d", "scroll-story", "creative-portfolio", "saas-motion"} <= ids
            # Every built-in website template ships a live demo to preview.
            builtin = [t for t in web if not t["own"]]
            assert builtin and all(t["has_demo"] and t["demo_url"] for t in builtin)
            demos = {t["id"]: t["demo_url"] for t in builtin}

            mine = daemon.post("/api/templates", {"name": "Glass Agency", "kind": "website",
                                                  "tagline": "frosted", "spec": "PRIVATE-PROMPT build a glass site"}).json()
            assert mine["own"] is True and mine["id"].startswith("my-")
            saved = env["hermes_home"] / "lyra-lite" / "templates" / mine["id"] / "spec.md"
            assert "PRIVATE-PROMPT" in saved.read_text()
            assert not (REPO / "lyra_lite" / "templates" / mine["id"]).exists()  # never in Lyra's source
            assert mine["id"] in {t["id"] for t in daemon.get("/api/templates?kind=website").json()["templates"]}
            assert daemon.get("/api/templates?kind=video").json()["templates"] == []

            url = demos["cinematic-parallax"]
            assert httpx.get(daemon.base + url, timeout=5).status_code == 401  # cookie-gated
            with httpx.Client(base_url=daemon.base, timeout=5) as browser:
                browser.get("/")
                page = browser.get(url)
                assert page.status_code == 200 and "Aurelia" in page.text
                assert browser.get(url + ".hidden").status_code == 404
                assert browser.get("/preview/templates/not-a-template/").status_code == 404

            assert httpx.delete(f"{daemon.base}/api/templates/cinematic-parallax",
                                headers={"x-lyra-token": TOKEN}, timeout=5).status_code == 404  # built-ins stay
            assert httpx.delete(f"{daemon.base}/api/templates/{mine['id']}",
                                headers={"x-lyra-token": TOKEN}, timeout=5).status_code == 200
            assert not saved.exists()
        finally:
            daemon.stop()


def test_website_project_hands_template_to_requirements(env):
    with FakeOpenAIServer([openai_text("Love it. Shall we keep the travel mood?"),
                           openai_text("Noted: Aurelia Lodge.")]) as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        try:
            path = env["home"] / "Lyra Projects" / "Retreat"
            res = daemon.post("/api/projects", {"path": str(path), "create": True, "team": [], "profile": "personal",
                                                "kind": "website", "template": "cinematic-parallax",
                                                "brief": "A site for my cabin retreat"})
            assert res.status_code == 200, res.text
            assert res.json()["project_kind"] == "website" and res.json()["template"] == "cinematic-parallax"
            start = _wait_event(path, lambda e: e["type"] == "turn_start")
            text = start["text"]
            payload = json.loads(text[len("IDRAK_INTERNAL_SETUP_BEGIN"):text.rindex("IDRAK_INTERNAL_SETUP_END")])
            assert payload["project_kind"] == "website"
            assert payload["kind_skill"] == "ultimate-builder:web-cinematic"
            assert payload["template"]["id"] == "cinematic-parallax"
            assert "Pinned story" in payload["template_spec"] and "delta interview" in payload["template_gate"]
            assert start["display"] == "A site for my cabin retreat"
            # Websites skip the size question: always the full functional + visual QA.
            assert payload["build_profile"] == "reusable"
            assert "BLOCKED, never APPROVED" in payload["website_gate"]

            # The checker and the template's live demo are inside the project
            # (git-ignored), so helpers on any engine can run and read them.
            first = _wait_event(path, lambda e: e["type"] == "turn_end")
            kit = path / ".lyra" / "kit"
            checker = REPO / "plugins/ultimate-builder/skills/ultimate-app-builder/references/workflows/web-cinematic/scripts/site-check.mjs"
            assert (kit / "site-check.mjs").read_bytes() == checker.read_bytes()
            demo = REPO / "lyra_lite/templates/cinematic-parallax/demo/index.html"
            assert (kit / "reference" / "index.html").read_bytes() == demo.read_bytes()
            for tool in ("imagine", "cutout", "frames"):  # run with Lyra's own Python
                assert os.access(kit / tool, os.X_OK), tool
            assert "usage" in subprocess.run([str(kit / "cutout"), "--help"], capture_output=True, text=True).stdout

            # Later turns carry the website rule, even for projects set up
            # before it existed.
            pid = res.json()["id"]
            assert daemon.post(f"/api/projects/{pid}/messages", {"text": "Call it Aurelia Lodge"}).status_code == 200
            _wait_event(path, lambda e: e["type"] == "turn_end" and e["turn"] != first["turn"])
            last = llm.main_requests()[-1]["messages"]
            user_text = next(m["content"] for m in reversed(last) if m["role"] == "user")
            assert "Call it Aurelia Lodge" in str(user_text) and "site-check.mjs" in str(user_text)
        finally:
            daemon.stop()


def test_new_skills_reach_claude_code_as_native_skills(env):
    with FakeOpenAIServer([]) as hermes_llm, FakeAnthropicServer([text_step("ok")]) as claude:
        _write_config(env["hermes_home"], hermes_llm.base_url)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env)
            daemon.post(f"/api/projects/{pid}/settings", {"engine": "claude", "claude": {
                "base_url": claude.base_url, "auth_token": "x", "model": "claude-fake"}})
            daemon.post(f"/api/projects/{pid}/messages", {"text": "hi"})
            _wait_event(path, lambda e: e["type"] == "turn_end", 120)
            first = json.dumps(claude.main_requests()[0])
            assert "ultimate-builder:web-cinematic" in first
            assert "ultimate-builder:business-motion-film" in first
        finally:
            daemon.stop()


def test_web_cinematic_skill_follows_the_description_rule():
    text = (REPO / "plugins/ultimate-builder/skills/ultimate-app-builder/references/workflows/web-cinematic/SKILL.md").read_text()
    description = re.search(r"^description: (.*)$", text, re.MULTILINE).group(1)
    assert len(description) <= 60 and description.endswith(".")


def test_photo_real_template_asks_for_the_owners_footage(env):
    with FakeOpenAIServer([openai_text("Do you have a video of the reveal?")]) as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        try:
            path = env["home"] / "Lyra Projects" / "Launch"
            res = daemon.post("/api/projects", {"path": str(path), "create": True, "team": [],
                                                "kind": "website", "template": "grand-reveal", "brief": "Unveil our watch"})
            assert res.status_code == 200, res.text
            start = _wait_event(path, lambda e: e["type"] == "turn_start")
            text = start["text"]
            payload = json.loads(text[len("IDRAK_INTERNAL_SETUP_BEGIN"):text.rindex("IDRAK_INTERNAL_SETUP_END")])
            assert "video" in payload["media_gate"] and ".lyra/kit/frames" in payload["media_gate"]
            assert "never pass ai pictures off" in payload["media_gate"].lower()
        finally:
            daemon.stop()
