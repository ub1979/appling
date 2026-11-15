"""Approved new scope -> guarded plan -> real workers/merge -> QA -> restart.

Only the model is scripted. HTTP, Hermes, file tools, RPC, worktrees and saved
approval decisions all use the actual implementations.
"""
import json
import threading

from lyra_lite import review
from lyra_lite.development import git
from lyra_lite.store import ProjectStore
from tests.fakes.fake_openai_server import FakeOpenAIServer, text_step, tool_step
from tests.lyra_lite.test_lyrad_real_path import Daemon, _events, _wait_event, _write_config, env  # noqa: F401


def replay_model():
    coding = [{'goal': f'REPLAY-CODE-{c}', 'context': json.dumps({
        'owned_paths': [f'replay-{c}.txt'], 'instructions': 'Write the assigned replay file.'})} for c in 'AB']
    checking = [{'goal': f'REPLAY-READ-{c}', 'context': json.dumps({
        'read_only': True, 'instructions': f'Read replay-{c}.txt without changing files.'})} for c in 'AB']
    llm = FakeOpenAIServer([], side_scripts={
        'REPLAY-LEAD': [tool_step('read_file', {'path': 'plan.md'}),
            tool_step('execute_code', {'code': 'from hermes_tools import read_file\nprint(len(read_file("plan.md")["content"]))'}, call_id='ptc'),
            tool_step('delegate_task', {'tasks': coding}, call_id='wave'), text_step('REPLAY DEV COMPLETE')],
        **{f'REPLAY-CODE-{c}': [{**tool_step('write_file', {'path': f'replay-{c}.txt', 'content': f'worker {c}\n'}), 'parallel_code': True},
                                text_step(f'Worker {c} finished.')] for c in 'AB'},
        'REPLAY-QA-LEAD': [tool_step('delegate_task', {'tasks': checking}), text_step('REPLAY QA COMPLETE')],
        **{f'REPLAY-READ-{c}': [{**tool_step('read_file', {'path': f'replay-{c}.txt'}), 'parallel_qa': True},
                                text_step(f'Checked worker {c}.')] for c in 'AB'},
    })
    next_step = llm.next_step
    barriers = {key: threading.Barrier(2, timeout=40) for key in ['parallel_code', 'parallel_qa']}
    def simultaneous(body):
        step = next_step(body)
        for key, barrier in barriers.items():
            if step.get(key):
                barrier.wait()
        return step
    llm.next_step = simultaneous
    return llm


def exercise_update_pipeline(env, root, llm):
    """Also used by the one-off replay of the user's copied project state."""
    _write_config(env['hermes_home'], llm.base_url, lyra_lite={
        'watchdog': {'enabled': False},
        'agent_models': {role: {'provider': 'custom', 'model': 'fake-model'}
                         for role in ['sw-developer', 'qa-engineer']}})
    daemon = Daemon(env).start()
    try:
        added = daemon.post('/api/projects', {'path': str(root), 'create': False})
        assert added.is_success, added.text
        prefix = '/api/projects/' + added.json()['id']
        card, = daemon.get(prefix).json()['inbox']
        assert card['kind'] == 'plan'
        assert card['requirements'] == review.requirements_revision(root)
        assert card['revision'] == review.implementation_plan(root)['revision']
        assert not review.plan_execution_started(ProjectStore(root).state())
        # Attempt a premature handoff through the same host dispatcher the
        # model uses. Composer messages at this checkpoint are owner feedback,
        # so they intentionally resolve the review as Request changes.
        from lyra_lite.delegation import dispatch_project_tasks
        before = len(_events(root))
        blocked = json.loads(dispatch_project_tasks(ProjectStore(root), None,
                                                   {'goal': 'sw-developer: REPLAY-LEAD'}))
        assert 'implementation plan' in blocked['error']
        assert not [e for e in _events(root)[before:] if e['type'] == 'helper' and e.get('event') == 'start']
        assert daemon.post(prefix + '/inbox/' + card['id'], {'answer': {
            'choice': 'Approve implementation plan', 'revision': 'incorrect-revision'}}).status_code == 409
        llm.script = [tool_step('delegate_task', {'goal': 'sw-developer: REPLAY-LEAD'}), text_step('Replay coding is running.'),
                      tool_step('delegate_task', {'goal': 'qa-engineer: REPLAY-QA-LEAD'}, call_id='qa'),
                      text_step('Replay QA is running.'), text_step('REPLAY COMPLETE')]
        approved = daemon.post(prefix + '/inbox/' + card['id'], {'answer': {
            'choice': 'Approve implementation plan', 'revision': card['revision']}})
        assert approved.is_success, approved.text
        # The live execute_code permission guard remains in force. Simulate
        # the owner's one-shot decision only inside this disposable replay.
        permission = _wait_event(root, lambda e: e['type'] == 'inbox'
            and e['item'].get('kind') == 'approval'
            and e['item'].get('requester', {}).get('goal') == 'sw-developer: REPLAY-LEAD', 40)['item']
        assert daemon.post(prefix + '/inbox/' + permission['id'], {'answer': 'once'}).is_success
        _wait_event(root, lambda e: e['type'] == 'turn_end' and e.get('reply') == 'REPLAY COMPLETE', 120)
        for c in 'AB':
            assert (root / f'replay-{c}.txt').read_text() == f'worker {c}\n'
        events = _events(root)[before:]
        starts = [e for e in events if e['type'] == 'helper' and e.get('event') == 'start']
        assert sum(e.get('goal', '').startswith('REPLAY-CODE-') and bool(e.get('parent_id')) for e in starts) == 2
        assert sum(e.get('goal', '').startswith('REPLAY-READ-') and bool(e.get('parent_id')) for e in starts) == 2
        waves = [json.loads(p.read_text()) for p in (root / '.lyra/development').glob('*/wave.json')]
        assert any(w.get('integrated') for w in waves)
        assert any(w.get('validated_baseline') for w in waves)
        assert review.plan_execution_started(ProjectStore(root).state())
        ptc = [e for e in events if e['type'] == 'helper' and e.get('tool') == 'execute_code']
        assert ptc
        for marker, field, expected in [('REPLAY-LEAD', 'ptc', None),
                                        ('REPLAY-READ-A', 'call_1', 'worker A'),
                                        ('REPLAY-READ-B', 'call_1', 'worker B')]:
            replies = []
            for request in llm.main_requests():
                first = next((str(m.get('content', '')) for m in request['messages'] if m['role'] == 'user'), '')
                if marker not in first:
                    continue
                replies.extend(json.loads(m['content']) for m in request['messages']
                               if m['role'] == 'tool' and m.get('tool_call_id') == field)
            assert replies, marker
            if expected is None:
                assert all(r.get('status') == 'success' and r.get('tool_calls_made') == 1 for r in replies)
            else:
                assert all(expected in r.get('content', '') for r in replies)
        assert not [e for e in events if e['type'] == 'turn_end' and e.get('status') == 'error']
        assert not daemon.get(prefix).json()['inbox']
        assert daemon.get('/api/settings').json()['parallel_work']['active'] == 0
        count = len(llm.main_requests())
        daemon.stop()
        daemon = Daemon(env).start()
        assert daemon.get(prefix).json()['inbox'] == []
        assert len(llm.main_requests()) == count  # No repeated approval or coding on restart.
        return {'coding_workers': 2, 'qa_workers': 2, 'plan_gate': 'enforced',
                'file_rpc_after_chat_read': 'passed', 'checked_merge': 'passed', 'restart': 'passed'}
    finally:
        daemon.stop()


def test_changed_scope_uses_new_plan_then_parallel_development_and_qa(env):
    import hashlib
    root = env['home'] / 'Updated editor'
    root.mkdir()
    old = '# Requirements\nEdit local documents.\n\n## Approval gates and current state\nApproved baseline.\n'
    (root / 'requirements.md').write_text(old)
    (root / 'plan.md').write_text('# Plan\nImplement old editor.\n')
    store = ProjectStore(root).init()
    old_scope = hashlib.sha256(review._requirements_content(old, include_nested=False).encode()).hexdigest()
    old_plan = review.implementation_plan(root)['revision']
    store.update_state(requirements_approved=old_scope, requirements_revision_format=2,
                       plan_approved=old_plan, plan_requirements=old_scope, plan_review_required=True,
                       plan_execution={'plan': old_plan, 'requirements': old_scope})
    changed = old + '\n### New menu scope\nProvide Open Recent without deleting projects.\n'
    (root / 'requirements.md').write_text(changed)
    card = store.add_inbox('requirements', revision=old_scope, question='Review.\n\n---\n\n' + changed)
    store.close_inbox(card['id'], 'answered', answer='Approve requirements')
    (root / 'plan.md').write_text('# Plan\nImplement the new menu, then independent QA.\n')
    git(root, 'init')
    git(root, 'add', 'requirements.md', 'plan.md')
    git(root, 'commit', '-m', 'Replay approved scope and new plan')
    with replay_model() as llm:
        result = exercise_update_pipeline(env, root, llm)
        assert result['coding_workers'] == result['qa_workers'] == 2
