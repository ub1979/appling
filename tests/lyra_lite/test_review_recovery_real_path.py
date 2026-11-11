"""Recover expired review buttons through real REST, disk state, restart, and Hermes."""
import json

from lyra_lite.review import PROTOTYPE_CHOICES, prototype_revision
from lyra_lite.store import ProjectStore
from tests.fakes.fake_openai_server import FakeOpenAIServer, text_step
from tests.lyra_lite.test_lyrad_real_path import Daemon, _wait_event, _write_config, env  # noqa: F401


def test_expired_review_restores_controls_without_ai_and_survives_restart(env):
    with FakeOpenAIServer([text_step("Owner review decision received.")]) as llm:
        _write_config(env["hermes_home"], llm.base_url, lyra_lite={"watchdog": {"enabled": False}})
        root = env["home"] / "Restore review"
        (root / "prototypes").mkdir(parents=True)
        (root / "prototypes/index.html").write_text("<button>Try the dropdown</button>")
        store = ProjectStore(root).init()
        store.update_state(project_kind="app", requirements_review=True)
        item = store.add_inbox("prototype", question="Approve the updated prototype?",
                               choices=list(PROTOTYPE_CHOICES), revision=prototype_revision(root))
        store.close_inbox(item["id"], "expired")
        daemon = Daemon(env).start()
        try:
            added = daemon.post("/api/projects", {"path": str(root), "create": False})
            assert added.is_success, added.text
            prefix = f"/api/projects/{added.json()['id']}"
            detail = daemon.get(prefix).json()
            assert detail["review_recovery"]["id"] == item["id"]
            opened = daemon.post(prefix + "/review/reopen", {"item_id": item["id"]})
            assert opened.is_success, opened.text
            card_id = opened.json()["id"]
            assert daemon.get(prefix).json()["inbox"][0]["choices"] == list(PROTOTYPE_CHOICES)
            assert llm.main_requests() == []
            assert not store.state().get("prototype_approved")

            daemon.stop()
            daemon = Daemon(env).start()
            detail = daemon.get(prefix).json()
            assert detail["review_recovery"]["id"] == card_id
            reopened = daemon.post(prefix + "/review/reopen", {"item_id": card_id})
            assert reopened.is_success, reopened.text
            card_id = reopened.json()["id"]
            assert llm.main_requests() == []
            assert daemon.post(prefix + "/inbox/" + card_id, {"answer": "Approve prototype"}).status_code == 409
            preview = daemon.post(prefix + "/preview/prototype", {}).json()
            assert daemon.post(prefix + "/inbox/" + card_id, {"answer": {
                "choice": "Approve prototype", "revision": preview["revision"],
            }}).is_success
            _wait_event(root, lambda e: e["type"] == "turn_end" and e.get("reply") == "Owner review decision received.")
            assert store.state()["prototype_approved"] == preview["revision"]
            assert daemon.get(prefix).json()["review_recovery"] is None
            request = llm.main_requests()[0]
            assert request["messages"][-1]["role"] == "user"
            assert "Owner's prototype review decision" in request["messages"][-1]["content"]
        finally:
            daemon.stop()
