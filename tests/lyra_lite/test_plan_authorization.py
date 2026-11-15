"""All coding handoffs use the same revision-bound authorization contract."""
import json

import pytest

from lyra_lite import review
from lyra_lite.delegation import dispatch_project_tasks
from lyra_lite.runner import ProjectRunner
from lyra_lite.store import ProjectStore


def project(root):
    (root / 'requirements.md').write_text('# Requirements\nEdit local documents.\n')
    (root / 'plan.md').write_text('# Plan\nImplement editor; verify it.\n')
    store = ProjectStore(root).init()
    return store, review.requirements_revision(root), review.implementation_plan(root)['revision']


@pytest.mark.parametrize('role', ['sw-developer', 'website-builder', 'oop-restructurer', 'debugger', 'qa-engineer'])
def test_unapproved_plan_blocks_handoff_before_provider_resolution(tmp_path, monkeypatch, role):
    store, requirements, _ = project(tmp_path)
    store.update_state(requirements_approved=requirements, plan_review_required=True)
    monkeypatch.setattr('lyra_lite.settings.resolve_agent_model', lambda *a: pytest.fail('Unapproved task reached provider resolution'))
    result = json.loads(dispatch_project_tasks(store, None, {'goal': role + ': implement the new scope'}))
    assert 'implementation plan' in result['error']


def test_approved_plan_authorizes_only_current_scope(tmp_path):
    store, requirements, plan = project(tmp_path)
    store.update_state(requirements_approved=requirements, plan_approved=plan, plan_requirements=requirements)
    assert review.implementation_authorized(tmp_path, store.state())
    (tmp_path / 'requirements.md').write_text('# Requirements\nEdit documents and upload them.\n')
    assert not review.implementation_authorized(tmp_path, store.state())
    store.update_state(requirements_approved=review.requirements_revision(tmp_path))
    assert not review.implementation_authorized(tmp_path, store.state())


def test_executed_baseline_allows_progress_edits_but_not_new_scope(tmp_path):
    store, requirements, plan = project(tmp_path)
    store.update_state(requirements_approved=requirements, plan_approved=plan, plan_requirements=requirements,
                       plan_execution={'plan': plan, 'requirements': requirements})
    (tmp_path / 'plan.md').write_text('# Plan\nCompleted implementation and engineering notes.\n')
    assert review.implementation_authorized(tmp_path, store.state())
    (tmp_path / 'requirements.md').write_text('# Requirements\nA new feature.\n')
    store.update_state(requirements_approved=review.requirements_revision(tmp_path))
    assert not review.implementation_authorized(tmp_path, store.state())


@pytest.mark.parametrize('changed', [False, True])
def test_requirements_answer_invalidates_only_obsolete_plan(tmp_path, changed):
    store, requirements, plan = project(tmp_path)
    store.update_state(requirements_approved=requirements, requirements_review=True,
                       plan_approved=plan, plan_requirements=requirements, plan_review_required=True,
                       plan_execution={'plan': plan, 'requirements': requirements})
    if changed:
        (tmp_path / 'requirements.md').write_text('# Requirements\nA new feature.\n')
    runner = ProjectRunner(store, lambda *_: None)
    answered = []
    try:
        item = runner._open_inbox('requirements', answered.append, turn=None,
                                 revision=review.requirements_revision(tmp_path), question='Approve requirements?',
                                 choices=list(review.REQUIREMENTS_CHOICES))
        assert runner.answer(item, 'Approve requirements')
        state = store.state()
        assert state['requirements_approved'] == review.requirements_revision(tmp_path)
        if changed:
            assert state['plan_approved'] is None and state['plan_execution'] is None
            assert not state['plan_review_required']  # A stale plan is not offered before replanning.
        else:
            assert state['plan_approved'] == plan
            assert state['plan_execution'] == {'plan': plan, 'requirements': requirements}
    finally:
        runner.shutdown()


def test_anonymous_task_cannot_bypass_plan_gate(tmp_path, monkeypatch):
    store, requirements, _ = project(tmp_path)
    store.update_state(requirements_approved=requirements, plan_review_required=True)
    monkeypatch.setattr('lyra_lite.agents.agent_for_goal', lambda _: None)
    monkeypatch.setattr('lyra_lite.settings.resolve_agent_model', lambda *a: pytest.fail('Unapproved anonymous task reached provider'))
    result = json.loads(dispatch_project_tasks(store, None, {'goal': 'Unclassified assignment'}))
    assert 'implementation plan' in result['error']
