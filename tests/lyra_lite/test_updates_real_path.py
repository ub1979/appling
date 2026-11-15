"""Exercise update and model routing through the daemon, with local model endpoints."""

from __future__ import annotations

import subprocess
from pathlib import Path

import httpx

from lyra_lite.review import PROTOTYPE_CHOICES, REQUIREMENTS_CHOICES, requirements_revision
from tests.fakes.fake_openai_server import FakeOpenAIServer, text_step, tool_step
from tests.lyra_lite.test_lyrad_real_path import Daemon, _events, _wait_event, _write_config, env  # noqa: F401


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def test_open_and_update_with_prototype_and_change_review(env):
    root = env["home"] / "Built app"
    root.mkdir()
    _git(root, "init", "-b", "main")
    (root / "index.html").write_text("<h1>Existing application</h1>")
    (root / "requirements.md").write_text("# Requirements\n**Status:** Approved\nKeep saved orders.\n")
    prototype = root / "prototypes"
    prototype.mkdir()
    (prototype / "index.html").write_text('<a href="old.html">Existing design</a>')
    ledger = root / ".sdlc" / "progress.md"
    ledger.parent.mkdir()
    ledger.write_text("## Revision 1\n\n| Phase | Status |\n| --- | --- |\n| Delivery | Verified |\n")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "Original delivery")
    base = _git(root, "rev-parse", "HEAD")
    from lyra_lite.store import ProjectStore

    store = ProjectStore(root).init()
    store.update_state(plan_approved="original-plan", plan_requirements=requirements_revision(root),
                       plan_execution={"plan": "original-plan", "requirements": requirements_revision(root)},
                       plan_review_required=True)
    plan = tool_step("delegate_task", {"goal": "task-planner: Plan the update"})
    change = tool_step("delegate_task", {"goal": "change-manager: Review the update"})
    preview = tool_step("clarify", {"question": "Do these flows work?", "choices": list(PROTOTYPE_CHOICES)})
    requirements = tool_step("clarify", {"question": "Approve the draft?", "choices": list(REQUIREMENTS_CHOICES)})
    script = [
        text_step("Your order tracker is built. What would you like to change?"),
        plan, preview, requirements, plan, change, text_step("Change management started."),
        plan, text_step("We need a decision on existing orders."),
        plan, text_step("Planning started."),
    ]
    with FakeOpenAIServer(script, side_scripts={
        "change-manager: Review the update": [text_step("Should imported orders stay editable?")],
        "task-planner: Plan the update": [text_step("Plan complete.")],
    }) as llm:
        _write_config(env["hermes_home"], llm.base_url)
        daemon = Daemon(env).start()
        try:
            res = daemon.post("/api/projects", {"path": str(root), "create": False, "kind": "website", "team": []})
            assert res.is_success, res.text
            url = f"/api/projects/{res.json()['id']}"
            assert daemon.get(url).json()["update_available"]
            assert not any(e["type"] == "turn_start" for e in _events(root))
            assert daemon.post(f"{url}/update", {"branch": "main"}).status_code == 409
            assert _git(root, "branch", "--show-current") == "main"
            started = daemon.post(f"{url}/update", {"branch": "appling/update-2"})
            assert started.is_success, started.text
            assert _git(root, "branch", "--show-current") == "appling/update-2"
            assert _git(root, "rev-parse", "main") == base
            assert store.state()['plan_execution'] is None
            assert store.state()['plan_approved'] is None
            assert "change-manager" in daemon.get(url).json()["team"]
            assert daemon.post(f"{url}/update", {"branch": None}).status_code == 409
            setup = _wait_event(root, lambda e: e["type"] == "turn_start" and e["kind"] == "setup")
            assert '"project_update"' in setup["text"]
            assert (root / ".lyra/updates/v2/requirements.md").read_text().endswith("Keep saved orders.\n")
            _wait_event(root, lambda e: e["type"] == "turn_end" and e["turn"] == setup["turn"])

            (root / "requirements.md").write_text("# Requirements\n**Status:** Draft\nImport and edit orders.\n")
            (prototype / "index.html").write_text('<a href="orders.html">Try the new order flow</a>')
            (prototype / "orders.html").write_text("<h1>Imported orders</h1>")
            assert daemon.post(f"{url}/messages", {"text": "Add an import flow."}).is_success
            item = _wait_event(root, lambda e: e["type"] == "inbox" and e["item"]["kind"] == "prototype")["item"]
            approval = f"{url}/inbox/{item['id']}"
            assert daemon.post(approval, {"answer": "Approve prototype"}).status_code == 409
            hosted = daemon.post(f"{url}/preview/prototype", {}).json()
            with httpx.Client(follow_redirects=True) as browser:
                page = browser.get(hosted["url"])
                assert page.is_success and 'href="orders.html"' in page.text
                assert "Imported orders" in browser.get(page.url.join("orders.html")).text
            assert hosted["revision"] == item["revision"]
            answer = {"choice": "Approve prototype", "revision": hosted["revision"]}
            assert daemon.post(approval, {"answer": {**answer, "revision": "old"}}).status_code == 409
            assert daemon.post(approval, {"answer": answer}).is_success
            draft = _wait_event(root, lambda e: e["type"] == "inbox" and e["item"]["kind"] == "requirements")["item"]
            assert daemon.post(f"{url}/inbox/{draft['id']}", {"answer": "Approve requirements"}).is_success
            _wait_event(root, lambda e: e["type"] == "turn_end" and e.get("reply") == "We need a decision on existing orders.")

            assert not any(e["type"] == "helper" and e.get("event") == "start"
                           and "task-planner:" in e.get("goal", "") for e in _events(root))
            rejected = [e.get("result", "") for e in _events(root)
                        if e["type"] == "tool" and e.get("phase") == "done"]
            assert any("Finish the owner review" in result for result in rejected)
            assert any("Change management must finish" in result for result in rejected)
            report = ledger.parent / "changes" / f"v2-{requirements_revision(root)[:12]}.md"
            report.parent.mkdir(exist_ok=True)
            report.write_text("Status: Ready\nKeep existing orders editable.\n")
            assert daemon.post(f"{url}/messages", {"text": "Keep existing orders editable."}).is_success
            _wait_event(root, lambda e: e["type"] == "helper" and e.get("event") == "reported"
                        and "task-planner:" in e.get("goal", ""))
            assert daemon.get(url).json()["active_update"]["revision"] == 2
            with ledger.open("a") as file:
                file.write("\n## Revision 2\n\n| Phase | Status |\n| --- | --- |\n| Delivery | Verified |\n")
            assert daemon.get(url).json()["update_available"]
            assert _git(root, "rev-parse", "main") == base
        finally:
            daemon.stop()


def test_saved_agent_model_uses_its_own_provider_and_survives_restart(env):
    tasks = [{"goal": "tech-writer: Explain imports"}, {"goal": "code-reviewer: Check imports"}]
    with FakeOpenAIServer([tool_step("delegate_task", {"tasks": tasks}), text_step("Working.")]) as llm, \
         FakeOpenAIServer([text_step("Documentation written.")]) as docs, \
         FakeOpenAIServer([text_step("Review complete.")]) as review:

        _write_config(env["hermes_home"], llm.base_url, custom_providers=[
            {"name": "Documentation", "base_url": docs.base_url, "api_key": "docs-key", "model": "doc-model"},
            {"name": "Review", "base_url": review.base_url, "api_key": "review-key", "model": "review-model"},
        ])
        daemon = Daemon(env).start()
        try:
            path = "/api/settings/agents/tech-writer"
            selection = {"provider": "custom:documentation", "model": "doc-model", "effort": "low"}
            response = daemon.post(path, {"selection": selection})
            assert response.is_success, response.text
            reviewer = {"provider": "custom:review", "model": "review-model", "effort": "high"}
            assert daemon.post("/api/settings/agents/code-reviewer", {"selection": reviewer}).is_success
            root = env["home"] / "Writing"
            pid = daemon.post("/api/projects", {"path": str(root), "create": True}).json()["id"]
            daemon.stop()
            daemon = Daemon(env).start()
            models = {row["id"]: row for row in daemon.get("/api/settings").json()["agent_models"]}
            assert models["tech-writer"]["selection"] == selection
            assert models["sw-developer"]["default"]["effort"] == "high"
            assert daemon.post(f"/api/projects/{pid}/messages", {"text": "Document order imports."}).is_success
            _wait_event(root, lambda e: e["type"] == "helper" and e.get("event") == "reported")
            assert [r["model"] for r in docs.main_requests()] == ["doc-model"]
            assert [r["model"] for r in review.main_requests()] == ["review-model"]
            assert all(r["model"] == "fake-model" for r in llm.main_requests())
            reset = daemon.post(path, {"selection": None})
            assert reset.is_success, reset.text
            reset_models = {row["id"]: row for row in reset.json()["agent_models"]}
            assert reset_models["tech-writer"]["selection"] is None
            assert reset_models["code-reviewer"]["selection"] == reviewer
        finally:
            daemon.stop()
