"""Controller proof: approved criteria decide what may wait; setup never excuses missing code."""
import json
import subprocess
import time
import sys
from pathlib import Path

import pytest

from appling import acceptance, checkpoints
from appling.store import Store
from appling.workflow import Workflow, artifact_revision, source_revision
from test_workflow import approve, wait_idle

REQUIREMENTS = '# App\n\n- FR-1: Show the saved number.\n- FR-2: Post the number to the owner account.\n'
CRITERIA = [
    dict(id='AC-FR-1-1', requirement='FR-1', description='Number 42 is shown', release='1', live=False, prerequisites=[]),
    dict(id='AC-FR-2-1', requirement='FR-2', description='A reviewed post reaches the real account', release='1', live=True,
         prerequisites=['P-login']),
]
PREREQS = [dict(id='P-login', kind='account', description='Sign in to the posting account', needed_at='verification')]


class Engine:
    """Deterministic engine. QA reports per-criterion results from real files."""

    def __init__(self, criteria=CRITERIA, owner_blocker=True):
        self.calls = []
        self.criteria = criteria
        self.owner_blocker = owner_blocker
        self.implemented = True      # whether the FR-2 adapter code exists
        self.live_ok = True          # whether a real live check would pass once setup is ready
        self.failed_check = None     # None | 'linked' | 'unlinked' failing builder check
        self.impl_blocker = False    # builder cannot finish the FR-2 adapter
        self.drop_requirement = False
        self.rescope_prompts = []

    @staticmethod
    def scope_resolved(root):
        spec = root / acceptance.SPEC
        return spec.exists() and any(c['release'] == 'later' for c in json.loads(spec.read_text())['criteria'])

    def __call__(self, connection, run):
        brief = json.loads(run.prompt)
        role = run.instructions.split('Role: ', 1)[1].splitlines()[0]
        self.calls.append(role)
        root = run.root
        if role == 'req-engineer' and 'Owner decision:' in run.prompt:
            self.rescope_prompts.append(run.prompt)
            if self.drop_requirement:
                return dict(requirements='# App\n\n- FR-1: Show the saved number.\n', acceptance_criteria=[CRITERIA[0]], prerequisites=PREREQS)
            later = [dict(c, release='later') if c['requirement'] == 'FR-2' else c for c in self.criteria]
            return dict(summary='FR-2 moved to later', requirements=REQUIREMENTS.replace('account.', 'account. Release: later'),
                        acceptance_criteria=later, prerequisites=PREREQS)
        if role == 'req-engineer':
            return dict(requirements=REQUIREMENTS, acceptance_criteria=self.criteria, prerequisites=PREREQS)
        if role == 'ui-designer':
            p = root / 'prototypes/index.html'; p.parent.mkdir(exist_ok=True)
            p.write_text('<button>42</button>')
            return dict(status='completed')
        if role == 'sw-developer':
            (root / 'number.txt').write_text('42')
            if self.implemented:
                (root / 'poster.py').write_text('def post(number, client):\n    return client.send(str(number))\n')
            evidence = root / '.sdlc/evidence/direct-build/build.txt'
            evidence.parent.mkdir(parents=True, exist_ok=True)
            # Real receipts differ every run; progress detection must not depend on bytes.
            evidence.write_text(f'command: unit tests\nexit: 0\nok at {time.time_ns()}\n')
            blockers = [dict(kind='owner_setup', detail='Owner must sign in to the posting account', criteria=['AC-FR-2-1'])] \
                if self.owner_blocker else []
            if self.impl_blocker and not self.scope_resolved(root):
                blockers.insert(0, dict(kind='implementation', detail='Posting adapter needs the real site to finish',
                                        criteria=['AC-FR-2-1'], next_action='Build the account posting adapter'))
            checks = [dict(command='unit tests', exit_code=0, evidence='.sdlc/evidence/direct-build/build.txt')]
            if self.failed_check:
                failed = root / '.sdlc/evidence/direct-build/live.txt'
                failed.write_text('command: live post\nexit: 1\nnot signed in\n')
                checks.append(dict(command='live post', exit_code=1, evidence='.sdlc/evidence/direct-build/live.txt',
                                   **({'criteria': ['AC-FR-2-1']} if self.failed_check == 'linked' else {})))
            return dict(status='blocked' if blockers else 'completed', summary='handoff', checks=checks, blockers=blockers)
        folder = root / brief['worker']['evidence']; folder.mkdir(parents=True, exist_ok=True)
        local = folder / 'local.txt'
        local.write_text('command: local checks\nexit: 0\n')
        rel = str(local.relative_to(root))
        if role != 'qa-engineer':
            return dict(verdict='pass', summary='review', checks=[dict(command='review', exit_code=0, evidence=rel)], findings=[])
        entries = [dict(id='AC-FR-1-1', status='passed', implemented=True, command='local checks', exit_code=0, evidence=rel)]
        has_code = (root / 'poster.py').exists()
        if not has_code:
            entries.append(dict(id='AC-FR-2-1', status='pending_owner', implemented=False, command='local checks', exit_code=0, evidence=rel))
        elif self.ready:
            live = folder / 'live.txt'; live.write_text('command: live post\nexit: 0\n' if self.live_ok else 'command: live post\nexit: 1\n')
            entries.append(dict(id='AC-FR-2-1', status='passed' if self.live_ok else 'failed', implemented=True,
                                command='live post', exit_code=0 if self.live_ok else 1, evidence=str(live.relative_to(root))))
        else:
            entries.append(dict(id='AC-FR-2-1', status='pending_owner', implemented=True, command='local checks', exit_code=0,
                                evidence=rel, next_action='Sign in, then verify the live post'))
        verdict = 'pass' if all(e['status'] == 'passed' for e in entries) else \
            'fail' if any(e['status'] == 'failed' for e in entries) else 'blocked'
        return dict(verdict=verdict, summary='qa', browser_tested=True, criteria=entries,
                    checks=[dict(command='local checks', exit_code=0, evidence=rel, requirements=['FR-1'])],
                    findings=[dict(description='live post failed')] if verdict == 'fail' else [])

    ready = False


def make(tmp_path, engine):
    store = Store(tmp_path / 'state')
    state = store.add(tmp_path / 'app')
    workflow = Workflow(store, engine)
    return store, workflow, state['id']


def to_build(store, workflow, pid):
    workflow.submit(pid, 'Build a number poster'); wait_idle(workflow, pid)
    approve(store, workflow, pid, 'prototype'); approve(store, workflow, pid, 'requirements')


def test_criteria_are_part_of_the_requirements_approval(tmp_path):
    engine = Engine(); store, workflow, pid = make(tmp_path, engine)
    try:
        workflow.submit(pid, 'Build'); wait_idle(workflow, pid)
        root = Path(store.get(pid)['root'])
        assert json.loads((root / acceptance.SPEC).read_text())['criteria'][1]['live'] is True
        approve(store, workflow, pid, 'prototype')
        review = store.inbox(pid)[0]
        assert 'AC-FR-2-1' in review['question'] and 'Sign in to the posting account' in review['question']
        before = artifact_revision(root, 'requirements')
        spec = json.loads((root / acceptance.SPEC).read_text())
        spec['criteria'][1]['live'] = False   # a model quietly weakening a criterion
        (root / acceptance.SPEC).write_text(json.dumps(spec))
        assert artifact_revision(root, 'requirements') != before
        with pytest.raises(ValueError, match='changed'):
            workflow.answer(pid, review['id'], {'choice': 'Approve requirements', 'revision': review['revision']})
    finally:
        workflow.shutdown()


def test_owner_only_blockers_reach_qa_and_end_implementation_verified_not_delivered(tmp_path):
    engine = Engine(); store, workflow, pid = make(tmp_path, engine)
    try:
        to_build(store, workflow, pid)
        state = store.get(pid)
        assert state['phase'] == 'implementation_verified', [m['content'] for m in store.messages(pid)][-3:]
        assert engine.calls.count('sw-developer') == 1 and 'qa-engineer' in engine.calls
        status = workflow.acceptance_status(pid)
        assert status['results']['AC-FR-1-1']['status'] == 'passed'
        assert status['results']['AC-FR-2-1']['status'] == 'pending_owner'
        assert status['results']['AC-FR-2-1']['owner'] == 'you'
        assert status['outcome'] == 'pending_owner'
        assert any('not delivered' in m['content'] for m in store.messages(pid))
        assert any(m['content'].startswith('Coding can proceed on 1') for m in store.messages(pid))
    finally:
        workflow.shutdown()


def test_setup_done_runs_verification_only_and_delivers_on_passing_live_evidence(tmp_path):
    engine = Engine(); store, workflow, pid = make(tmp_path, engine)
    try:
        to_build(store, workflow, pid)
        assert store.get(pid)['phase'] == 'implementation_verified'
        builds = engine.calls.count('sw-developer')
        engine.ready = True
        workflow.set_prerequisite(pid, 'P-login', True); wait_idle(workflow, pid)
        assert engine.calls.count('sw-developer') == builds   # verification only
        assert store.get(pid)['phase'] == 'delivered'
        assert workflow.acceptance_status(pid)['outcome'] == 'passed'
    finally:
        workflow.shutdown()


def test_failed_live_check_after_setup_returns_to_build_and_never_delivers(tmp_path):
    engine = Engine(); store, workflow, pid = make(tmp_path, engine)
    try:
        to_build(store, workflow, pid)
        engine.ready = True; engine.live_ok = False
        workflow.set_prerequisite(pid, 'P-login', True); wait_idle(workflow, pid)
        assert store.get(pid)['phase'] != 'delivered'
        assert engine.calls.count('sw-developer') > 1
    finally:
        workflow.shutdown()


def test_missing_implementation_cannot_hide_behind_owner_setup(tmp_path):
    engine = Engine(); engine.implemented = False
    store, workflow, pid = make(tmp_path, engine)
    try:
        to_build(store, workflow, pid)
        state = store.get(pid)
        assert state['phase'] != 'implementation_verified' and state['phase'] != 'delivered'
        results = acceptance.load_results(Path(state['root']))
        assert results['AC-FR-2-1']['status'] == 'failed'
        assert engine.calls.count('sw-developer') >= 2   # sent back for repair
    finally:
        workflow.shutdown()


def test_builder_blocker_label_alone_cannot_defer_without_approved_live_criterion(tmp_path):
    local_only = [dict(c, live=False, prerequisites=[]) for c in CRITERIA]
    engine = Engine(criteria=local_only); store, workflow, pid = make(tmp_path, engine)
    try:
        to_build(store, workflow, pid)
        state = store.get(pid)
        assert state['phase'] == 'build' and state['paused']
        assert 'qa-engineer' not in engine.calls
        assert state['attention']['blockers'][0]['owner'] == 'you'
        assert 'cannot be deferred' in state['attention']['message']
    finally:
        workflow.shutdown()


def test_no_progress_guard_pauses_and_recorded_setup_allows_a_retry(tmp_path):
    local_only = [dict(c, live=False, prerequisites=[]) for c in CRITERIA]
    engine = Engine(criteria=local_only); store, workflow, pid = make(tmp_path, engine)
    try:
        to_build(store, workflow, pid)
        assert engine.calls.count('sw-developer') == 1
        workflow.submit(pid, 'Continue'); wait_idle(workflow, pid)
        assert engine.calls.count('sw-developer') == 2
        assert 'No progress since the previous attempt' in store.get(pid)['attention']['message']
        workflow.submit(pid, 'Continue'); wait_idle(workflow, pid)
        assert engine.calls.count('sw-developer') == 2      # third identical attempt is not run
        assert store.get(pid)['attention']['reason'] == 'no_progress'
        # A real change (owner setup recorded in project state) permits another attempt.
        store.update(pid, prerequisites_done={'P-login': 1})
        workflow.submit(pid, 'Signed in now'); wait_idle(workflow, pid)
        assert engine.calls.count('sw-developer') == 3
    finally:
        workflow.shutdown()


def test_source_change_turns_old_results_into_not_run_and_reverifies(tmp_path):
    engine = Engine(); store, workflow, pid = make(tmp_path, engine)
    try:
        to_build(store, workflow, pid)
        root = Path(store.get(pid)['root'])
        (root / 'number.txt').write_text('43')
        status = workflow.acceptance_status(pid)
        assert status['results']['AC-FR-1-1']['status'] == 'not_run' and status['results']['AC-FR-1-1']['stale']
        qa_runs = engine.calls.count('qa-engineer')
        workflow.submit(pid, 'Check again'); wait_idle(workflow, pid)
        assert engine.calls.count('qa-engineer') == qa_runs + 1
        assert 'change-manager' not in engine.calls
    finally:
        workflow.shutdown()


def test_criteria_command_adds_criteria_and_requires_reapproval(tmp_path):
    engine = Engine(criteria=None, owner_blocker=False)
    original = Engine.__call__

    def call(self, connection, run):
        role = run.instructions.split('Role: ', 1)[1].splitlines()[0]
        if role == 'req-engineer' and 'already written' in run.prompt:
            self.calls.append(role)
            return dict(acceptance_criteria=CRITERIA, prerequisites=PREREQS)
        if role == 'req-engineer':
            self.calls.append(role)
            return dict(requirements=REQUIREMENTS)
        return original(self, connection, run)
    engine.__class__ = type('LegacyEngine', (Engine,), {'__call__': call})
    store, workflow, pid = make(tmp_path, engine)
    try:
        workflow.submit(pid, 'Build'); wait_idle(workflow, pid)
        root = Path(store.get(pid)['root'])
        assert not (root / acceptance.SPEC).exists()
        approve(store, workflow, pid, 'prototype'); approve(store, workflow, pid, 'requirements')
        assert workflow.acceptance_status(pid)['derived']
        workflow.submit(pid, '/criteria'); wait_idle(workflow, pid)
        assert (root / acceptance.SPEC).exists()
        assert 'requirements' not in store.get(pid)['approvals']
        assert store.inbox(pid)[0]['kind'] == 'requirements'
        assert (root / 'requirements.md').read_text() == REQUIREMENTS
    finally:
        workflow.shutdown()


def test_normalize_rejects_unrecorded_live_and_uncovered_requirements():
    with pytest.raises(ValueError, match='prerequisite'):
        acceptance.normalize([dict(CRITERIA[1], prerequisites=[])], PREREQS, REQUIREMENTS)
    with pytest.raises(ValueError, match='FR-2'):
        acceptance.normalize([CRITERIA[0]], PREREQS, REQUIREMENTS)
    with pytest.raises(ValueError, match='unknown requirement'):
        acceptance.normalize([*CRITERIA, dict(CRITERIA[0], id='AC-X-1', requirement='FR-9')], PREREQS, REQUIREMENTS)
    spec = acceptance.normalize(CRITERIA, PREREQS, REQUIREMENTS)
    assert [c['id'] for c in acceptance.release_one(spec)] == ['AC-FR-1-1', 'AC-FR-2-1']


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, check=True).stdout


def test_checkpoint_keeps_owner_staging_and_skips_secrets_and_generated_files(tmp_path):
    root = tmp_path / 'repo'; root.mkdir()
    git(root, 'init', '-q', '-b', 'main')
    git(root, 'config', 'user.email', 'owner@example.test'); git(root, 'config', 'user.name', 'Owner')
    (root / '.gitignore').write_text('ignored.txt\n')
    (root / 'app.py').write_text('v1\n'); (root / 'notes.md').write_text('n1\n')
    git(root, 'add', '.'); git(root, 'commit', '-qm', 'base')
    (root / 'app.py').write_text('v2\n')                 # builder edit, unstaged
    (root / 'notes.md').write_text('owner staged\n'); git(root, 'add', 'notes.md')
    (root / 'notes.md').write_text('owner staged then edited\n')
    (root / 'new.py').write_text('new\n')
    (root / '.env').write_text('SECRET=1\n'); (root / '.env.example').write_text('SECRET=\n')
    (root / 'data.sqlite').write_text('db'); (root / 'ignored.txt').write_text('x')
    (root / 'node_modules').mkdir(); (root / 'node_modules' / 'x.js').write_text('x')
    outside = tmp_path / 'models'; outside.mkdir(); (outside / 'w.bin').write_text('w')
    (root / 'models').symlink_to(outside)
    (root / '.sdlc/evidence').mkdir(parents=True); (root / '.sdlc/evidence/log.txt').write_text('token=abc')
    (root / '.sdlc/handoffs').mkdir(); (root / '.sdlc/handoffs/next.json').write_text('{}')
    saved = checkpoints.checkpoint(root, 'Appling checkpoint', 'demo')
    assert saved['changed'] and saved['branch_updated']
    files = set(git(root, 'ls-tree', '-r', '--name-only', 'HEAD').split())
    assert {'app.py', 'new.py', '.env.example', 'notes.md'} <= files
    assert not files & {'.env', 'data.sqlite', 'ignored.txt', 'node_modules/x.js', 'models', '.sdlc/evidence/log.txt'}
    assert '.sdlc/handoffs/next.json' in files
    assert git(root, 'show', 'HEAD:app.py') == 'v2\n'
    # The owner's staged version of notes.md is untouched in their index.
    assert git(root, 'show', ':notes.md') == 'owner staged\n'
    status = git(root, 'status', '--porcelain')
    assert ' app.py' not in status and 'app.py' not in status   # no phantom staged reversal
    assert checkpoints.checkpoint(root, 'again', 'demo')['changed'] in {False, True}


def test_checkpoint_on_detached_head_uses_private_ref(tmp_path):
    root = tmp_path / 'repo'; root.mkdir()
    git(root, 'init', '-q', '-b', 'main'); git(root, 'config', 'user.email', 'o@e.test'); git(root, 'config', 'user.name', 'O')
    (root / 'a.txt').write_text('1'); git(root, 'add', '.'); git(root, 'commit', '-qm', 'base')
    git(root, 'checkout', '-q', '--detach')
    (root / 'a.txt').write_text('2')
    saved = checkpoints.checkpoint(root, 'cp', 'My Project')
    assert saved['ref'] == 'refs/appling/checkpoints/My-Project' and not saved['branch_updated']
    assert git(root, 'rev-parse', 'HEAD').strip() != saved['commit']


def test_failed_live_attempt_linked_to_waiting_criterion_still_reaches_qa(tmp_path):
    engine = Engine(); engine.failed_check = 'linked'
    store, workflow, pid = make(tmp_path, engine)
    try:
        to_build(store, workflow, pid)
        assert store.get(pid)['phase'] == 'implementation_verified'
        assert not any(e['type'] == 'problem' for e in store.events(pid))
    finally:
        workflow.shutdown()


def test_unlinked_failing_check_is_implementation_work_not_deferral(tmp_path):
    engine = Engine(); engine.failed_check = 'unlinked'
    store, workflow, pid = make(tmp_path, engine)
    try:
        to_build(store, workflow, pid)
        state = store.get(pid)
        assert 'qa-engineer' not in engine.calls
        assert state['attention']['reason'] == 'implementation'
        assert any('Check failed (exit 1): live post' in b['detail'] for b in state['attention']['blockers'])
        # Same outcomes on retry: bounded, despite receipts changing every run.
        assert engine.calls.count('sw-developer') == 2
    finally:
        workflow.shutdown()


def test_build_handoffs_are_checkpointed_on_the_project_branch(tmp_path):
    engine = Engine(); store, workflow, pid = make(tmp_path, engine)
    try:
        to_build(store, workflow, pid)
        root = Path(store.get(pid)['root'])
        events = [e for e in store.events(pid) if e['type'] == 'checkpoint']
        assert events and all(e['status'] == 'saved' for e in events)
        log = git(root, 'log', '--format=%s', 'main')
        assert 'Appling checkpoint: builder handoff with owner setup pending' in log
        assert 'poster.py' in git(root, 'ls-tree', '-r', '--name-only', 'main')
    finally:
        workflow.shutdown()


def spec_and_root(tmp_path):
    root = tmp_path / 'p'; (root / '.sdlc/evidence/run').mkdir(parents=True)
    (root / 'requirements.md').write_text(REQUIREMENTS)
    ok = root / '.sdlc/evidence/run/ok.txt'; ok.write_text('exit 0')
    old = root / '.sdlc/evidence/old.txt'; old.write_text('exit 0 from an older run')
    return root, acceptance.normalize(CRITERIA, PREREQS, REQUIREMENTS)


def test_evaluate_requires_criterion_reports_for_live_and_explicit_zero_exit(tmp_path):
    root, spec = spec_and_root(tmp_path)
    legacy = dict(checks=[dict(command='all', exit_code=0, evidence='.sdlc/evidence/run/ok.txt', requirements=['FR-1', 'FR-2'])])
    out = acceptance.evaluate(root, spec, {}, legacy, 'rev', evidence_prefix='.sdlc/evidence/run/')
    assert out['AC-FR-1-1']['status'] == 'passed' and out['AC-FR-2-1']['status'] == 'not_run'
    missing_exit = dict(criteria=[dict(id='AC-FR-1-1', status='passed', evidence='.sdlc/evidence/run/ok.txt')])
    assert acceptance.evaluate(root, spec, {}, missing_exit, 'rev')['AC-FR-1-1']['status'] == 'not_run'


def test_evaluate_rejects_old_evidence_and_live_pass_before_setup(tmp_path):
    root, spec = spec_and_root(tmp_path)
    stale = dict(criteria=[dict(id='AC-FR-1-1', status='passed', exit_code=0, evidence='.sdlc/evidence/old.txt')])
    assert acceptance.evaluate(root, spec, {}, stale, 'rev', evidence_prefix='.sdlc/evidence/run/')['AC-FR-1-1']['status'] == 'not_run'
    live = dict(criteria=[dict(id='AC-FR-2-1', status='passed', implemented=True, exit_code=0, evidence='.sdlc/evidence/run/ok.txt')])
    early = acceptance.evaluate(root, spec, {}, live, 'rev', evidence_prefix='.sdlc/evidence/run/')['AC-FR-2-1']
    assert early['status'] == 'pending_owner' and early['owner'] == 'you'
    ready = acceptance.evaluate(root, spec, {'prerequisites_done': {'P-login': 1}}, live, 'rev', evidence_prefix='.sdlc/evidence/run/')
    assert ready['AC-FR-2-1']['status'] == 'passed'


from appling.direct import BUILD_SOME, KEEP_ALL, LEAVE_ALL, PROVIDE_FIRST


def scope_question(store, pid):
    items = [i for i in store.inbox(pid) if i.get('scope')]
    assert len(items) == 1
    return items[0]


def stuck(tmp_path):
    engine = Engine(); engine.impl_blocker = True
    store, workflow, pid = make(tmp_path, engine)
    to_build(store, workflow, pid)
    return engine, store, workflow, pid


def test_unfinishable_parts_are_put_to_the_owner_as_a_choice(tmp_path):
    engine, store, workflow, pid = stuck(tmp_path)
    try:
        item = scope_question(store, pid)
        assert item['choices'] == [BUILD_SOME, LEAVE_ALL, KEEP_ALL, PROVIDE_FIRST]
        assert 'Build the account posting adapter' in item['question']
        assert engine.calls.count('sw-developer') == 2 and 'qa-engineer' not in engine.calls
    finally:
        workflow.shutdown()


def test_leaving_parts_for_later_needs_owner_review_then_builds_release_one_only(tmp_path):
    engine, store, workflow, pid = stuck(tmp_path)
    try:
        item = scope_question(store, pid)
        workflow.answer(pid, item['id'], LEAVE_ALL); wait_idle(workflow, pid)
        assert 'Build the account posting adapter' in engine.rescope_prompts[0]
        state = store.get(pid)
        assert state['phase'] == 'requirements_review' and 'requirements' not in state['approvals']
        review = store.inbox(pid)[0]
        assert review['kind'] == 'requirements' and '| AC-FR-2-1 | FR-2 | later |' in review['question']
        builds = engine.calls.count('sw-developer')
        approve(store, workflow, pid, 'requirements')
        assert engine.calls.count('sw-developer') == builds + 1
        assert store.get(pid)['phase'] == 'delivered'
        assert set(workflow.acceptance_status(pid)['results']) == {'AC-FR-1-1'}
    finally:
        workflow.shutdown()


def test_keep_building_reruns_the_builder_and_provide_access_runs_nothing(tmp_path):
    engine, store, workflow, pid = stuck(tmp_path)
    try:
        builds = engine.calls.count('sw-developer')
        workflow.answer(pid, scope_question(store, pid)['id'], PROVIDE_FIRST); wait_idle(workflow, pid)
        assert engine.calls.count('sw-developer') == builds and store.get(pid)['paused']
        assert any('Tick each setup item' in m['content'] for m in store.messages(pid))
        workflow.submit(pid, 'Continue'); wait_idle(workflow, pid)
        workflow.answer(pid, scope_question(store, pid)['id'], KEEP_ALL); wait_idle(workflow, pid)
        assert engine.calls.count('sw-developer') > builds + 1
        assert 'req-engineer' not in engine.calls[2:]
    finally:
        workflow.shutdown()


def test_owner_can_type_which_parts_to_build_and_scope_change_cannot_drop_requirements(tmp_path):
    engine, store, workflow, pid = stuck(tmp_path)
    try:
        engine.drop_requirement = True
        workflow.submit(pid, 'Build the number screen now; leave posting for later'); wait_idle(workflow, pid)
        assert 'leave posting for later' in engine.rescope_prompts[0]
        assert any(e['type'] == 'problem' and 'cannot add or remove' in e['text'] for e in store.events(pid))
        root = Path(store.get(pid)['root'])
        assert 'FR-2' in (root / 'requirements.md').read_text()
    finally:
        workflow.shutdown()
