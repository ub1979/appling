"""Direct coding remains behind prototype/requirements gates and independent QA."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from appling.store import Store
from appling.workflow import Workflow, artifact_revision
from test_workflow import approve, wait_idle


class Engine:
    def __init__(self):
        self.calls = []
        self.block = False
        self.mutate_qa = False
        self.fail_first_qa = False
        self.mutate_prototype = False
        self.sessions = []

    def __call__(self, connection, run):
        brief = json.loads(run.prompt)
        role = run.instructions.split('Role: ', 1)[1].splitlines()[0]
        self.calls.append(role)
        if role == 'req-engineer':
            return dict(requirements='FR-1: Show the saved number.', suggested_team=['code-reviewer','security-auditor','unknown-role'])
        if role == 'ui-designer':
            p = run.root/'prototypes/index.html'
            p.parent.mkdir(exist_ok=True)
            p.write_text(f'<button>Prototype number version {self.calls.count(role)}</button>')
            return dict(status='completed')
        if role == 'sw-developer':
            assert brief['execution']['mode'] == 'direct'
            assert not run.managed_worker and run.native_delegation
            self.sessions.append(run.session)
            run.save_session('native-builder-session')
            (run.root/'number.txt').write_text('42')
            checked = subprocess.run([sys.executable, '-c',
                'from pathlib import Path; assert int(Path("number.txt").read_text())==42; print("saved number checked")'],
                cwd=run.root, capture_output=True, text=True)
            assert checked.returncode == 0
            evidence = run.root/'.sdlc/evidence/direct-build/build.txt'
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text(f'command: check saved number\nexit: {checked.returncode}\n{checked.stdout}')
            if self.mutate_prototype:
                (run.root/'prototypes/index.html').write_text('unapproved prototype mutation')
            return dict(status='blocked' if self.block else 'completed', summary='Builder handoff',
                checks=[dict(command='check saved number',exit_code=0,evidence=str(evidence.relative_to(run.root)))])
        assert role in {'qa-engineer','code-reviewer','security-auditor'}
        assert (run.root/'number.txt').read_text() == '42'
        if self.mutate_qa:
            (run.root/'number.txt').write_text('QA changed source')
        path = run.root/brief['worker']['evidence']/'fixture-review.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        # A controller fixture receipt, not actual product/browser acceptance.
        path.write_text(json.dumps(dict(controller_test=True, observed_number=42)))
        verdict = 'fail' if role == 'qa-engineer' and self.fail_first_qa and self.calls.count('qa-engineer') == 1 else 'pass'
        return dict(verdict=verdict, summary='Independent controller test', browser_tested=True,
            checks=[dict(command='fixture review',exit_code=0,evidence=str(path.relative_to(run.root)),requirements=['FR-1'])],
            findings=[dict(description='Fix number formatting')] if verdict=='fail' else [])


def project(tmp_path, engine):
    store = Store(tmp_path/'state')
    state = store.add(tmp_path/'app')
    workflow = Workflow(store, engine)
    # Direct mode must work without the mandatory two-host-worker policy.
    settings = workflow.settings()
    settings['parallel_work']['agents_per_project'] = 1
    store.save_setting('ai', settings)
    return store, workflow, state['id']


def test_direct_pipeline_always_prototypes_then_builds_and_reviews_sequentially(tmp_path):
    engine = Engine()
    store, workflow, pid = project(tmp_path, engine)
    try:
        workflow.submit(pid, 'Build a number viewer')
        wait_idle(workflow,pid)
        assert engine.calls == ['req-engineer','ui-designer']
        assert store.inbox(pid)[0]['kind'] == 'prototype'
        approve(store,workflow,pid,'prototype')
        assert engine.calls == ['req-engineer','ui-designer']
        assert store.inbox(pid)[0]['kind'] == 'requirements'
        approve(store,workflow,pid,'requirements')
        state = store.get(pid)
        assert state['phase'] == 'delivered'
        assert engine.calls == ['req-engineer','ui-designer','sw-developer','qa-engineer','code-reviewer','security-auditor']
        assert 'unknown-role' not in state['team']
        assert 'task-planner' not in state['team']
        assert not (Path(state['root'])/'plan.md').exists()
        assert state['tasks'][0]['status'] == 'done'
        assert set(state['approvals']) == {'requirements','prototype'}
    finally:
        workflow.shutdown()


def test_blocked_direct_build_resumes_native_session_without_planning(tmp_path):
    engine=Engine();engine.block=True
    store,workflow,pid=project(tmp_path,engine)
    workflow.submit(pid,'Build');wait_idle(workflow,pid)
    approve(store,workflow,pid,'prototype');approve(store,workflow,pid,'requirements')
    assert store.get(pid)['paused'] and 'qa-engineer' not in engine.calls
    root=Path(store.get(pid)['root'])
    assert (root/'number.txt').read_text()=='42'
    approvals=store.get(pid)['approvals'];workflow.shutdown()
    engine.block=False
    workflow=Workflow(store,engine)
    try:
        workflow.submit(pid,'Continue saved implementation');wait_idle(workflow,pid)
        assert engine.sessions==[None,'native-builder-session']
        assert store.get(pid)['phase']=='delivered'
        assert store.get(pid)['approvals']==approvals
    finally:workflow.shutdown()


@pytest.mark.parametrize('failure',['missing_prototype','qa_edits_source'])
def test_direct_mode_cannot_bypass_approved_prototype_or_independent_qa(tmp_path,failure):
    engine=Engine()
    store,workflow,pid=project(tmp_path,engine)
    try:
        workflow.submit(pid,'Build');wait_idle(workflow,pid)
        if failure=='missing_prototype':
            # Reproduce a forged controller phase without granting approval.
            store.update(pid,phase='build',approvals={'requirements':artifact_revision(Path(store.get(pid)['root']),'requirements')})
            store.close(pid,store.inbox(pid)[0]['id'])
            workflow.submit(pid,'Go');wait_idle(workflow,pid)
            assert 'sw-developer' not in engine.calls
        else:
            engine.mutate_qa=failure=='qa_edits_source'
            approve(store,workflow,pid,'prototype');approve(store,workflow,pid,'requirements')
        assert store.get(pid)['phase']!='delivered' and store.get(pid)['paused']
    finally:workflow.shutdown()


def test_builder_edit_to_the_approved_prototype_is_undone_and_the_build_continues(tmp_path):
    engine=Engine();engine.mutate_prototype=True
    store,workflow,pid=project(tmp_path,engine)
    try:
        workflow.submit(pid,'Build');wait_idle(workflow,pid)
        root=Path(store.get(pid)['root']);approved=(root/'prototypes/index.html').read_bytes()
        approve(store,workflow,pid,'prototype');approve(store,workflow,pid,'requirements')
        state=store.get(pid)
        assert state['phase']=='delivered',[m['content'] for m in store.messages(pid)][-3:]
        assert (root/'prototypes/index.html').read_bytes()==approved
        assert state['approvals']['prototype']==artifact_revision(root,'prototype')
        restored=[e for e in store.events(pid) if e['type']=='approved_files_restored']
        assert restored and restored[0]['kinds']==['prototype']
        assert any('put the approved version back' in m['content'] for m in store.messages(pid))
    finally:workflow.shutdown()


def test_qa_findings_return_to_same_builder_before_fresh_reviews(tmp_path):
    engine=Engine();engine.fail_first_qa=True
    store,workflow,pid=project(tmp_path,engine)
    try:
        workflow.submit(pid,'Build');wait_idle(workflow,pid)
        approve(store,workflow,pid,'prototype');approve(store,workflow,pid,'requirements')
        assert store.get(pid)['phase']=='delivered'
        assert engine.calls[2:]==['sw-developer','qa-engineer','sw-developer','qa-engineer','code-reviewer','security-auditor']
        assert engine.sessions==[None,'native-builder-session']
    finally:workflow.shutdown()


def test_prototype_feedback_requires_review_of_the_new_revision_before_coding(tmp_path):
    engine=Engine();store,workflow,pid=project(tmp_path,engine)
    try:
        workflow.submit(pid,'Build');wait_idle(workflow,pid)
        original=store.inbox(pid)[0]
        workflow.answer(pid,original['id'],dict(choice='Request changes',feedback='Change the prototype number label'))
        wait_idle(workflow,pid)
        current=store.inbox(pid)[0]
        assert current['kind']=='prototype' and current['revision']!=original['revision']
        # Prototype feedback is recorded in the requirements first, then the prototype is regenerated.
        assert engine.calls==['req-engineer','ui-designer','req-engineer','ui-designer']
        with pytest.raises(ValueError,match='changed'):
            workflow.answer(pid,current['id'],dict(choice='Approve prototype',revision=original['revision']))
        assert 'sw-developer' not in engine.calls
        approve(store,workflow,pid,'prototype');approve(store,workflow,pid,'requirements')
        assert store.get(pid)['phase']=='delivered'
    finally:workflow.shutdown()


def test_native_helpers_are_observable_communicate_and_clear_after_completion(tmp_path):
    engine=Engine();observed=[]
    def execute(connection,run):
        if '\nRole: sw-developer\n' in run.instructions:
            run.emit('helper',event='start',native=True,subagent_id='codex:child',goal='Independent frontend specialist')
            observed.append(store.get(pid)['native_helpers']['codex:child'])
            run.emit('native_agent',tool='sendInput',status='completed',threads=['child'],agents={})
            # Parent completion also clears any child whose final event was lost.
        return engine(connection,run)
    store,workflow,pid=project(tmp_path,execute)
    try:
        workflow.submit(pid,'Build');wait_idle(workflow,pid)
        approve(store,workflow,pid,'prototype');approve(store,workflow,pid,'requirements')
        assert observed[0]['goal']=='Independent frontend specialist'
        assert observed[0]['run_id']
        assert not store.get(pid).get('native_helpers')
        assert any(e['type']=='native_agent' and e['tool']=='sendInput' for e in store.events(pid))
    finally:workflow.shutdown()


class BlockedEngine(Engine):
    def __init__(self, mode):
        super().__init__();self.mode=mode

    def __call__(self,connection,run):
        result=super().__call__(connection,run)
        if '\nRole: sw-developer\n' not in run.instructions:return result
        attempt=self.calls.count('sw-developer')
        if self.mode=='recover' and attempt>1:return result
        if self.mode=='progress':(run.root/'partial.txt').write_text(str(attempt))
        blockers=[dict(kind='owner_setup',detail='Owner must sign in'),
                  dict(kind='live_acceptance',detail='Remote participant evidence is unavailable')]
        if self.mode not in {'owner','owner_completed'}:blockers.insert(0,dict(kind='implementation',detail='Adapter wiring is unfinished'))
        return dict(result,status='completed' if self.mode=='owner_completed' else 'blocked',blockers=blockers)


def run_to_build(store,workflow,pid):
    workflow.submit(pid,'Build');wait_idle(workflow,pid)
    approve(store,workflow,pid,'prototype');approve(store,workflow,pid,'requirements')


def test_mixed_blockers_continue_coding_in_same_session_before_independent_qa(tmp_path):
    engine=BlockedEngine('recover');store,workflow,pid=project(tmp_path,engine)
    try:
        run_to_build(store,workflow,pid)
        assert store.get(pid)['phase']=='delivered'
        assert engine.calls[2:5]==['sw-developer','sw-developer','qa-engineer']
        assert engine.sessions==[None,'native-builder-session']
        assert len([e for e in store.events(pid) if e['type']=='build_continuation'])==1
        assert not any(e['type']=='problem' for e in store.events(pid))
    finally:workflow.shutdown()


@pytest.mark.parametrize('mode,attempts',[('owner',1),('owner_completed',1),('stagnant',2),('progress',4)])
def test_expected_waiting_is_not_a_crash_and_retries_are_bounded(tmp_path,mode,attempts):
    engine=BlockedEngine(mode);store,workflow,pid=project(tmp_path,engine)
    try:
        run_to_build(store,workflow,pid)
        state=store.get(pid)
        assert state['paused'] and state['phase']=='build'
        assert state['attention']['blockers'] and not state['running']
        assert engine.calls.count('sw-developer')==attempts
        assert 'qa-engineer' not in engine.calls
        assert state['tasks'][0]['status']=='pending'
        assert not any(e['type']=='problem' for e in store.events(pid))
        assert [e for e in store.events(pid) if e['type']=='turn_end'][-1]['status']=='blocked'
        assert all('RuntimeError' not in m['content'] for m in store.messages(pid))
        assert Store(store.home).get(pid)['attention']==state['attention']
    finally:workflow.shutdown()


def test_real_engine_errors_remain_errors_and_owner_resume_clears_waiting(tmp_path):
    engine=BlockedEngine('owner');store,workflow,pid=project(tmp_path,engine)
    try:
        run_to_build(store,workflow,pid)
        approvals=store.get(pid)['approvals']
        def broken(connection,run):raise RuntimeError('Connection was lost')
        workflow.execute=broken
        workflow.submit(pid,'Continue');wait_idle(workflow,pid)
        assert store.get(pid)['attention'] is None
        assert store.get(pid)['approvals']==approvals
        assert any(e['type']=='problem' and 'Connection was lost' in e['text'] for e in store.events(pid))
    finally:workflow.shutdown()


def test_stop_prevents_automatic_continuation_even_with_implementation_blockers(tmp_path):
    engine=BlockedEngine('stagnant')
    def execute(connection,run):
        result=engine(connection,run)
        if '\nRole: sw-developer\n' in run.instructions:workflow.stop(pid)
        return result
    store,workflow,pid=project(tmp_path,execute)
    try:
        run_to_build(store,workflow,pid)
        assert store.get(pid)['paused'] and not store.get(pid)['queue']
        assert engine.calls.count('sw-developer')==1
        assert not any(e['type']=='build_continuation' for e in store.events(pid))
        assert [e for e in store.events(pid) if e['type']=='turn_end'][-1]['status']=='interrupted'
    finally:workflow.shutdown()
