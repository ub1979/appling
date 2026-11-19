import json
import subprocess
import threading
import sys
import textwrap
import time
from pathlib import Path

import pytest

from appling import workspaces
from appling.store import Store
from appling.swarm import build_ready, ready_batch
from appling.workflow import ARTIFACTS, Workflow, artifact_revision, parse_tasks


def fixture(tmp_path, execute):
    store=Store(tmp_path/'studio')
    state=store.add(tmp_path/'app',team=['sw-developer','qa-engineer','tech-writer'],execution_mode='planned')
    pid=state['id'];root=Path(state['root'])
    (root/'.gitignore').write_text('.appling/\ndist/\nnode_modules/\n.sdlc/\n')
    for name in ['dist/generated.js','node_modules/dependency/index.js']:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('generated dependency')
    for kind,name in ARTIFACTS.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('FR-001: approved '+kind)
    approvals={kind:artifact_revision(root,kind) for kind in ARTIFACTS}
    tasks=parse_tasks([dict(id='front',goal='frontend',files=['front.txt']),
                       dict(id='back',goal='backend',files=['back.txt']),
                       dict(id='join',goal='integrate',files=['joined.txt'],depends_on=['front','back'])])
    store.update(pid,phase='build',approvals=approvals,tasks=tasks)
    workflow=Workflow(store,execute);workflow.cancelled[pid]=threading.Event()
    return store,workflow,pid,root


def write_result(run, text='done'):
    brief=json.loads(run.prompt);task=(brief.get('worker') or {}).get('task_id')
    name={'front':'front.txt','back':'back.txt'}.get(task,'joined.txt')
    (run.root/name).write_text(text)
    for generated in ['dist/output.js','node_modules/dependency/index.js']:
        path=run.root/generated;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('worker build output')
    if not task:return dict(status='completed')
    path=run.root/brief['worker']['evidence']/'check.txt'
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text('Verified '+name)
    return dict(status='completed',checks=[dict(command='check '+name,exit_code=0,evidence=str(path.relative_to(run.root)))])


def test_parallel_workers_overlap_isolate_sessions_and_integrate_before_dependency(tmp_path):
    barrier=threading.Barrier(2);roots=[]
    def execute(conn,run):
        brief=json.loads(run.prompt);roots.append(run.root)
        if brief['worker']['task_id'] in {'front','back'}:
            assert run.managed_worker
            assert brief['workspace']==str(run.root)
            barrier.wait(timeout=5)
            run.save_session('session-'+brief['worker']['id'])
        else:
            assert (run.root/'front.txt').read_text()=='done'
            assert (run.root/'back.txt').read_text()=='done'
        return write_result(run)
    store,w,pid,root=fixture(tmp_path,execute)
    try:
        assert build_ready(w,pid)
        state=store.get(pid)
        assert len(set(roots))==3 and root not in roots
        assert all(t['status']=='done' for t in state['tasks'])
        assert len(set(state['sessions'].values()))==2
        assert all(worker['status']=='integrated' for worker in state['workers'])
        assert (root/'joined.txt').is_file()
        assert not build_ready(w,pid)
        assert len(list((root/'.sdlc/evidence/workers').rglob('check.txt')))==3
        assert root not in roots and len(set(roots))==3
    finally:w.shutdown()


def test_snapshot_preserves_user_index_head_and_excludes_secrets(tmp_path):
    root=tmp_path/'app';root.mkdir()
    workspaces.git(root,'init','-b','main')
    (root/'existing.txt').write_text('initial')
    workspaces.git(root,'add','existing.txt')
    workspaces.git(root,'-c','user.name=Tester','-c','user.email=test@example.test','commit','-m','initial')
    head=workspaces.git(root,'rev-parse','HEAD')
    (root/'existing.txt').write_text('staged');workspaces.git(root,'add','existing.txt')
    (root/'existing.txt').write_text('unstaged')
    (root/'.env').write_text('PRIVATE_SECRET=must-not-copy')
    (root/'new.txt').write_text('untracked')
    index=(root/'.git/index').read_bytes()
    base=workspaces.snapshot(root)
    workspace=tmp_path/'worker';workspaces.create(root,workspace,base)
    assert (root/'.git/index').read_bytes()==index
    assert workspaces.git(root,'rev-parse','HEAD')==head
    assert (workspace/'existing.txt').read_text()=='unstaged'
    assert (workspace/'new.txt').read_text()=='untracked'
    assert not (workspace/'.env').exists()
    (workspace/'existing.txt').write_text('worker')
    commit=workspaces.snapshot(workspace,base)
    (root/'existing.txt').write_text('new user edit')
    with pytest.raises(ValueError,match='changed since'):
        workspaces.integrate(root,workspace,base,commit,['existing.txt'],'.sdlc/evidence/w/')
    assert (root/'existing.txt').read_text()=='new user edit'
    assert (root/'.git/index').read_bytes()==index


def test_no_parallelism_for_unknown_or_overlapping_ownership():
    for scopes in [([],['b.txt']),(['src/'],['src/a.ts']),(['shared.ts'],['shared.ts'])]:
        tasks=parse_tasks([dict(id='a',goal='a',files=scopes[0]),dict(id='b',goal='b',files=scopes[1])])
        assert len(ready_batch(tasks,3))==1
    for value in [['../escape'],['.git/config'],['/absolute'],['src/*'],['.']]:
        with pytest.raises(ValueError):parse_tasks([dict(id='a',goal='a',files=value)])


def test_out_of_scope_worker_blocked_without_discarding_other_success(tmp_path):
    def execute(conn,run):
        result=write_result(run)
        if json.loads(run.prompt)['worker']['task_id']=='front':(run.root/'unexpected.txt').write_text('surprise')
        return result
    store,w,pid,root=fixture(tmp_path,execute)
    try:
        with pytest.raises(RuntimeError,match='outside its assigned ownership'):build_ready(w,pid)
        state=store.get(pid)
        assert (root/'back.txt').exists() and not (root/'front.txt').exists()
        assert not (root/'unexpected.txt').exists()
        failed=next(worker for worker in state['workers'] if worker['task_id']=='front')
        assert failed['status']=='conflict'
        assert (Path(failed['workspace'])/'unexpected.txt').exists()
    finally:w.shutdown()


def test_stop_and_restart_resume_retained_task_sessions(tmp_path):
    entered=threading.Barrier(3)
    def blocked(conn,run):
        brief=json.loads(run.prompt);run.save_session('saved-'+brief['worker']['id'])
        (run.root/(brief['worker']['task_id']+'.progress')).write_text('unfinished')
        entered.wait(timeout=5)
        run.cancel.wait(5)
        raise InterruptedError('stopped')
    store,w,pid,root=fixture(tmp_path,blocked);errors=[]
    def run_batch():
        try:build_ready(w,pid)
        except InterruptedError as exc:errors.append(str(exc))
    thread=threading.Thread(target=run_batch);thread.start();entered.wait(timeout=5)
    store.update(pid,running=True);w.stop(pid);thread.join(5)
    assert not thread.is_alive();assert errors
    old=store.get(pid)['workers'];old_paths={worker['workspace'] for worker in old}
    w.shutdown()
    resumed=[]
    def resume(conn,run):
        brief=json.loads(run.prompt)
        if brief['worker']['task_id']=='join':return write_result(run)
        assert run.session.startswith('saved-')
        assert (run.root/(brief['worker']['task_id']+'.progress')).exists()
        # Progress scratch file isn't app output: remove it before integration.
        (run.root/(brief['worker']['task_id']+'.progress')).unlink()
        resumed.append(str(run.root));return write_result(run)
    w2=Workflow(store,resume);w2.cancelled[pid]=threading.Event()
    try:
        assert store.get(pid)['paused']
        assert build_ready(w2,pid)
        assert set(resumed)==old_paths
        assert (root/'front.txt').exists() and (root/'back.txt').exists()
    finally:w2.shutdown()


def test_multiple_worker_questions_are_answered_by_exact_id(tmp_path):
    store,w,pid,_=fixture(tmp_path,lambda c,r:{})
    answers={}
    def ask(ident):
        answers[ident]=w.runtime_ask(pid,'question','Which option?',[],worker=dict(id=ident,task_id=ident,role='developer'))
    threads=[threading.Thread(target=ask,args=(ident,)) for ident in ['front','back']]
    try:
        for t in threads:t.start()
        import time
        end=time.monotonic()+3
        while len(store.inbox(pid))<2 and time.monotonic()<end:time.sleep(.01)
        for item in store.inbox(pid):w.answer(pid,item['id'],'answer-'+item['task_id'])
        for t in threads:t.join(3)
        assert answers==dict(front='answer-front',back='answer-back')
        assert not store.inbox(pid)
    finally:w.stop(pid);w.shutdown()


def test_new_plan_does_not_reuse_old_worker_with_recycled_task_id(tmp_path):
    def fail(conn,run):raise RuntimeError('blocked old task')
    store,w,pid,_=fixture(tmp_path,fail)
    try:
        with pytest.raises(RuntimeError):build_ready(w,pid)
        old_paths={worker['workspace'] for worker in store.get(pid)['workers']}
        tasks=store.get(pid)['tasks'];tasks[0]['goal']='entirely different frontend'
        store.update(pid,tasks=tasks,revision=2)
        w.execute=lambda conn,run:write_result(run)
        assert build_ready(w,pid)
        new=[worker for worker in store.get(pid)['workers'] if worker['status']=='integrated']
        assert len(new)==3 and not old_paths & {worker['workspace'] for worker in new}
    finally:w.shutdown()


def test_inroot_symlink_changes_require_manual_review(tmp_path):
    root=tmp_path/'app';root.mkdir();(root/'target').write_text('data')
    base=workspaces.snapshot(root);workspace=tmp_path/'worker';workspaces.create(root,workspace,base)
    (workspace/'link').symlink_to('target');commit=workspaces.snapshot(workspace,base)
    with pytest.raises(ValueError,match='symlinks'):
        workspaces.integrate(root,workspace,base,commit,['link'],'.sdlc/evidence/w/')
    assert not (root/'link').exists()


def test_restart_after_patch_application_finishes_without_reexecution(tmp_path,monkeypatch):
    store,w,pid,root=fixture(tmp_path,lambda conn,run:write_result(run))
    original=workspaces.integrate
    applied=[]
    def simulate_crash(*args,**kwargs):
        names=original(*args,**kwargs)
        applied.append(names)
        raise SystemExit('power loss after apply')
    monkeypatch.setattr(workspaces,'integrate',simulate_crash)
    try:
        with pytest.raises(SystemExit):build_ready(w,pid)
        assert applied and any((root/name).exists() for name in ['front.txt','back.txt'])
        assert any(worker['status']=='integrating' for worker in store.get(pid)['workers'])
        store.update(pid,running=True)
    finally:w.shutdown()
    monkeypatch.setattr(workspaces,'integrate',original)
    def must_not_run(conn,run):
        assert json.loads(run.prompt)['worker']['task_id']=='join', 'Completed worker must not execute again'
        return write_result(run)
    w2=Workflow(store,must_not_run);w2.cancelled[pid]=threading.Event()
    try:
        assert build_ready(w2,pid)
        assert all(task['status']=='done' for task in store.get(pid)['tasks'][:2])
        assert all(worker['status']=='integrated' for worker in store.get(pid)['workers'])
    finally:w2.shutdown()


def test_conflict_retry_reconciles_against_current_source_and_retains_old_attempt(tmp_path):
    root_holder=[]
    def execute(conn,run):
        brief=json.loads(run.prompt)
        result=write_result(run)
        if brief['worker']['task_id']=='front':
            (root_holder[0]/'front.txt').write_text('user change')
        return result
    store,w,pid,root=fixture(tmp_path,execute);root_holder.append(root)
    try:
        with pytest.raises(RuntimeError,match='changed since'):build_ready(w,pid)
        assert (root/'front.txt').read_text()=='user change'
        original=next(worker for worker in store.get(pid)['workers'] if worker['status']=='conflict')
        def reconcile(conn,run):
            if json.loads(run.prompt)['worker']['task_id']=='join':return write_result(run)
            assert (run.root/'.appling/recovery.patch').is_file()
            assert (run.root/'front.txt').read_text()=='user change'
            assert 'Keep my user change' in json.loads(run.prompt)['goal']
            return write_result(run,text='user change plus requested feature')
        w.execute=reconcile
        assert build_ready(w,pid,feedback='Keep my user change')
        assert (root/'front.txt').read_text()=='user change plus requested feature'
        assert Path(original['workspace']).is_dir()
        assert next(worker for worker in store.get(pid)['workers'] if worker['id']==original['id'])['status']=='retained'
    finally:w.shutdown()


def test_edited_retained_worktree_is_reverified_before_reusing_result(tmp_path,monkeypatch):
    store,w,pid,root=fixture(tmp_path,lambda conn,run:write_result(run))
    original=workspaces.integrate
    def crash_before_apply(*args,**kwargs):
        if (Path(args[1])/'front.txt').exists():raise SystemExit('interrupted integration')
        return original(*args,**kwargs)
    monkeypatch.setattr(workspaces,'integrate',crash_before_apply)
    try:
        with pytest.raises(SystemExit):build_ready(w,pid)
        worker=next(worker for worker in store.get(pid)['workers'] if worker['task_id']=='front')
        (Path(worker['workspace'])/'front.txt').write_text('edited retained change')
        calls=[]
        def reverify(conn,run):
            if json.loads(run.prompt)['worker']['task_id']=='join':return write_result(run)
            calls.append(str(run.root))
            assert (run.root/'front.txt').read_text()=='edited retained change'
            return write_result(run,text='reverified edited change')
        w.execute=reverify
        monkeypatch.setattr(workspaces,'integrate',original)
        assert build_ready(w,pid)
        assert calls==[worker['workspace']]
        assert (root/'front.txt').read_text()=='reverified edited change'
    finally:w.shutdown()


def test_legacy_plan_gets_safe_execution_ownership_without_changing_approved_goals(tmp_path):
    calls=[]
    def assess(conn,run):
        assert run.readonly
        calls.append(run.prompt)
        return dict(task_scopes=[dict(id='front',files=['front.txt'],additional_depends_on=[]),
                                dict(id='back',files=['back.txt'],additional_depends_on=[])])
    store,w,pid,root=fixture(tmp_path,assess)
    state=store.get(pid);tasks=state['tasks']
    for task in tasks:task['files']=[]
    store.update(pid,tasks=tasks)
    plan=(root/'plan.md').read_bytes()
    try:
        w.scope_remaining_tasks(pid)
        updated=store.get(pid)
        assert [t['goal'] for t in updated['tasks']]==[t['goal'] for t in tasks]
        assert updated['tasks'][2]['depends_on']==['front','back']
        assert updated['approvals']==state['approvals']
        assert (root/'plan.md').read_bytes()==plan
        assert len(ready_batch(updated['tasks'],3))==2
        w.scope_remaining_tasks(pid)
        assert len(calls)==1
    finally:w.shutdown()


def test_legacy_scope_assessment_cannot_invent_tasks_or_create_dependency_cycles(tmp_path):
    store,w,pid,_=fixture(tmp_path,lambda conn,run:dict(task_scopes=[dict(id='invented',files=['new.txt'])]))
    tasks=store.get(pid)['tasks']
    for task in tasks:task['files']=[]
    store.update(pid,tasks=tasks)
    try:
        with pytest.raises(ValueError,match='unknown'):w.scope_remaining_tasks(pid)
        assert store.get(pid)['tasks']==tasks
        w.execute=lambda conn,run:dict(task_scopes=[dict(id='front',files=['front.txt'],additional_depends_on=['join'])])
        with pytest.raises(ValueError,match='cycle'):w.scope_remaining_tasks(pid)
        assert store.get(pid)['tasks']==tasks
    finally:w.shutdown()


def test_parallel_codex_app_servers_route_permissions_and_integrate_real_process_output(tmp_path):
    from appling.engines import execute
    markers=tmp_path/'native-processes';markers.mkdir()
    binary=tmp_path/'controlled-codex'
    binary.write_text('#!'+sys.executable+'\n'+textwrap.dedent('''
        import json,sys,time
        from pathlib import Path
        def send(data): print(json.dumps(data),flush=True)
        tid=Path.cwd().name
        brief=None
        def finish():
            task=brief['worker']['task_id']
            Path('joined.txt' if task=='join' else task+'.txt').write_text('native '+task)
            evidence=Path(brief['worker']['evidence'])/'check.txt'
            evidence.parent.mkdir(parents=True,exist_ok=True);evidence.write_text('native process check passed')
            result={'status':'completed','checks':[{'command':'verify '+task,'exit_code':0,'evidence':str(evidence)}]}
            send({'method':'thread/tokenUsage/updated','params':{'threadId':tid,'tokenUsage':{'last':{'inputTokens':10,'outputTokens':2}}}})
            send({'method':'item/completed','params':{'threadId':tid,'item':{'type':'agentMessage','text':json.dumps(result)}}})
            send({'method':'turn/completed','params':{'threadId':tid,'turn':{'id':'turn-'+tid,'status':'completed'}}})
        for line in sys.stdin:
            msg=json.loads(line);method=msg.get('method');p=msg.get('params',{})
            if method=='initialize':send({'id':msg['id'],'result':{}})
            elif method=='thread/start':
                assert p['config']['features.multi_agent'] is False
                send({'id':msg['id'],'result':{'thread':{'id':tid}}})
            elif method=='turn/start':
                brief=json.loads(p['input'][0]['text']);task=brief['worker']['task_id']
                markers=Path(MARKERS)
                (markers/task).write_text(str(Path.cwd()))
                if task in {'front','back'}:
                    deadline=time.monotonic()+4
                    while len(list(markers.iterdir()))<2 and time.monotonic()<deadline:time.sleep(.01)
                    assert len(list(markers.iterdir()))==2
                else:
                    assert Path('front.txt').read_text()=='native front'
                    assert Path('back.txt').read_text()=='native back'
                send({'id':msg['id'],'result':{'turn':{'id':'turn-'+tid}}})
                if task=='join':finish()
                else:send({'id':800,'method':'item/commandExecution/requestApproval','params':{'threadId':tid,'command':'verify task '+task}})
            elif msg.get('id')==800:
                assert msg['result']['decision']=='accept'
                finish()
    ''').replace('MARKERS',repr(str(markers))))
    binary.chmod(0o755)
    store,w,pid,root=fixture(tmp_path,execute)
    settings=w.settings();settings['connections']['codex']['binary']=str(binary)
    store.save_setting('ai',settings);errors=[]
    def run_batch():
        try:build_ready(w,pid)
        except BaseException as exc:errors.append(exc)
    thread=threading.Thread(target=run_batch);thread.start()
    try:
        deadline=time.monotonic()+6
        while len(store.inbox(pid))<2 and thread.is_alive() and time.monotonic()<deadline:time.sleep(.01)
        questions=store.inbox(pid)
        assert len(questions)==2,errors
        assert len({q['worker_id'] for q in questions})==2
        for question in questions:w.answer(pid,question['id'],'once')
        thread.join(6)
        assert not thread.is_alive() and not errors
        assert (root/'front.txt').read_text()=='native front'
        assert (root/'back.txt').read_text()=='native back'
        assert (root/'joined.txt').read_text()=='native join'
        assert len(store.get(pid)['sessions'])==3
        usage=[event for event in store.events(pid) if event['type']=='usage']
        assert len({event['run_id'] for event in usage})==3
    finally:
        w.stop(pid);thread.join(5);w.shutdown()
