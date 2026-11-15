"""Pre-development plan approval cannot loop back after approved execution."""
from lyra_lite import review
from lyra_lite.engines.hermes import HermesEngine
from lyra_lite.runner import ProjectRunner
from lyra_lite.store import ProjectStore


def _approved(root):
    (root / "requirements.md").write_text("# Requirements\nEdit documents.\n")
    (root / "plan.md").write_text("# Plan\nImplement editor and verify it.\n")
    store = ProjectStore(root).init()
    requirements = review.requirements_revision(root)
    plan = review.implementation_plan(root)["revision"]
    store.update_state(requirements_approved=requirements, requirements_revision_format=2,
                       plan_approved=plan, plan_requirements=requirements, plan_review_required=True)
    card = store.add_inbox("plan", revision=plan, requirements=requirements)
    store.close_inbox(card["id"], "answered", answer="Approve implementation plan")
    return store


def test_development_start_latches_approved_execution_and_stops_plan_loop(tmp_path):
    store = _approved(tmp_path)
    engine = HermesEngine(workspace=str(tmp_path), session_key="execution-test", store=store)
    engine._on_progress("subagent.start", goal="sw-developer: Implement the approved editor", subagent_id="lead")
    (tmp_path / "plan.md").write_text("# Plan\nImplement editor in independent waves.\n")
    runner = ProjectRunner(store, lambda *_: None)
    try:
        assert runner.snapshot()["inbox"] == []
        assert store.state()["plan_approved"] != review.implementation_plan(tmp_path)["revision"]
        # An accidental model request must not reopen the same pre-build gate.
        assert "already started" in engine._on_clarify("Approve plan?", list(review.PLAN_CHOICES))
    finally:
        runner.shutdown()


def test_existing_executed_project_recovers_without_reoffering_stale_card(tmp_path):
    store = _approved(tmp_path)
    store.append_event("helper", event="start", goal="sw-developer: Implement editor", subagent_id="lead")
    (tmp_path / "plan.md").write_text("# Plan\nCompleted implementation details.\n")
    stale = store.add_inbox("plan", revision=review.implementation_plan(tmp_path)["revision"],
                            requirements=review.requirements_revision(tmp_path))
    runner = ProjectRunner(store, lambda *_: None)
    try:
        assert runner.snapshot()["inbox"] == []
        assert runner.recoverable_review() is None
        assert store.inbox_item(stale["id"])["status"] != "answered"
    finally:
        runner.shutdown()


def test_plan_edits_before_execution_still_require_review(tmp_path):
    store = _approved(tmp_path)
    (tmp_path / "plan.md").write_text("# Plan\nA different implementation approach.\n")
    runner = ProjectRunner(store, lambda *_: None)
    try:
        card, = runner.snapshot()["inbox"]
        assert card["kind"] == "plan"
        assert card["revision"] == review.implementation_plan(tmp_path)["revision"]
    finally:
        runner.shutdown()


def test_changed_plan_is_not_latched_as_approved_execution(tmp_path):
    store = _approved(tmp_path)
    (tmp_path / "plan.md").write_text("# Plan\nDifferent approach before execution.\n")
    engine = HermesEngine(workspace=str(tmp_path), session_key="execution-test", store=store)
    engine._on_progress("subagent.start", goal="sw-developer: Unapproved start", subagent_id="lead")
    assert not review.plan_execution_started(store.state())


def test_legacy_start_before_approval_is_not_execution_evidence(tmp_path):
    store = _approved(tmp_path)
    store.append_event("helper", event="start", goal="sw-developer: Earlier unrelated work", ts=1)
    (tmp_path / "plan.md").write_text("# Plan\nNew unexecuted implementation.\n")
    runner = ProjectRunner(store, lambda *_: None)
    try:
        assert not review.plan_execution_started(store.state())
        assert runner.snapshot()["inbox"][0]["kind"] == "plan"
    finally:
        runner.shutdown()
