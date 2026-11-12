"""Prototype approval -> visible requirements -> metadata edit -> actual task planning."""
import json

import pytest

from lyra_lite.review import PROTOTYPE_CHOICES, requirements_revision
from tests.fakes.fake_openai_server import FakeOpenAIServer, text_step, tool_step
from tests.lyra_lite.test_requirements_approval import DRAFT, APPROVED
from tests.lyra_lite.test_lyrad_real_path import Daemon, _events, _new_project, _wait_event, _write_config, env  # noqa: F401
from lyra_lite.store import ProjectStore


@pytest.mark.parametrize("start_agent", [True, False])
def test_acknowledgement_only_model_cannot_strand_either_approval(env, start_agent):
    goal = 'task-planner: Plan approved app'
    with FakeOpenAIServer([], side_scripts={goal: [text_step('Plan: import, analyse, report, and verify compatibility.')]}) as llm:
        _write_config(env['hermes_home'], llm.base_url, lyra_lite={'watchdog': {'enabled': False}})
        daemon = Daemon(env).start()
        try:
            pid, root = _new_project(daemon, env, 'Approval handoff')
            (root / 'prototypes').mkdir()
            (root / 'prototypes/index.html').write_text('<button>Load CSV</button>')
            (root / 'requirements.md').write_text(DRAFT)
            llm.script = [
                tool_step('clarify', {'question': 'Approve prototype?', 'choices': list(PROTOTYPE_CHOICES)}),
                text_step('Prototype approved; requirements approval is next.'),
                tool_step('write_file', {'path': str(root / 'requirements.md'), 'content': APPROVED}, call_id='status'),
                text_step('Requirements approved. Planning is next.'),
                *([tool_step('delegate_task', {'goal': goal}, call_id='plan'),
                   text_step('Planning has started.'), text_step('Task plan received.')]
                  if start_agent else [text_step('Planning is next again.')]),
            ]
            prefix = f'/api/projects/{pid}'
            assert daemon.post(prefix + '/messages', {'text': 'Review the app prototype'}).is_success
            prototype = _wait_event(root, lambda e: e['type'] == 'inbox' and e['item']['kind'] == 'prototype')['item']
            viewed = daemon.post(prefix + '/preview/prototype', {}).json()
            assert daemon.post(prefix + '/inbox/' + prototype['id'], {'answer': {
                'choice': 'Approve prototype', 'revision': viewed['revision'],
            }}).is_success
            requirements = _wait_event(root, lambda e: e['type'] == 'inbox' and e['item']['kind'] == 'requirements')['item']
            assert DRAFT in requirements['question']
            assert len(llm.main_requests()) == 2  # Showing the next card requires no extra AI call.
            assert not any(e['type'] == 'helper' for e in _events(root))
            assert daemon.post(prefix + '/inbox/' + requirements['id'], {'answer': 'Approve requirements'}).is_success
            if start_agent:
                worker = _wait_event(root, lambda e: e['type'] == 'helper' and e.get('event') == 'start' and e.get('goal') == goal)
                assert worker['model']
                _wait_event(root, lambda e: e['type'] == 'turn_end' and e.get('reply') == 'Task plan received.')
            else:
                problem = _wait_event(root, lambda e: e['type'] == 'problem' and e.get('kind') == 'workflow_stalled')
                assert 'No work is running' in problem['text']
                _wait_event(root, lambda e: e['type'] == 'turn_end' and e.get('reply') == 'Planning is next again.')
                assert len(llm.main_requests()) == 5
                assert daemon.get(prefix).json()['queue'] == []
            state = json.loads((root / '.lyra/state.json').read_text())
            assert state['requirements_approved'] == requirements_revision(root)
            assert state.get('approval_followup') is None
            handoffs = [e for e in _events(root) if e['type'] == 'turn_start' and e.get('kind') == 'approval_continue']
            assert len(handoffs) == 1
            if start_agent:
                assert not any(e['type'] == 'problem' and e.get('kind') == 'workflow_stalled' for e in _events(root))
        finally:
            daemon.stop()


def test_model_opened_requirements_card_contains_the_actual_draft_and_reopens_after_restart(env):
    from lyra_lite.review import REQUIREMENTS_CHOICES, prototype_revision

    with FakeOpenAIServer([]) as llm:
        _write_config(env['hermes_home'], llm.base_url, lyra_lite={'watchdog': {'enabled': False}})
        daemon = Daemon(env).start()
        try:
            pid, root = _new_project(daemon, env, 'Visible requirements')
            (root / 'prototypes').mkdir()
            (root / 'prototypes/index.html').write_text('<button>Try task list</button>')
            (root / 'requirements.md').write_text(DRAFT)
            ProjectStore(root).update_state(project_kind='app', requirements_review=True,
                                           prototype_approved=prototype_revision(root))
            llm.script = [tool_step('clarify', {'question': 'Approve these requirements?',
                                               'choices': list(REQUIREMENTS_CHOICES)})]
            prefix = f'/api/projects/{pid}'
            assert daemon.post(prefix + '/messages', {'text': 'Show requirements review'}).is_success
            item = _wait_event(root, lambda e: e['type'] == 'inbox' and e['item']['kind'] == 'requirements')['item']
            assert DRAFT in item['question']
            assert DRAFT in daemon.get(prefix).json()['inbox'][0]['question']
            daemon.stop()
            daemon = Daemon(env).start()
            assert daemon.get(prefix).json()['review_recovery']['id'] == item['id']
            assert daemon.post(prefix + '/review/reopen', {'item_id': item['id']}).is_success
            assert DRAFT in daemon.get(prefix).json()['inbox'][0]['question']
        finally:
            daemon.stop()
