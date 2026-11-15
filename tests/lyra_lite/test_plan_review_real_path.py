"""The plan is visible, its exact revision is approved, and only then may development start."""
import pytest

from lyra_lite import review
from lyra_lite.store import ProjectStore
from tests.fakes.fake_openai_server import FakeOpenAIServer, text_step, tool_step
from tests.lyra_lite.test_lyrad_real_path import Daemon, _wait_event, _write_config, env  # noqa: F401


@pytest.mark.parametrize('status,current_chat,restored', [
    ('open', True, True), ('expired', True, True),
    ('answered', True, False), ('expired', False, False),
])
def test_restart_migrates_unanswered_legacy_plan_questions(env, status, current_chat, restored):
    with FakeOpenAIServer([]) as llm:
        _write_config(env['hermes_home'], llm.base_url, lyra_lite={'watchdog': {'enabled': False}})
        root = env['home'] / 'Legacy plan'
        (root / '.sdlc').mkdir(parents=True)
        (root / 'requirements.md').write_text('# Requirements\nBuild a dashboard.\n')
        (root / 'prototypes').mkdir()
        (root / 'prototypes/index.html').write_text('<button>Load data</button>')
        plan_text = '# Plan\nImplement the approved dashboard.\n'
        (root / '.sdlc/task-graph.md').write_text(plan_text)
        store = ProjectStore(root).init()
        store.update_state(requirements_approved=review.requirements_revision(root), requirements_revision_format=2,
                           prototype_approved=review.prototype_revision(root), requirements_review=False)
        legacy = store.add_inbox('question', question='Do you approve this implementation plan?',
                                 choices=list(review.PLAN_CHOICES),
                                 **({} if current_chat else {'chat_id': 'previous-chat'}))
        if status != 'open':
            store.close_inbox(legacy['id'], status)
        daemon = Daemon(env).start()
        try:
            added = daemon.post('/api/projects', {'path': str(root), 'create': False})
            assert added.is_success
            prefix = '/api/projects/' + added.json()['id']
            cards = daemon.get(prefix).json()['inbox']
            assert bool(cards) is restored
            if restored:
                assert cards[0]['kind'] == 'plan'
                assert plan_text in cards[0]['question']
                assert not store.state().get('plan_approved')
                # A further restart offers recovery of this exact review rather than duplicating it.
                daemon.stop()
                daemon = Daemon(env).start()
                detail = daemon.get(prefix).json()
                assert detail['inbox'] == []
                assert detail['review_recovery']['id'] == cards[0]['id']
            assert not llm.main_requests()
        finally:
            daemon.stop()


def test_plan_card_contains_the_actual_document_and_blocks_blind_or_stale_approval(env):
    with FakeOpenAIServer([]) as llm:
        _write_config(env['hermes_home'], llm.base_url, lyra_lite={'watchdog': {'enabled': False}})
        root = env['home'] / 'Visible plan'
        (root / '.sdlc').mkdir(parents=True)
        (root / 'requirements.md').write_text('# Requirements\nBuild a CSV dashboard.\n')
        (root / 'prototypes').mkdir()
        (root / 'prototypes/index.html').write_text('<button>Load CSV</button>')
        plan_text = '# Implementation plan\n\n## Step 1\nImplement CSV import in src/import.js.\n\n## Checks\nRun the import tests.\n'
        plan_file = root / '.sdlc/task-graph.md'
        plan_file.write_text(plan_text)
        store = ProjectStore(root).init()
        store.update_state(requirements_approved=review.requirements_revision(root), requirements_revision_format=2,
                           prototype_approved=review.prototype_revision(root), requirements_review=False, plan_review_required=True)
        goal = 'sw-developer: Begin the approved Step 1'
        target = root / 'src/import.js'
        llm.script = [tool_step('delegate_task', {'goal': goal}), text_step('Development started.'), text_step('Step 1 report received.')]
        llm.side_scripts = {goal: [tool_step('write_file', {'path': str(target), 'content': 'export const sample = true;'}), text_step('Step 1 completed in test.') ]}
        daemon = Daemon(env).start()
        try:
            added = daemon.post('/api/projects', {'path': str(root), 'create': False})
            assert added.is_success
            prefix = '/api/projects/' + added.json()['id']
            item, = daemon.get(prefix).json()['inbox']
            assert item['kind'] == 'plan' and plan_text in item['question']
            assert not llm.main_requests()
            assert daemon.post(prefix + '/inbox/' + item['id'], {'answer': 'Approve implementation plan'}).status_code == 409
            plan_file.write_text(plan_text + '\nAdd a new unreviewed step.\n')
            answer = {'choice': 'Approve implementation plan', 'revision': item['revision']}
            assert daemon.post(prefix + '/inbox/' + item['id'], {'answer': answer}).status_code == 409
            assert not target.exists()
            plan_file.write_text(plan_text)
            assert daemon.post(prefix + '/inbox/' + item['id'], {'answer': answer}).is_success
            _wait_event(root, lambda e: e['type'] == 'helper' and e.get('event') == 'reported')
            assert target.read_text() == 'export const sample = true;'
        finally:
            daemon.stop()


def test_executed_plan_can_evolve_through_delivery_and_restart_without_new_approval(env):
    goal = "sw-developer: Implement and verify the approved editor"
    with FakeOpenAIServer([], side_scripts={goal: [
        tool_step("write_file", {"path": "plan.md", "content": "# Plan\nVerified implementation details.\n"}),
        text_step("Approved implementation and tests finished."),
    ]}) as llm:
        _write_config(env['hermes_home'], llm.base_url, lyra_lite={'watchdog': {'enabled': False}})
        root = env['home'] / 'Completed editor'
        root.mkdir()
        (root / 'requirements.md').write_text('# Requirements\nEdit documents.\n')
        (root / 'plan.md').write_text('# Plan\nImplement and test the editor.\n')
        store = ProjectStore(root).init()
        store.update_state(requirements_approved=review.requirements_revision(root), requirements_revision_format=2,
                           requirements_review=False, plan_review_required=True)
        llm.script = [tool_step('delegate_task', {'goal': goal}), text_step('Implementation running.'),
                      text_step('Your app is ready.')]
        daemon = Daemon(env).start()
        try:
            prefix = '/api/projects/' + daemon.post('/api/projects', {'path': str(root), 'create': False}).json()['id']
            item, = daemon.get(prefix).json()['inbox']
            assert daemon.post(prefix + '/inbox/' + item['id'], {'answer': {
                'choice': 'Approve implementation plan', 'revision': item['revision'],
            }}).is_success
            _wait_event(root, lambda e: e['type'] == 'turn_end' and e.get('reply') == 'Your app is ready.')
            detail = daemon.get(prefix).json()
            assert detail['inbox'] == [] and detail['review_recovery'] is None
            assert store.state()['plan_approved'] != review.implementation_plan(root)['revision']
            requests = len(llm.main_requests())
            daemon.stop()
            daemon = Daemon(env).start()
            detail = daemon.get(prefix).json()
            assert detail['inbox'] == [] and detail['review_recovery'] is None
            assert len(llm.main_requests()) == requests
        finally:
            daemon.stop()
