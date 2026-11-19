"""Behavioral regressions for the plan-review findings, using isolated projects."""
import json
import sys
import shlex
import subprocess
from pathlib import Path

import pytest

from appling import planning, workspaces
from appling.preflight import require_runtime
from appling.swarm import build_ready
from appling.workflow import parse_tasks, artifact_revision
from test_swarm import fixture
from test_planning import project, parallel_tasks, wait_idle
from plan_fixtures import plan_result


def evidence(run,command='verify',verdict=None):
    b=json.loads(run.prompt);path=run.root/b['worker']['evidence']/'check.log'
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text('Actual test fixture result\n')
    result=dict(status='completed',checks=[dict(command=command,exit_code=0,evidence=str(path.relative_to(run.root)))])
    if verdict:result['verdict']=verdict
    return result


@pytest.mark.parametrize('omission',['empty_log','split_commands'])
@pytest.mark.parametrize('repair',[False,True])
def test_worker_repairs_receipts_once_before_integration(tmp_path,omission,repair):
    command=shlex.join([sys.executable,'-c','from pathlib import Path; assert Path("owned.txt").read_text()=="work"'])
    combined=command+' && '+command;calls=[]
    def execute(conn,run):
        calls.append(run.root)
        (run.root/'owned.txt').write_text('work')
        b=json.loads(run.prompt);log=run.root/b['worker']['evidence']/'check.log';log.parent.mkdir(parents=True,exist_ok=True)
        fixed=repair and len(calls)==2
        checked=subprocess.run(combined,cwd=run.root,shell=True,capture_output=True,text=True)
        assert checked.returncode==0
        log.write_text(('command: '+combined+'\nexit: 0\noutput: empty\n') if fixed or omission=='split_commands' else checked.stdout)
        return dict(status='completed',checks=[dict(command=combined if fixed or omission=='empty_log' else command,
            exit_code=checked.returncode,evidence=str(log.relative_to(run.root)))])
    s,w,pid,root=fixture(tmp_path,execute)
    s.update(pid,tasks=parse_tasks([dict(id='one',goal='one change',files=['owned.txt'],
        acceptance=[dict(command=combined,expect='actual silent checks pass')])]))
    approvals=s.get(pid)['approvals']
    try:
        if repair:
            assert build_ready(w,pid)
            assert s.get(pid)['tasks'][0]['status']=='done' and (root/'owned.txt').read_text()=='work'
        else:
            with pytest.raises(RuntimeError,match='evidence|acceptance'):build_ready(w,pid)
            assert s.get(pid)['tasks'][0]['status']=='pending' and not (root/'owned.txt').exists()
        assert len(calls)==2 and calls[0]==calls[1] and root not in calls
        assert s.get(pid)['approvals']==approvals
    finally:w.shutdown()


def test_evidence_retry_cannot_hide_reviewer_source_edits(tmp_path):
    calls=[]
    def execute(conn,run):
        calls.append(run.root);b=json.loads(run.prompt)
        log=run.root/b['worker']['evidence']/'check.log';log.parent.mkdir(parents=True,exist_ok=True)
        log.write_text('')
        if len(calls)==2:
            (run.root/'source.txt').write_text('forbidden reviewer repair')
            log.write_text('claimed receipt')
        return dict(status='completed',verdict='pass',checks=[dict(command='verify',exit_code=0,evidence=str(log.relative_to(run.root)))])
    s,w,pid,root=fixture(tmp_path,execute);(root/'source.txt').write_text('owner source')
    s.update(pid,tasks=parse_tasks([dict(id='qa',goal='independent check',kind='verification',role='qa-engineer',files=['tests/'])]))
    approvals=s.get(pid)['approvals']
    try:
        with pytest.raises(RuntimeError,match='Verification changed application source'):build_ready(w,pid)
        assert len(calls)==2 and (root/'source.txt').read_text()=='owner source'
        assert s.get(pid)['approvals']==approvals and s.get(pid)['tasks'][0]['status']=='pending'
    finally:w.shutdown()


@pytest.mark.parametrize('failure',['missing_evidence','unowned_file','missing_planned_check'])
def test_single_task_cannot_bypass_evidence_or_ownership(tmp_path,failure):
    calls=[]
    def execute(conn,run):
        calls.append(run.root)
        (run.root/'owned.txt').write_text('proposed change')
        if failure=='unowned_file':(run.root/'outside.txt').write_text('unowned change')
        return dict(status='completed') if failure=='missing_evidence' else evidence(run)
    s,w,pid,root=fixture(tmp_path,execute)
    task=dict(id='one',goal='one bounded change',files=['owned.txt'])
    if failure=='missing_planned_check':task['acceptance']=[dict(command='different check',expect='specific behavior')]
    s.update(pid,tasks=parse_tasks([task]));before=s.get(pid)['approvals']
    try:
        with pytest.raises(RuntimeError,match='evidence|ownership|acceptance'):build_ready(w,pid)
        assert calls and root not in calls
        assert not (root/'owned.txt').exists() and not (root/'outside.txt').exists()
        assert s.get(pid)['tasks'][0]['status']=='pending'
        assert s.get(pid)['approvals']==before
        assert Path(s.get(pid)['workers'][0]['workspace']).is_dir()
    finally:w.shutdown()


@pytest.mark.parametrize('mutate',[False,True])
def test_reviewer_has_own_session_and_cannot_change_source(tmp_path,mutate):
    calls=[]
    def execute(conn,run):
        b=json.loads(run.prompt);task=b['worker']['task_id']
        calls.append((task,run.session,run.root,run.instructions))
        run.save_session('session-'+task)
        if task=='implement':(run.root/'source.txt').write_text('reviewed source')
        elif mutate:(run.root/'source.txt').write_text('reviewer repair is forbidden')
        return evidence(run,verdict='pass' if task=='review' else None)
    s,w,pid,root=fixture(tmp_path,execute)
    s.update(pid,team=['req-engineer','task-planner'],tasks=parse_tasks([
        dict(id='implement',goal='implementation',files=['source.txt']),
        dict(id='review',goal='independent acceptance',kind='verification',role='qa-engineer',
             files=['tests/acceptance/'],depends_on=['implement'])]))
    try:
        if mutate:
            with pytest.raises(RuntimeError,match='Verification changed application source'):build_ready(w,pid)
            assert s.get(pid)['tasks'][1]['status']=='pending'
        else:
            assert build_ready(w,pid) and s.get(pid)['tasks'][1]['status']=='done'
        assert (root/'source.txt').read_text()=='reviewed source'
        assert calls[1][1] is None and calls[0][2]!=calls[1][2]
        assert '\nRole: qa-engineer\n' in calls[1][3]
        assert len(s.get(pid)['sessions'])==2
    finally:w.shutdown()


@pytest.mark.parametrize('change,error',[
    (lambda p:p['tasks'][0].pop('kind'),'declare its kind'),
    (lambda p:p['tasks'][0].update(requirements=['FR-999']),'unknown requirements'),
    (lambda p:p['tasks'][0].update(acceptance=[]),'acceptance commands'),
    (lambda p:p['tasks'][-1].update(inputs=[]),'input contract'),
    (lambda p:p.update(journeys=[]),'acceptance journeys'),
    (lambda p:p['journeys'][0].update(operations=''),'trigger, operations'),
    (lambda p:p.update(runtime={}),'runtime tools'),
    (lambda p:p['tasks'][-1].update(kind='development'),'final integration'),
])
def test_plan_validation_rejects_missing_executable_contracts(tmp_path,change,error):
    (tmp_path/'requirements.md').write_text('FR-1: Counter increments')
    p=plan_result(parallel_tasks());change(p)
    with pytest.raises(ValueError,match=error):planning.validate_contract(p,parse_tasks(p['tasks']),tmp_path)


@pytest.mark.parametrize('task',[
    dict(id='qa',goal='review',kind='verification',role='sw-developer',files=['tests/']),
    dict(id='qa',goal='review',kind='verification',role='qa-engineer',files=['src/']),
    dict(id='x',goal='unknown',role='invented-role',files=['src/']),
])
def test_reviewer_contracts_cannot_silently_fall_back_to_development(task):
    with pytest.raises(ValueError):parse_tasks([task])


def test_independent_plan_reviewer_can_block_structurally_valid_plan(tmp_path):
    candidate=plan_result(parallel_tasks())
    s,w,pid,root,approvals,calls=project(tmp_path,[candidate])
    original=(root/'plan.md').read_bytes();reviews=[]
    def execute(conn,run):
        role=run.instructions.split('Role: ',1)[1].splitlines()[0]
        if role=='task-planner':calls.append(run.prompt);return candidate
        assert role=='sw-architect' and run.readonly and run.session is None
        reviews.append(run.prompt)
        return dict(verdict='fail',summary='Missing actual operation dispatcher',findings=['Connect request to the account operation'])
    w.execute=execute
    try:
        w.submit(pid,'Plan');wait_idle(w,pid)
        assert len(calls)==2 and len(reviews)==2
        assert not s.inbox(pid) and s.get(pid)['phase']=='plan' and s.get(pid)['paused']
        assert s.get(pid)['approvals']==approvals and (root/'plan.md').read_bytes()==original
    finally:w.shutdown()


def test_old_pending_approval_requires_replan_without_changing_approval_or_inbox(tmp_path):
    s,w,pid,root,approvals,_=project(tmp_path,[plan_result(parallel_tasks())])
    s.update(pid,phase='plan_review',plan_policy='parallel-v1')
    w.review(pid,'plan');before=s.get(pid);item=s.inbox(pid)[0]
    try:
        with pytest.raises(ValueError,match='execution contract'):
            w.answer(pid,item['id'],dict(choice='Approve implementation plan',revision=item['revision']))
        assert s.get(pid)==before and s.inbox(pid)[0]['id']==item['id']
    finally:w.shutdown()


def test_runtime_checks_actual_executable_and_does_not_execute_bootstrap(tmp_path,monkeypatch):
    binary=tmp_path/'node';binary.write_text('#!'+sys.executable+'\nprint("v22.17.0")\n');binary.chmod(0o755)
    monkeypatch.setenv('PATH',str(tmp_path))
    (tmp_path/'package.json').write_text('{"engines":{"node":">=24.13.0"}}')
    runtime=dict(tools=[],bootstrap=['touch should-not-exist'],browser=False)
    with pytest.raises(ValueError,match='requires >= 24.13.0; found 22.17.0'):
        require_runtime(tmp_path,runtime,tmp_path/'browser.mjs')
    assert not (tmp_path/'should-not-exist').exists()
    binary.write_text('#!'+sys.executable+'\nprint("v24.13.0")\n')
    assert require_runtime(tmp_path,runtime,tmp_path/'browser.mjs')['node']=='24.13.0'


def test_runtime_failure_blocks_worker_before_model_and_preserves_project(tmp_path,monkeypatch):
    calls=[];s,w,pid,root=fixture(tmp_path,lambda c,r:calls.append(r))
    binary=tmp_path/'node';binary.write_text('#!'+sys.executable+'\nprint("v22.17.0")\n');binary.chmod(0o755)
    monkeypatch.setenv('PATH',str(tmp_path)+':'+__import__('os').environ['PATH'])
    (root/'package.json').write_text('{"engines":{"node":">=24.13.0"}}')
    s.update(pid,tasks=parse_tasks([dict(id='one',goal='one',files=['src/'])]))
    try:
        with pytest.raises(RuntimeError,match='Runtime preflight'):build_ready(w,pid)
        assert not calls and s.get(pid)['tasks'][0]['status']=='pending'
    finally:w.shutdown()


def test_failed_check_names_actual_command_and_cannot_be_hidden_by_subset_retry(tmp_path):
    calls=[]
    def execute(conn,run):
        calls.append(run.root)
        (run.root/'owned.txt').write_text('proposed change')
        result=evidence(run,command='combined acceptance')
        failed=dict(result['checks'][0],exit_code=1)
        result['checks']=[failed,dict(result['checks'][0],command='targeted retry')]
        return result
    s,w,pid,root=fixture(tmp_path,execute)
    s.update(pid,tasks=parse_tasks([dict(id='one',goal='one change',files=['owned.txt'],
        acceptance=[dict(command='combined acceptance',expect='all checks pass')])]))
    try:
        with pytest.raises(RuntimeError,match=r'one: Worker check failed \(exit 1\): combined acceptance'):
            build_ready(w,pid)
        assert len(calls)==1 and not (root/'owned.txt').exists()
        assert s.get(pid)['tasks'][0]['status']=='pending'
        assert s.get(pid)['workers'][0]['status']=='blocked'
    finally:w.shutdown()


def test_blocked_worker_keeps_its_actual_reason_in_controller_error(tmp_path):
    s,w,pid,_=fixture(tmp_path,lambda c,r:dict(status='blocked',summary='Native audio device is unavailable.'))
    s.update(pid,tasks=s.get(pid)['tasks'][:1])
    try:
        with pytest.raises(RuntimeError,match='front: Worker reported a blocker: Native audio device is unavailable'):
            build_ready(w,pid)
    finally:w.shutdown()


def test_cancelled_invocation_does_not_start_engine_or_record_new_session(tmp_path):
    calls=[]
    s,w,pid,_=fixture(tmp_path,lambda c,r:calls.append(r))
    w.cancelled[pid].set()
    try:
        with pytest.raises(InterruptedError,match='Stopped before starting'):
            w.invoke(pid,'sw-developer','Continue current work')
        assert not calls and not s.get(pid)['sessions']
        assert not any(e['type']=='invocation' for e in s.events(pid))
    finally:w.shutdown()


def test_invocations_record_model_effort_and_instruction_provenance(tmp_path):
    s,w,pid,_=fixture(tmp_path,lambda c,r:dict(status='completed'))
    settings=w.settings();settings.update(model='chosen-model',effort='high');s.save_setting('ai',settings)
    try:
        w.invoke(pid,'task-planner','Read only',readonly=True)
        e=next(e for e in s.events(pid) if e['type']=='invocation')
        assert e['model']=='chosen-model' and e['effort']=='high' and e['source_access']=='read-only'
        assert len(e['instructions_sha256'])==64 and e['run_id']
    finally:w.shutdown()
