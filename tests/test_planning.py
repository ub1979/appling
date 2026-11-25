"""Exercise planning validation through the controller and real persisted projects."""
import copy
import hashlib
import json
import threading
import time
from pathlib import Path

import pytest

from appling import planning
from appling import context
from appling.store import Store
from appling.swarm import ready_batch
from appling.workflow import Workflow, artifact_revision, parse_tasks
from plan_fixtures import plan_result


def parallel_tasks():
    return [dict(id='contracts',goal='Establish shared contract',files=['shared.py']),
            dict(id='ui',goal='UI against contract',files=['ui/'],depends_on=['contracts']),
            dict(id='api',goal='API against contract',files=['api/'],depends_on=['contracts']),
            dict(id='integration',goal='Check combined app',files=['main.py'],depends_on=['ui','api'])]


@pytest.mark.parametrize('tasks',[
    [dict(id='all',goal='Build entire app',files=['src/'])],
    [dict(id='a',goal='First',files=['a.py']),dict(id='b',goal='Second',files=['b.py'],depends_on=['a'])],
    [dict(id='a',goal='First'),dict(id='b',goal='Second')],
    [dict(id='a',goal='First',files=['src/']),dict(id='b',goal='Second',files=['src/b.py'])],
])
def test_serial_and_unowned_plans_are_rejected(tasks):
    with pytest.raises(ValueError,match='one agent|ownership'):
        planning.execution_waves(parse_tasks(tasks),3)


def test_computed_waves_match_real_scheduler_and_preserve_original_tasks():
    tasks=parse_tasks(parallel_tasks());before=copy.deepcopy(tasks)
    waves=planning.execution_waves(tasks,3)
    assert waves==[['contracts'],['ui','api'],['integration']]
    assert tasks==before
    for wave in waves:
        batch=ready_batch(tasks,3)
        assert [task['id'] for task in batch]==wave
        for task in batch:task['status']='done'


def test_serial_bottlenecks_do_not_hide_a_later_parallel_wave():
    tasks=parse_tasks([dict(id='setup',goal='Shared setup',files=['package.json']),
        *[dict(id=name,goal=name,files=[name+'/'],depends_on=['setup']) for name in ['front','back','accounts','speech']]])
    waves=planning.execution_waves(tasks,2)
    assert waves[0]==['setup']
    assert max(map(len,waves))==2
    assert {ident for wave in waves for ident in wave}=={task['id'] for task in tasks}


def wait_idle(workflow,pid):
    deadline=time.monotonic()+5
    while pid in workflow.active and time.monotonic()<deadline:time.sleep(.01)
    assert pid not in workflow.active


def project(tmp_path,results):
    store=Store(tmp_path/'state');state=store.add(tmp_path/'app',execution_mode='planned',team=['req-engineer','task-planner']);pid=state['id'];root=Path(state['root'])
    (root/'requirements.md').write_text('FR-1: Keep approved behavior')
    (root/'prototypes').mkdir();(root/'prototypes/index.html').write_text('Approved design')
    (root/'existing.py').write_text('valuable existing work')
    (root/'plan.md').write_text('Previous plan kept until a valid replacement exists')
    approvals={kind:artifact_revision(root,kind) for kind in ['requirements','prototype']}
    store.update(pid,phase='plan',approvals=approvals)
    calls=[]
    def execute(conn,run):
        assert run.readonly
        if '\nRole: sw-architect\n' in run.instructions:
            return dict(verdict='pass',summary='Counter journey and integration contract cover FR-1.',findings=[])
        calls.append(json.loads(run.prompt)['goal'])
        return results[min(len(calls)-1,len(results)-1)]
    workflow=Workflow(store,execute)
    return store,workflow,pid,root,approvals,calls


def test_bad_plan_gets_one_correction_then_only_valid_plan_is_reviewed(tmp_path):
    bad=dict(summary='Serial',plan='Three giant serial tasks',tasks=[dict(id='a',goal='Entire app')])
    good=plan_result(parallel_tasks())
    store,w,pid,root,approvals,calls=project(tmp_path,[bad,good])
    try:
        w.submit(pid,'Replan implementation only');wait_idle(w,pid)
        assert len(calls)==2 and 'missing: a' in calls[1]
        state=store.get(pid)
        assert state['phase']=='plan_review' and state['plan_policy']==planning.POLICY
        assert state['approvals']==approvals
        assert {kind:artifact_revision(root,kind) for kind in approvals}==approvals
        assert (root/'existing.py').read_text()=='valuable existing work'
        assert '| 2 | ui, api | 2 |' in (root/'plan.md').read_text()
        assert store.inbox(pid)[0]['revision']==artifact_revision(root,'plan')
        assert not state.get('workers')
    finally:w.shutdown()


def test_repeated_invalid_plan_pauses_without_replacing_plan_or_starting_build(tmp_path):
    invalid=dict(plan='Lead has workers in prose only',tasks=[dict(id='lead',goal='Build everything',files=['src/'])])
    store,w,pid,root,approvals,calls=project(tmp_path,[invalid])
    previous=(root/'plan.md').read_bytes()
    try:
        w.submit(pid,'Replan');wait_idle(w,pid)
        state=store.get(pid)
        assert len(calls)==2
        assert state['paused'] and state['phase']=='plan'
        assert state['approvals']==approvals and not state['tasks']
        assert not store.inbox(pid) and not state.get('workers')
        assert (root/'plan.md').read_bytes()==previous
        assert any('could not produce a safe parallel plan' in message['content'] for message in store.messages(pid))
    finally:w.shutdown()


def test_capacity_one_blocks_before_model_and_after_plan_approval(tmp_path):
    good=plan_result(parallel_tasks())
    store,w,pid,root,approvals,calls=project(tmp_path,[good])
    try:
        settings=w.settings();settings['parallel_work']['agents_per_project']=1;store.save_setting('ai',settings)
        w.submit(pid,'Plan');wait_idle(w,pid)
        assert not calls and store.get(pid)['paused']
        settings['parallel_work']['agents_per_project']=3;store.save_setting('ai',settings)
        w.submit(pid,'Plan');wait_idle(w,pid)
        item=store.inbox(pid)[0]
        settings['parallel_work']['agents_per_project']=1;store.save_setting('ai',settings)
        w.answer(pid,item['id'],{'choice':'Approve implementation plan','revision':item['revision']});wait_idle(w,pid)
        assert len(calls)==1
        state=store.get(pid)
        assert state['phase']=='build' and state['paused'] and not state.get('workers')
        assert all(task['status']=='pending' for task in state['tasks'])
    finally:w.shutdown()


def test_replan_tells_the_owner_when_it_changes_the_build_mode(tmp_path):
    store,w,pid,root,approvals,calls=project(tmp_path,[plan_result(parallel_tasks())])
    store.update(pid,phase='build',execution_mode='direct')
    try:
        w.submit(pid,'/replan Split the work');wait_idle(w,pid)
        assert store.get(pid)['execution_mode']=='planned'
        assert any('now uses the planned build' in m['content'] for m in store.messages(pid))
    finally:w.shutdown()


def test_replan_command_preserves_approved_inputs_and_existing_code(tmp_path):
    good=plan_result(parallel_tasks())
    store,w,pid,root,approvals,calls=project(tmp_path,[good])
    previous=parse_tasks([dict(id='old',goal='Original implementation')]);previous[0]['status']='done'
    store.update(pid,phase='build',tasks=previous,
                 approvals={**approvals,'plan':artifact_revision(root,'plan')})
    try:
        w.submit(pid,'/replan Use useful parallel workers');wait_idle(w,pid)
        assert len(calls)==1
        state=store.get(pid)
        assert state['phase']=='plan_review' and state['approvals']==approvals
        assert state['revision']==1 and not state.get('workers')
        assert {kind:artifact_revision(root,kind) for kind in approvals}==approvals
        assert (root/'existing.py').read_text()=='valuable existing work'
        with store.connect() as conn:
            records=conn.execute("SELECT data FROM checkpoints WHERE project=? AND role LIKE 'plan-history:%'",(pid,)).fetchall()
        assert json.loads(records[0][0])['tasks']==previous
    finally:w.shutdown()


@pytest.mark.parametrize('mode',['active','changed_requirements','changed_design'])
def test_replan_cannot_race_worker_or_bypass_changed_approval(tmp_path,mode):
    good=plan_result(parallel_tasks())
    store,w,pid,root,approvals,calls=project(tmp_path,[good])
    if mode=='active':w.active[pid]=True
    elif mode=='changed_requirements':(root/'requirements.md').write_text('unapproved change')
    else:(root/'prototypes/index.html').write_text('unapproved design')
    before=store.get(pid);plan=(root/'plan.md').read_bytes()
    try:
        with pytest.raises(ValueError,match='Stop the project|needs approval'):
            w.submit(pid,'/replan')
        assert store.get(pid)==before and not calls
        assert (root/'plan.md').read_bytes()==plan
    finally:
        w.active.pop(pid,None);w.shutdown()


def test_capacity_in_briefing_changes_without_mutating_stable_instructions(tmp_path):
    store=Store(tmp_path/'state');state=store.add(tmp_path/'app');pid=state['id']
    before=context.instructions('task-planner')
    store.save_setting('ai',dict(parallel_work=dict(agents_per_project=5,max_workers=2)))
    brief=json.loads(context.briefing(store,pid,'task-planner','Plan'))
    assert brief['execution']['agents_per_project']==5
    assert brief['execution']['max_concurrent_projects']==2
    assert context.instructions('task-planner')==before


@pytest.mark.parametrize('reject_first',[False,True])
def test_replacement_review_uses_candidate_and_host_roles_without_adopting_early(tmp_path,reject_first):
    candidate=plan_result([*parallel_tasks(),dict(id='qa',goal='Independent acceptance',
        kind='verification',role='qa-engineer',files=['tests/acceptance/'],depends_on=['integration'])])
    corrected=copy.deepcopy(candidate)
    corrected['tasks'][1]['goal']='Corrected UI journey'
    store,w,pid,root,approvals,_=project(tmp_path,[candidate])
    previous=parse_tasks([dict(id='qa',goal='Legacy QA assignment',role='sw-developer',files=['old/'])])
    store.update(pid,tasks=previous,plan_contract=dict(legacy=True))
    # Reproduce stale project memory and a resumable session created by the old briefing.
    context.checkpoint(store,pid,'task-planner','Old plan',dict(tasks=previous),'plan')
    old_brain=(root/'.sdlc/project-brain.md').read_text()
    store.remember(pid,'old-plan','Replacement implementation plan: QA uses sw-developer')
    before_instructions=context.instructions('task-planner')
    key,conn,selection=w.connection('task-planner')
    fingerprint=hashlib.sha256((key+json.dumps(conn,sort_keys=True)+selection.get('model','')+
        selection.get('effort','')+before_instructions).encode()).hexdigest()[:16]
    store.update(pid,sessions={'task-planner:'+fingerprint+':planner-'+planning.POLICY:'stale-session'})
    proposals=[];reviews=[]
    def execute(conn,run):
        b=json.loads(run.prompt)
        assert run.readonly and b['selected_roles']==['req-engineer','task-planner']
        assert {'sw-developer','qa-engineer'}<=set(b['available_roles'])
        assert store.get(pid)['tasks']==previous and store.get(pid)['plan_contract']==dict(legacy=True)
        assert store.get(pid)['approvals']==approvals
        assert (root/'plan.md').read_text()=='Previous plan kept until a valid replacement exists'
        assert 'tasks' not in b and 'plan_contract' not in b
        if '\nRole: task-planner\n' in run.instructions:
            assert run.session==('proposal-session' if proposals else None)
            assert b['planning']['stage']=='proposal'
            assert b['planning']['previous_plan']['tasks']==previous
            if not proposals:
                assert b['planning']['previous_plan']['project_brain']==old_brain
            run.save_session('proposal-session')
            proposals.append(b)
            return copy.deepcopy(corrected if len(proposals)>1 else candidate)
        assert '\nRole: sw-architect\n' in run.instructions and run.session is None
        assert b['planning']['stage']=='review' and 'previous_plan' not in b['planning']
        assert not b['relevant_memory'] and b['checkpoint'] is None
        assert '.sdlc/project-brain.md' not in b['documents']
        expected=corrected if len(reviews) else candidate
        reviewed=b['planning']['candidate']
        assert reviewed['tasks']==parse_tasks(expected['tasks'])
        assert reviewed['runtime']==expected['runtime'] and reviewed['journeys']==expected['journeys']
        assert next(t for t in reviewed['tasks'] if t['id']=='qa')['role']=='qa-engineer'
        reviews.append(b)
        if reject_first and len(reviews)==1:
            return dict(verdict='fail',summary='UI journey needs correction',findings=['Correct UI journey'])
        return dict(verdict='pass',summary='Candidate has supported roles and independent QA.',findings=[])
    w.execute=execute
    try:
        w.submit(pid,'Replan implementation');wait_idle(w,pid)
        assert len(proposals)==len(reviews)==(2 if reject_first else 1)
        state=store.get(pid)
        expected=corrected if reject_first else candidate
        assert state['phase']=='plan_review' and state['tasks']==parse_tasks(expected['tasks'])
        assert state['approvals']==approvals and not state.get('workers')
        assert {kind:artifact_revision(root,kind) for kind in approvals}==approvals
        assert store.inbox(pid)[0]['revision']==artifact_revision(root,'plan')
        assert context.instructions('task-planner')==before_instructions
    finally:w.shutdown()


def test_planning_repairs_all_accumulated_findings_before_owner_review(tmp_path):
    original=plan_result(parallel_tasks())
    store,w,pid,root,approvals,_=project(tmp_path,[original]);proposals=[];reviews=[]
    def execute(conn,run):
        b=json.loads(run.prompt);p=b['planning']
        assert store.get(pid)['approvals']==approvals and not store.inbox(pid)
        if p['stage']=='proposal':
            if proposals:
                assert p['draft']['candidate']==proposals[-1]
                assert p['draft']['reviews']==reviews
            candidate=copy.deepcopy(original)
            candidate['tasks'][0]['goal']+=' correction '+str(len(proposals))
            proposals.append(candidate);return candidate
        assert store.get(pid)['plan_draft']['candidate']==proposals[-1]
        assert p['prior_reviews']==reviews
        if len(reviews)<2:
            result=dict(verdict='fail',summary='Concrete journey gap',findings=[['Resume provider after review','Bind meeting audio'][len(reviews)]])
        else:result=dict(verdict='pass',summary='All journeys have executable owners and checks.',findings=[])
        reviews.append(result);return result
    w.execute=execute
    try:
        w.submit(pid,'Correct implementation plan');wait_idle(w,pid)
        assert len(proposals)==len(reviews)==3
        state=store.get(pid)
        assert state['phase']=='plan_review' and state['plan_draft'] is None
        assert state['approvals']==approvals and not state.get('workers')
        assert state['tasks']==parse_tasks(proposals[-1]['tasks'])
        assert store.inbox(pid)[0]['revision']==artifact_revision(root,'plan')
    finally:w.shutdown()


@pytest.mark.parametrize('change_source',[False,True])
def test_paused_plan_resumes_saved_corrections_after_restart_unless_source_changes(tmp_path,change_source):
    candidate=plan_result(parallel_tasks())
    store,w,pid,root,approvals,_=project(tmp_path,[candidate]);reviews=[]
    def reject(conn,run):
        if json.loads(run.prompt)['planning']['stage']=='proposal':return copy.deepcopy(candidate)
        result=dict(verdict='fail',summary='Missing actual continuation',findings=['Wire provider result continuation'])
        reviews.append(result);return result
    w.execute=reject
    w.submit(pid,'Plan');wait_idle(w,pid);w.shutdown()
    assert len(reviews)==2  # Stop unchanged responses rather than spending the full budget.
    draft=store.get(pid)['plan_draft']
    assert draft['candidate']==candidate and draft['reviews']==reviews
    assert not store.inbox(pid) and not store.get(pid)['tasks']
    if change_source:(root/'existing.py').write_text('newer owner source')
    calls=[]
    def correct(conn,run):
        p=json.loads(run.prompt)['planning'];calls.append(p['stage'])
        if p['stage']=='proposal':
            if change_source:assert 'draft' not in p
            else:assert p['draft']==dict(candidate=candidate,reviews=reviews)
            return copy.deepcopy(candidate)
        assert p['prior_reviews']==([] if change_source else reviews)
        return dict(verdict='pass',summary='Continuation is specified and checked.',findings=[])
    w=Workflow(store,correct)
    try:
        w.submit(pid,'Continue correction');wait_idle(w,pid)
        assert calls==['proposal','review']
        assert store.get(pid)['phase']=='plan_review' and store.get(pid)['approvals']==approvals
        assert store.get(pid)['plan_draft'] is None
    finally:w.shutdown()


def test_interrupt_during_review_keeps_latest_candidate_without_adopting(tmp_path):
    candidate=plan_result(parallel_tasks())
    store,w,pid,root,approvals,_=project(tmp_path,[candidate])
    previous=(root/'plan.md').read_bytes()
    def execute(conn,run):
        if json.loads(run.prompt)['planning']['stage']=='proposal':return copy.deepcopy(candidate)
        raise InterruptedError('Review interrupted')
    w.execute=execute
    try:
        w.submit(pid,'Plan');wait_idle(w,pid)
        state=store.get(pid)
        assert state['plan_draft']['candidate']==candidate
        assert state['approvals']==approvals and state['tasks']==[] and not store.inbox(pid)
        assert (root/'plan.md').read_bytes()==previous
    finally:w.shutdown()


def test_bundled_skill_links_resolve_to_complete_readable_skills():
    import re
    from appling.tools import execute
    from appling.engines import Run
    run=Run(root=Path.cwd(),instructions='',prompt='')
    for skill in (context.ROOT/'skills').glob('*/SKILL.md'):
        for name in re.findall(r'skills/([a-z0-9-]+)/SKILL\.md',skill.read_text()):
            assert execute(run,'read_skill',dict(name=name))==(context.ROOT/'skills'/name/'SKILL.md').read_text()
