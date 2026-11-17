import json
import threading
import time
from pathlib import Path
import pytest
from appling.store import Store, safe_path
from appling.workflow import Workflow, artifact_revision, parse_tasks


def wait_idle(workflow,pid):
    deadline=time.monotonic()+5
    while pid in workflow.active and time.monotonic()<deadline:
        time.sleep(.01)
    assert pid not in workflow.active


class Builder:
    def __init__(self):
        self.roles=[];self.bad_qa=False
    def __call__(self,connection,run):
        role=run.instructions.split('Role: ',1)[1].splitlines()[0]
        self.roles.append(role)
        run.save_session('session-'+role)
        if role=='req-engineer':
            return {'summary':'Requirements drafted.','requirements':'# Counter\nFR-1: Increment the counter when clicked.\nAcceptance: 0 becomes 1.'}
        if role=='ui-designer':
            (run.root/'prototypes').mkdir(exist_ok=True)
            (run.root/'prototypes/index.html').write_text('<button onclick="this.textContent=1">0</button>')
            return {'summary':'Try the counter.','status':'completed'}
        if role=='task-planner':
            return {'summary':'One task.','plan':'Build a working counter and test the click.',
                    'tasks':[{'id':'counter','goal':'Build counter','depends_on':[]}]}
        if role=='sw-developer':
            (run.root/'index.html').write_text('<button onclick="this.textContent=1">0</button>')
            return {'summary':'Counter implemented.','status':'completed'}
        if role=='qa-engineer':
            if getattr(self,'mutate_qa',False):
                (run.root/'index.html').write_text('QA unexpectedly edited the application')
            p=run.root/'.sdlc/evidence/check.json';p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text('{"click": "0 becomes 1"}')
            return {'summary':'Checked.','verdict':'pass','browser_tested':not self.bad_qa,
                    'checks':[{'command':'browser click increment','exit_code':0,'evidence':str(p.relative_to(run.root)),'requirements':['FR-1']}]}
        if role=='change-manager':
            return {'summary':'Apply the requested small fix.','action':'fix','goal':'Fix counter spacing'}
        raise AssertionError(role)


@pytest.fixture
def project(tmp_path):
    store=Store(tmp_path/'studio.db');builder=Builder();workflow=Workflow(store,builder)
    p=store.add(tmp_path/'app',team=['req-engineer','task-planner','sw-developer','qa-engineer'])
    yield store,workflow,p['id'],builder
    workflow.shutdown()


def approve(store,workflow,pid,kind):
    wait_idle(workflow,pid)
    item=store.inbox(pid)[0]
    assert item['kind']==kind
    workflow.answer(pid,item['id'],{'choice':item['choices'][0],'revision':item['revision']})
    wait_idle(workflow,pid)


def test_full_pipeline_preserves_gates_and_follow_up(project):
    store,w,pid,builder=project
    w.submit(pid,'Make a counter with smart defaults');wait_idle(w,pid)
    assert 'sw-developer' not in builder.roles
    approve(store,w,pid,'prototype')
    assert 'task-planner' not in builder.roles
    approve(store,w,pid,'requirements')
    assert 'sw-developer' not in builder.roles
    approve(store,w,pid,'plan')
    assert store.get(pid)['phase']=='delivered'
    assert store.get(pid)['tasks'][0]['status']=='done'
    assert store.last_checkpoint(pid,'sw-developer')
    assert store.search(pid,'counter')
    w.submit(pid,'Fix the button spacing');wait_idle(w,pid)
    assert store.get(pid)['phase']=='delivered'
    assert builder.roles.count('req-engineer')==1
    assert builder.roles.count('qa-engineer')==2


def test_modified_prototype_cannot_use_old_approval(project):
    store,w,pid,_=project;w.submit(pid,'Counter');wait_idle(w,pid)
    item=store.inbox(pid)[0]
    (Path(store.get(pid)['root'])/'prototypes/index.html').write_text('changed')
    with pytest.raises(ValueError,match='changed'):
        w.answer(pid,item['id'],{'choice':'Approve prototype','revision':item['revision']})
    assert not store.get(pid)['approvals']


def test_implementation_cannot_bypass_missing_approval(project):
    store,w,pid,builder=project
    store.update(pid,phase='build',tasks=[{'id':'a','goal':'build','status':'pending','depends_on':[]}])
    w.submit(pid,'go');wait_idle(w,pid)
    assert not builder.roles
    assert store.get(pid)['paused']
    assert not (Path(store.get(pid)['root'])/'index.html').exists()


def test_qa_cannot_pass_without_browser(project):
    store,w,pid,builder=project;builder.bad_qa=True
    w.submit(pid,'Counter');wait_idle(w,pid)
    for kind in ['prototype','requirements','plan']:
        approve(store,w,pid,kind)
    assert store.get(pid)['phase']=='qa'
    assert store.get(pid)['paused']


def test_qa_requires_coverage_of_approved_requirement_ids(project):
    store,w,pid,_=project;root=Path(store.get(pid)['root'])
    (root/'requirements.md').write_text('FR-001: Add items\nFR-002: Delete items')
    (root/'evidence.txt').write_text('Added item successfully')
    report=dict(browser_tested=True,checks=[dict(command='browser add',exit_code=0,evidence='evidence.txt',requirements=['FR-001'])])
    assert not w.valid_evidence(pid,report,require_browser=True)
    report['checks'][0]['requirements'].append('FR-002')
    assert w.valid_evidence(pid,report,require_browser=True)


def test_qa_source_changes_invalidate_its_verdict(project):
    store,w,pid,builder=project;builder.mutate_qa=True
    w.submit(pid,'Counter');wait_idle(w,pid)
    for kind in ['prototype','requirements','plan']:
        approve(store,w,pid,kind)
    assert store.get(pid)['phase']=='qa'
    assert store.get(pid)['paused']
    assert any('changed application source' in m['content'] for m in store.messages(pid))


def test_restart_preserves_approvals_and_pauses_active_work(tmp_path):
    path=tmp_path/'state.db';store=Store(path);p=store.add(tmp_path/'app')
    store.update(p['id'],running=True,phase='build',approvals={'requirements':'revision'})
    other=Store(path);workflow=Workflow(other,Builder())
    try:
        state=other.get(p['id']);assert state['paused'];assert not state['running']
        assert state['approvals']=={'requirements':'revision'}
        assert not workflow.active
    finally:
        workflow.shutdown()


def test_stop_cancels_runtime_question_and_does_not_deliver(tmp_path):
    store=Store(tmp_path/'state.db');p=store.add(tmp_path/'app');entered=threading.Event()
    def blocked(conn,run):
        entered.set();run.ask('approval','Run a command?',['once','deny'])
    w=Workflow(store,blocked)
    try:
        w.submit(p['id'],'Build app');assert entered.wait(2)
        deadline=time.monotonic()+2
        while not store.inbox(p['id']) and time.monotonic()<deadline:
            time.sleep(.01)
        w.stop(p['id']);wait_idle(w,p['id'])
        assert store.get(p['id'])['paused'];assert not store.inbox(p['id'])
        assert store.get(p['id'])['phase']!='delivered'
    finally:
        w.shutdown()


def test_memory_is_project_scoped_and_replaces_stale_facts(tmp_path):
    store=Store(tmp_path/'state.db');a=store.add(tmp_path/'a');b=store.add(tmp_path/'b')
    store.remember(a['id'],'decision','Use a purple counter')
    assert not store.search(b['id'],'purple')
    store.remember(a['id'],'decision','Use a green counter')
    assert not store.search(a['id'],'purple')
    assert store.search(a['id'],'green')


def test_paths_cannot_escape_through_parent_or_symlink(tmp_path):
    root=tmp_path/'app';root.mkdir();outside=tmp_path/'secret';outside.write_text('private')
    (root/'link').symlink_to(outside)
    for name in ['../secret','link','.git/config']:
        with pytest.raises(ValueError):
            safe_path(root,name)


def test_task_dependencies_reject_cycles_and_missing_ids():
    for tasks in [[{'id':'a','goal':'x','depends_on':['b']}],
                  [{'id':'a','goal':'x','depends_on':['b']},{'id':'b','goal':'x','depends_on':['a']}]]:
        with pytest.raises(ValueError):
            parse_tasks(tasks)
    assert parse_tasks([{'id':'b','goal':'second','depends_on':['a']},{'id':'a','goal':'first'}])


def test_question_and_multiline_answer_survive_in_normal_conversation(tmp_path):
    store=Store(tmp_path/'studio.db');p=store.add(tmp_path/'app')
    w=Workflow(store,lambda conn,run:{'question':'Which users need access?','choices':['Me','My team']})
    try:
        store.ask(p['id'],'question','What would you like to build?',[])
        answer='Track spending.\nGroup transactions.\nShow monthly totals.\nSupport several accounts.\nKeep my data private.'
        w.submit(p['id'],answer);wait_idle(w,p['id'])
        messages=store.messages(p['id'])
        assert messages[0]['role']=='assistant';assert messages[0]['content']=='What would you like to build?'
        assert messages[1]['role']=='user';assert messages[1]['content']==answer
        assert messages[-1]['content']=='Which users need access?'
        assert sum(m['content']=='What would you like to build?' for m in messages)==1
        assert Store(tmp_path/'studio.db').messages(p['id'])==messages
        assert store.get(p['id'])['requirements_notes']==[answer]
    finally:w.shutdown()
