"""Blocks mode: independent reusable blocks built in parallel, merged by the body, saved to a library."""
import json
import sys
import threading
from pathlib import Path

import pytest

from appling import acceptance, blocks
from appling.blockbuild import LEAVE
from appling.store import Store
from appling.workflow import Workflow
from test_workflow import approve, wait_idle

REQUIREMENTS = ('# App\n\n- FR-1: Show the saved number on the home screen.\n'
                '- FR-2: Send a Telegram notification when the number changes.\n'
                '- FR-3: Post the number to the owner social account.\n')
CRITERIA = [
    dict(id='AC-FR-1-1', requirement='FR-1', description='Home screen shows 42', release='1', live=False, prerequisites=[]),
    dict(id='AC-FR-2-1', requirement='FR-2', description='A change sends one notification', release='1', live=False, prerequisites=[]),
    dict(id='AC-FR-3-1', requirement='FR-3', description='A reviewed post reaches the real account', release='1', live=True,
         prerequisites=['P-login']),
]
PREREQS = [dict(id='P-login', kind='account', description='Sign in to the social account', needed_at='verification')]
PY = sys.executable


def block_test(ident):
    return f'"{PY}" -c "import pathlib,sys; sys.exit(0 if pathlib.Path(\'blocks/{ident}/ok\').read_text()==\'ok\' else 1)"'


def plan_for(sources=None):
    sources = sources or {}
    return dict(summary='A notifier and a poster block plus the app body.', blocks=[
        dict(id='notifier', name='Telegram notifier', purpose='Send short notifications', interface='notify(text: str) -> None',
             criteria=['AC-FR-2-1'], source=sources.get('notifier', 'new'), test=block_test('notifier')),
        dict(id='poster', name='Social poster', purpose='Post reviewed text to an account', interface='post(text: str) -> PostResult',
             criteria=['AC-FR-3-1'], prerequisites=['P-login'], test=block_test('poster')),
    ], body=dict(purpose='Number screen and wiring', criteria=['AC-FR-1-1'], files=[]))


class Engine:
    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()
        self.barrier = threading.Barrier(2, timeout=10)
        self.overlapped = False
        self.stuck = set()          # block ids whose builder cannot finish
        self.body_edits_block = False
        self.sources = {}
        self.ready = False
        self.root_file_once = set()     # block ids whose first attempt writes outside the block folder
        self.body_blocker_once = None   # block id the body asks to change on its first run
        self.body_output = False        # body leaves build output inside blocks/

    def role(self, run):
        return run.instructions.split('Role: ', 1)[1].splitlines()[0]

    def __call__(self, connection, run):
        brief = json.loads(run.prompt); role = self.role(run); root = run.root
        with self.lock:
            self.calls.append(role)
        if role == 'req-engineer':
            return dict(requirements=REQUIREMENTS, acceptance_criteria=CRITERIA, prerequisites=PREREQS)
        if role == 'ui-designer':
            p = root / 'prototypes/index.html'; p.parent.mkdir(exist_ok=True); p.write_text('<b>42</b>')
            return dict(status='completed')
        if role == 'sw-architect':
            assert not run.session            # fresh, independent planner session
            return plan_for(self.sources)
        if role == 'sw-developer' and brief.get('worker'):
            ident = 'notifier' if 'blocks/notifier/' in brief['goal'] else 'poster'
            with self.lock:
                self.calls.append('block:' + ident)
            if len(self.barrier_parties()) == 2:
                try:
                    self.barrier.wait(); self.overlapped = True
                except threading.BrokenBarrierError:
                    pass
            if ident in self.stuck:
                return dict(status='blocked', summary='Needs the real site', checks=[],
                            blockers=[dict(kind='implementation', detail='Posting needs the real website to finish')])
            folder = root / 'blocks' / ident; folder.mkdir(parents=True, exist_ok=True)
            if ident in self.root_file_once:
                self.root_file_once.discard(ident)
                (root / 'package-lock.json').write_text('{}')   # outside its ownership
            (folder / 'ok').write_text('ok')
            (folder / 'README.md').write_text(f'# {ident}\n')
            (folder / 'block.json').write_text(json.dumps(dict(name=ident, test=block_test(ident))))
            ev = root / brief['worker']['evidence'] / 'test.txt'; ev.parent.mkdir(parents=True, exist_ok=True)
            ev.write_text('command: block test\nexit: 0\n')
            command = next(b['test'] for b in plan_for()['blocks'] if b['id'] == ident)
            return dict(status='completed', summary=f'{ident} built',
                        checks=[dict(command=command, exit_code=0, evidence=str(ev.relative_to(root)))], blockers=[])
        if role == 'sw-developer':
            assert run.native_delegation and not run.managed_worker
            with self.lock:
                self.calls.append('body')
            (root / 'app').mkdir(exist_ok=True); (root / 'app/main.txt').write_text('42 uses notifier')
            if self.body_blocker_once:
                ident, self.body_blocker_once = self.body_blocker_once, None
                return dict(status='blocked', summary='needs a block change', checks=[],
                            blockers=[dict(kind='implementation', detail='notify() must return a message id', block=ident)])
            if self.body_output:
                out = root / 'blocks/notifier/dist'; out.mkdir(parents=True, exist_ok=True); (out / 'bundle.js').write_text('x')
            if self.body_edits_block:
                (root / 'blocks/notifier/ok').write_text('changed by body')
            ev = root / '.sdlc/evidence/direct-build/body.txt'; ev.parent.mkdir(parents=True, exist_ok=True)
            ev.write_text('command: body tests\nexit: 0\n')
            return dict(status='completed', summary='Body wired',
                        checks=[dict(command='body tests', exit_code=0, evidence='.sdlc/evidence/direct-build/body.txt')], blockers=[])
        folder = root / brief['worker']['evidence']; folder.mkdir(parents=True, exist_ok=True)
        local = folder / 'qa.txt'; local.write_text('command: qa\nexit: 0\n'); rel = str(local.relative_to(root))
        if role != 'qa-engineer':
            return dict(verdict='pass', summary='review', checks=[dict(command='review', exit_code=0, evidence=rel)], findings=[])
        spec = json.loads((root / acceptance.SPEC).read_text())
        entries = []
        for c in spec['criteria']:
            if c['release'] != '1':
                continue
            if c['live'] and not self.ready:
                entries.append(dict(id=c['id'], status='pending_owner', implemented=True, command='qa', exit_code=0, evidence=rel))
            else:
                entries.append(dict(id=c['id'], status='passed', implemented=True, command='qa', exit_code=0, evidence=rel))
        return dict(verdict='pass' if all(e['status'] == 'passed' for e in entries) else 'blocked', summary='qa',
                    browser_tested=True, criteria=entries, checks=[dict(command='qa', exit_code=0, evidence=rel)], findings=[])

    def barrier_parties(self):
        return [] if self.stuck else [1, 2]


@pytest.fixture(autouse=True)
def library(tmp_path, monkeypatch):
    home = tmp_path / 'library'
    monkeypatch.setenv('APPLING_BLOCKS_HOME', str(home))
    return home


def make(tmp_path, engine, name='app'):
    store = Store(tmp_path / ('state-' + name))
    state = store.add(tmp_path / name, execution_mode='blocks')
    workflow = Workflow(store, engine)
    settings = workflow.settings(); settings['parallel_work']['agents_per_project'] = 3
    store.save_setting('ai', settings)
    return store, workflow, state['id']


def to_blocks_review(store, workflow, pid):
    workflow.submit(pid, 'Build a number app'); wait_idle(workflow, pid)
    approve(store, workflow, pid, 'prototype'); approve(store, workflow, pid, 'requirements')


def test_block_plan_validation_rejects_cycles_gaps_and_unknown_library():
    spec = acceptance.normalize(CRITERIA, PREREQS, REQUIREMENTS)
    checked = blocks.validate(plan_for(), spec)
    assert checked['waves'] == [['notifier', 'poster']] and checked['body']['files'] == ['app/']
    cyc = plan_for(); cyc['blocks'][0]['depends_on'] = ['poster']; cyc['blocks'][1]['depends_on'] = ['notifier']
    with pytest.raises(ValueError, match='cycle'):
        blocks.validate(cyc, spec)
    gap = plan_for(); gap['body']['criteria'] = []
    with pytest.raises(ValueError, match='AC-FR-1-1'):
        blocks.validate(gap, spec)
    with pytest.raises(ValueError, match='unknown library'):
        blocks.validate(plan_for({'notifier': 'library:notifier@v9'}), spec)
    bad = plan_for(); bad['body']['files'] = ['blocks/notifier/x']
    with pytest.raises(ValueError, match='cannot own blocks'):
        blocks.validate(bad, spec)


def test_independent_blocks_build_in_parallel_then_body_merges_and_blocks_are_published(tmp_path, library):
    engine = Engine(); store, workflow, pid = make(tmp_path, engine)
    try:
        to_blocks_review(store, workflow, pid)
        review = store.inbox(pid)[0]
        assert review['kind'] == 'blocks' and 'Telegram notifier' in review['question'] and '(in parallel)' in review['question']
        assert 'sw-developer' not in engine.calls
        approve(store, workflow, pid, 'blocks')
        state = store.get(pid)
        assert engine.overlapped, 'the two independent blocks did not build at the same time'
        assert engine.calls.index('body') > max(engine.calls.index('block:notifier'), engine.calls.index('block:poster'))
        assert state['phase'] == 'implementation_verified'
        root = Path(state['root'])
        assert (root / 'app/main.txt').exists() and (root / 'blocks/notifier/README.md').exists()
        assert (root / '.sdlc/evidence/blocks/notifier/test.log').read_text().startswith('command:')
        names = {(b['name'], b['version'], b['status']) for b in blocks.catalogue(library)}
        assert names == {('notifier', 'v1', 'candidate'), ('poster', 'v1', 'candidate')}
        assert {b['status'] for b in store.get(pid)['block_status'].values()} == {'merged'}
    finally:
        workflow.shutdown()


def test_stuck_block_does_not_stop_others_and_owner_can_leave_it_for_later(tmp_path, library):
    engine = Engine(); engine.stuck = {'poster'}
    store, workflow, pid = make(tmp_path, engine)
    try:
        to_blocks_review(store, workflow, pid); approve(store, workflow, pid, 'blocks')
        state = store.get(pid)
        assert state['block_status']['notifier']['status'] == 'tested'
        assert state['block_status']['poster']['status'] == 'blocked'
        question = next(i for i in store.inbox(pid) if i.get('blocks_scope'))
        assert 'Social poster' in question['question'] and 'body' not in engine.calls
        workflow.answer(pid, question['id'], LEAVE); wait_idle(workflow, pid)
        review = store.inbox(pid)[0]
        assert review['kind'] == 'requirements' and '| AC-FR-3-1 | FR-3 | later |' in review['question']
        approve(store, workflow, pid, 'requirements')
        state = store.get(pid)
        assert state['phase'] == 'delivered', [m['content'][:120] for m in store.messages(pid)][-3:]
        assert engine.calls.count('block:poster') == 1 and engine.calls.count('block:notifier') == 1
        assert {b['name'] for b in blocks.catalogue(library)} == {'notifier'}
    finally:
        workflow.shutdown()


def test_second_project_reuses_library_block_without_rebuilding_and_marks_it_verified(tmp_path, library):
    first = Engine(); store, workflow, pid = make(tmp_path, first, 'first')
    try:
        to_blocks_review(store, workflow, pid); approve(store, workflow, pid, 'blocks')
    finally:
        workflow.shutdown()
    second = Engine(); second.sources = {'notifier': 'library:notifier@v1'}; second.barrier_parties = lambda: []
    store, workflow, pid = make(tmp_path, second, 'second')
    try:
        to_blocks_review(store, workflow, pid)
        assert 'library notifier@v1' in store.inbox(pid)[0]['question']
        approve(store, workflow, pid, 'blocks')
        assert 'block:notifier' not in second.calls and 'block:poster' in second.calls
        root = Path(store.get(pid)['root'])
        assert json.loads((root / 'blocks/notifier/block.json').read_text())['origin'] == dict(library='notifier', version='v1')
        meta = next(b for b in blocks.catalogue(library) if b['name'] == 'notifier')
        assert meta['status'] == 'verified' and meta['verified_in'] == ['second']
    finally:
        workflow.shutdown()


def test_body_cannot_edit_block_files(tmp_path):
    engine = Engine(); engine.body_edits_block = True
    store, workflow, pid = make(tmp_path, engine)
    try:
        to_blocks_review(store, workflow, pid); approve(store, workflow, pid, 'blocks')
        assert store.get(pid)['phase'] == 'body'
        assert any(e['type'] == 'problem' and 'changed files inside blocks/' in e['text'] for e in store.events(pid))
    finally:
        workflow.shutdown()


def test_retry_after_rejected_merge_runs_a_fresh_builder(tmp_path):
    from appling.blockbuild import RETRY
    engine = Engine(); engine.root_file_once = {'notifier'}; engine.barrier_parties = lambda: []
    store, workflow, pid = make(tmp_path, engine)
    try:
        to_blocks_review(store, workflow, pid); approve(store, workflow, pid, 'blocks')
        assert store.get(pid)['block_status']['notifier']['status'] == 'blocked'
        assert 'could not be merged' in store.get(pid)['block_status']['notifier']['reason']
        (Path(store.get(pid)['root']) / 'package-lock.json').unlink(missing_ok=True)
        question = next(i for i in store.inbox(pid) if i.get('blocks_scope'))
        workflow.answer(pid, question['id'], RETRY); wait_idle(workflow, pid)
        assert engine.calls.count('block:notifier') == 2
        assert store.get(pid)['block_status']['notifier']['status'] in {'tested', 'merged'}
    finally:
        workflow.shutdown()


def test_block_integrated_but_untested_before_restart_is_tested_on_resume(tmp_path):
    from appling.blockbuild import build
    engine = Engine(); store, workflow, pid = make(tmp_path, engine)
    try:
        to_blocks_review(store, workflow, pid); approve(store, workflow, pid, 'blocks')
        root = Path(store.get(pid)['root'])
        status = store.get(pid)['block_status']; status['notifier'] = dict(status='building')
        (root / 'blocks/notifier/ok').write_text('broken')
        store.update(pid, block_status=status, phase='blocks_build',
                     tasks=[dict(t, status='done') for t in blocks.block_tasks(blocks.load(root), acceptance.load(root))])
        workflow.cancelled[pid] = threading.Event()
        calls = engine.calls.count('block:notifier')
        try:
            build(workflow, pid)
        except Exception:
            pass
        assert store.get(pid)['block_status']['notifier']['test']['passed'] is False or engine.calls.count('block:notifier') > calls
    finally:
        workflow.shutdown()


def test_typed_feedback_on_block_plan_replans_instead_of_queueing(tmp_path):
    engine = Engine(); store, workflow, pid = make(tmp_path, engine)
    try:
        to_blocks_review(store, workflow, pid)
        workflow.submit(pid, 'Split the poster into its own two blocks'); wait_idle(workflow, pid)
        assert engine.calls.count('sw-architect') == 2
        assert store.get(pid)['queue'] == [] and store.inbox(pid)[0]['kind'] == 'blocks'
    finally:
        workflow.shutdown()


def test_leave_for_later_defers_a_block_even_when_its_check_is_shared(tmp_path):
    engine = Engine(); engine.stuck = {'poster'}
    shared = plan_for(); shared['body']['criteria'] = ['AC-FR-1-1', 'AC-FR-3-1']
    engine.__class__ = type('Shared', (Engine,), {})
    orig = Engine.__call__
    def call(self, connection, run):
        if self.role(run) == 'sw-architect':
            with self.lock: self.calls.append('sw-architect')
            return shared
        return orig(self, connection, run)
    engine.__class__.__call__ = call
    store, workflow, pid = make(tmp_path, engine)
    try:
        to_blocks_review(store, workflow, pid); approve(store, workflow, pid, 'blocks')
        question = next(i for i in store.inbox(pid) if i.get('blocks_scope'))
        workflow.answer(pid, question['id'], LEAVE); wait_idle(workflow, pid)
        root = Path(store.get(pid)['root'])
        spec = acceptance.load(root)
        assert spec['deferred_blocks'] == ['poster']
        assert next(c for c in spec['criteria'] if c['id'] == 'AC-FR-3-1')['release'] == '1'   # body still covers it
        approve(store, workflow, pid, 'requirements')
        assert engine.calls.count('block:poster') == 1 and 'body' in engine.calls
    finally:
        workflow.shutdown()


def test_body_interface_request_reopens_the_block_then_merges(tmp_path):
    engine = Engine(); engine.body_blocker_once = 'notifier'; engine.barrier_parties = lambda: []
    store, workflow, pid = make(tmp_path, engine)
    try:
        to_blocks_review(store, workflow, pid); approve(store, workflow, pid, 'blocks')
        assert engine.calls.count('block:notifier') == 2 and engine.calls.count('block:poster') == 1
        assert engine.calls.count('body') == 2
        assert store.get(pid)['phase'] == 'implementation_verified'
    finally:
        workflow.shutdown()


def test_unknown_block_in_body_request_does_not_loop(tmp_path):
    engine = Engine(); engine.body_blocker_once = 'no-such-block'
    store, workflow, pid = make(tmp_path, engine)
    try:
        to_blocks_review(store, workflow, pid); approve(store, workflow, pid, 'blocks')
        assert engine.calls.count('body') <= 4   # bounded continuation, not 100 silent reruns
    finally:
        workflow.shutdown()


def test_body_edit_to_blocks_stays_rejected_on_resume_but_build_output_is_fine(tmp_path):
    engine = Engine(); engine.body_edits_block = True
    store, workflow, pid = make(tmp_path, engine)
    try:
        to_blocks_review(store, workflow, pid); approve(store, workflow, pid, 'blocks')
        engine.body_edits_block = False
        workflow.submit(pid, 'Continue'); wait_idle(workflow, pid)
        assert store.get(pid)['phase'] == 'body'   # the earlier edit is still detected
    finally:
        workflow.shutdown()
    engine = Engine(); engine.body_output = True
    store, workflow, pid = make(tmp_path, engine, 'output')
    try:
        to_blocks_review(store, workflow, pid); approve(store, workflow, pid, 'blocks')
        assert store.get(pid)['phase'] == 'implementation_verified'
    finally:
        workflow.shutdown()


def test_plan_shows_every_command_and_runner_survives_background_processes(tmp_path):
    spec = acceptance.normalize(CRITERIA, PREREQS, REQUIREMENTS)
    plan = plan_for(); plan['blocks'][0]['setup'] = 'npm install'
    assert 'Setup: `npm install`' in blocks.markdown(blocks.validate(plan, spec), spec)
    import time as _t
    started = _t.time()
    code = blocks._run('sleep 30 & echo started', tmp_path, tmp_path / 'log.txt', timeout=20)
    assert code == 0 and _t.time() - started < 10 and 'started' in (tmp_path / 'log.txt').read_text()


def test_reused_block_with_pending_live_check_is_not_marked_verified(tmp_path, library):
    first = Engine(); store, workflow, pid = make(tmp_path, first, 'first')
    try:
        to_blocks_review(store, workflow, pid); approve(store, workflow, pid, 'blocks')
    finally:
        workflow.shutdown()
    second = Engine(); second.sources = {'poster': 'library:poster@v1'}
    orig_plan = plan_for
    second.barrier_parties = lambda: []
    def call(self, connection, run):
        if self.role(run) == 'sw-architect':
            with self.lock: self.calls.append('sw-architect')
            p = orig_plan(); p['blocks'][1]['source'] = 'library:poster@v1'; return p
        return Engine.__call__(self, connection, run)
    second.__class__ = type('Reuse', (Engine,), {'__call__': call})
    store, workflow, pid = make(tmp_path, second, 'second')
    try:
        to_blocks_review(store, workflow, pid); approve(store, workflow, pid, 'blocks')
        meta = next(b for b in blocks.catalogue(library) if b['name'] == 'poster')
        assert meta['status'] == 'candidate'   # its live check is still waiting on the owner
    finally:
        workflow.shutdown()


def test_switching_an_existing_project_to_blocks_starts_block_planning(tmp_path):
    from appling.direct import set_mode
    engine = Engine(); store = Store(tmp_path / 'state'); state = store.add(tmp_path / 'legacy', execution_mode='direct')
    workflow = Workflow(store, engine)
    try:
        store.update(state['id'], phase='build', paused=True)
        set_mode(workflow, state['id'], 'blocks')
        assert store.get(state['id'])['phase'] == 'blocks_plan'
    finally:
        workflow.shutdown()


def test_block_with_red_test_history_and_live_parts_pending_is_not_stuck(tmp_path):
    from appling.swarm import validate_checks
    task = dict(id='speech', block='speech', acceptance=[dict(command='npm test')])
    worker = dict(evidence='.sdlc/evidence/workers/w/')
    live = dict(status='blocked', summary='36 tests pass; live acceptance needs the owner',
                blockers=[dict(kind='live_acceptance', detail='needs a real meeting')],
                checks=[dict(command='node --test red', exit_code=1, evidence='x'), dict(command='npm test', exit_code=0, evidence='y')])
    validate_checks(tmp_path, task, worker, live)   # does not raise
    with pytest.raises(RuntimeError, match='blocker'):
        validate_checks(tmp_path, task, worker, dict(live, blockers=[dict(kind='implementation', detail='adapter unfinished')]))
