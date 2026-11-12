"""Design must be able to prepare the artifact required by the review gate."""

from lyra_lite.store import ProjectStore
from tests.fakes.fake_openai_server import FakeOpenAIServer, text_step, tool_step
from tests.lyra_lite.test_lyrad_real_path import (  # noqa: F401
    Daemon, _events, _new_project, _wait_event, _write_config, env,
)


def test_design_prepares_prototype_while_development_waits_for_owner_review(env):
    design = "ui-designer: Create the clickable prototype for owner review"
    development = "sw-developer: Implement the application"
    with FakeOpenAIServer([], side_scripts={design: [text_step("Prototype design report.")]}) as llm:
        _write_config(env["hermes_home"], llm.base_url,
                      lyra_lite={"watchdog": {"enabled": False}})
        daemon = Daemon(env).start()
        try:
            pid, root = _new_project(daemon, env, "Design review")
            (root / "requirements.md").write_text("# Tasks\nStatus: Draft\nA personal task list.\n")
            ProjectStore(root).update_state(requirements_review=True,
                                           team=["req-engineer", "ui-designer", "sw-developer"])
            llm.script = [
                tool_step("delegate_task", {"goal": design}, call_id="design"),
                tool_step("delegate_task", {"goal": development}, call_id="development"),
                text_step("Prototype preparation started. Development waits for review."),
                text_step("Design report received; prototype review is next."),
            ]
            assert daemon.post(f"/api/projects/{pid}/messages", {"text": "Prepare the prototype"}).is_success
            _wait_event(root, lambda e: e["type"] == "helper" and e.get("event") == "start"
                        and e.get("goal") == design)
            denial = _wait_event(root, lambda e: e["type"] == "tool" and e.get("id") == "development"
                                 and e.get("phase") == "done")
            assert "Finish the owner review" in denial["result"]
            _wait_event(root, lambda e: e["type"] == "turn_end")
            assert not any(e["type"] == "helper" and e.get("goal") == development for e in _events(root))
        finally:
            daemon.stop()
