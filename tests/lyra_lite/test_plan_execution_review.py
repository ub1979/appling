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


def test_new_reviewed_nested_scope_cannot_reuse_old_execution(tmp_path):
    import hashlib
    old_requirements = '# Requirements\nEdit documents.\n\n## Approval gates and current state\nBaseline approved.\n'
    (tmp_path / 'requirements.md').write_text(old_requirements)
    (tmp_path / 'plan.md').write_text('# Plan\nImplement baseline.\n')
    store = ProjectStore(tmp_path).init()
    legacy = hashlib.sha256(review._requirements_content(old_requirements, include_nested=False).encode()).hexdigest()
    old_plan = review.implementation_plan(tmp_path)['revision']
    store.update_state(requirements_approved=legacy, requirements_revision_format=2,
                       plan_approved=old_plan, plan_requirements=legacy, plan_review_required=True,
                       plan_execution={'plan': old_plan, 'requirements': legacy})
    # The old format produces the SAME digest despite the material new scope.
    new_requirements = old_requirements + '\n### New menu requirements\nOpen recent local projects.\n'
    assert hashlib.sha256(review._requirements_content(new_requirements, include_nested=False).encode()).hexdigest() == legacy
    (tmp_path / 'requirements.md').write_text(new_requirements)
    card = store.add_inbox('requirements', revision=legacy,
                          question='Approve requirements?\n\n---\n\n' + new_requirements)
    store.close_inbox(card['id'], 'answered', answer='Approve requirements')
    (tmp_path / 'plan.md').write_text('# Plan\nImplement recent projects, then focused QA.\n')
    runner = ProjectRunner(store, lambda *_: None)
    try:
        assert store.state()['requirements_approved'] == review.requirements_revision(tmp_path)
        assert not review.plan_execution_started(store.state())
        review_card, = runner.snapshot()['inbox']
        assert review_card['kind'] == 'plan'
        assert review_card['revision'] == review.implementation_plan(tmp_path)['revision']
        assert review_card['requirements'] != legacy
        assert store.state()['plan_approved'] == old_plan  # historical evidence is retained
    finally:
        runner.shutdown()
