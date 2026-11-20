"""A durable state machine. Only the controller advances approval gates."""
from __future__ import annotations
import hashlib
import json
import re
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from . import context, engines
from .engines import Run
from .store import safe_path
from .workspaces import ownership
from . import planning
from . import acceptance

ARTIFACTS = {'prototype':'prototypes/index.html','requirements':'requirements.md','plan':'plan.md','blocks':'blocks.md'}
CHOICES = {'prototype':['Approve prototype','Request changes'],
           'requirements':['Approve requirements','Request changes'],
           'plan':['Approve implementation plan','Request changes'],
           'blocks':['Approve block plan','Request changes']}
ROLES = {'requirements':'req-engineer','prototype':'ui-designer','plan':'task-planner',
         'build':'sw-developer','qa':'qa-engineer','security':'security-auditor','deploy':'devops-engineer'}


class WorkWaiting(Exception):
    """Expected retained work, never an engine failure or release approval."""
    def __init__(self, message, *, reason, blockers):
        super().__init__(message)
        self.reason = reason
        self.blockers = blockers


def coding_phase(state):
    """Where coding work (repairs, continuations, in-scope fixes) goes in each mode."""
    return 'body' if state.get('execution_mode')=='blocks' else 'build'


def artifact_revision(root, kind):
    names=[ARTIFACTS[kind]]
    if kind=='blocks' and safe_path(root,'.sdlc/blocks.json').is_file():
        names.append('.sdlc/blocks.json')
    if kind=='requirements' and safe_path(root,acceptance.SPEC).is_file():
        # Criteria and owner prerequisites are approved with the requirements.
        names.append(acceptance.SPEC)
    if kind=='prototype':
        names=[str(p.relative_to(root)) for p in sorted((root/'prototypes').rglob('*'))
               if p.is_file() and not p.is_symlink()]
    digest=hashlib.sha256()
    if not names:
        return None
    for name in names:
        p=safe_path(root,name)
        if not p.is_file():
            return None
        digest.update(name.encode());digest.update(p.read_bytes())
    return digest.hexdigest()


def parse_tasks(value):
    if not isinstance(value,list) or not value:
        raise ValueError('The plan must contain at least one bounded implementation task.')
    tasks=[];ids=set()
    for task in value:
        if not isinstance(task,dict) or not isinstance(task.get('id'),str) or not isinstance(task.get('goal'),str) or not task['id'] or not task['goal']:
            raise ValueError('Every task needs an ID and a goal.')
        if task['id'] in ids:
            raise ValueError('Task IDs must be unique.')
        ids.add(task['id'])
        deps=task.get('depends_on',[])
        if not isinstance(deps,list) or any(not isinstance(dep,str) for dep in deps):
            raise ValueError('Task dependencies must be a list of task IDs.')
        kind=task.get('kind','development')
        role=task.get('role','qa-engineer' if kind=='verification' else 'sw-developer')
        planning.validate_role(kind,role,ownership(task.get('files',[])))
        tasks.append(dict(id=task['id'],goal=task['goal'],depends_on=deps,kind=kind,
                          role=role,files=ownership(task.get('files',[])),status='pending',
                          **{k:task[k] for k in ['requirements','inputs','outputs','acceptance'] if k in task}))
    done=set()
    while len(done)<len(tasks):
        ready=[t for t in tasks if t['id'] not in done and set(t['depends_on'])<=done]
        if not ready:
            raise ValueError('The task plan has missing dependencies or a cycle.')
        done.update(t['id'] for t in ready)
    return tasks


def source_revision(root):
    """Bind QA evidence to the source it actually examined, ignoring artifacts."""
    import os
    digest=hashlib.sha256()
    skip={'.git','.appling','.sdlc','node_modules','.venv','dist','build','out','coverage','test-results','playwright-report','__pycache__'}
    for base,dirs,files in os.walk(root):
        dirs[:]=sorted(d for d in dirs if d not in skip)
        for name in sorted(files):
            path=Path(base)/name
            if path.is_symlink() or name.startswith('.env') or name in {'bug-report.md','security-report.md','code-review-report.md','qa-report.md'}:
                continue
            digest.update(str(path.relative_to(root)).encode());digest.update(path.read_bytes())
    return digest.hexdigest()


class Workflow:
    def __init__(self,store,execute=engines.execute):
        self.store=store;self.execute=execute
        self.pool=ThreadPoolExecutor(max_workers=8,thread_name_prefix='appling-project')
        self.lock=threading.RLock();self.active={};self.cancelled={};self.answers={}
        self.started=time.time()
        for p in store.projects():
            if p.get('running'):
                workers=p.get('workers',[])
                for worker in workers:
                    if worker['status']=='running':worker['status']='interrupted'
                tasks=p['tasks']
                for task in tasks:
                    if task['status']=='running':task['status']='pending'
                store.update(p['id'],running=False,paused=True,workers=workers,tasks=tasks,native_helpers={})
                store.message(p['id'],'assistant','Appling restarted. Your files and task checkpoints are saved. Send a message to continue.','status')
            for item in store.inbox(p['id']):
                if item['kind'] in {'approval','question'} and item.get('runtime'):
                    store.close(p['id'],item['id'])

    def settings(self):
        return self.store.setting('ai',dict(provider='codex',model='',effort='',about_me='',agent_models={},
            parallel_work=dict(max_workers=3,agents_per_project=3),connections=default_connections()))

    def connection(self,role):
        s=self.settings();selection=s.get('agent_models',{}).get(role) or s
        key=selection.get('provider',s['provider'])
        conn=s['connections'].get(key)
        if not conn:
            raise ValueError(f'Connection {key} is not configured. Choose a connection in Settings.')
        return key,conn,selection

    def submit(self,pid,text,kind='user'):
        text=text.strip()
        if not text:
            raise ValueError('Write a message first.')
        if kind=='user' and text.split(maxsplit=1)[0]=='/replan':
            return self.replan(pid,text)
        if kind=='user' and text.split(maxsplit=1)[0]=='/criteria':
            return self.propose_criteria(pid,text)
        with self.lock:
            pending=[i for i in self.store.inbox(pid) if (i['kind']=='question' or i['kind'] in ARTIFACTS)
                     and not (i.get('runtime') and self.cancelled.get(pid,threading.Event()).is_set())]
            if len(pending)==1:
                item=pending[0]
                answer=text if item['kind']=='question' else dict(choice='Request changes',feedback=text)
                return self.answer(pid,item['id'],answer)
            if kind=='user':
                self.store.message(pid,'user',text)
            state=self.store.get(pid)
            if state['phase']=='requirements':
                self.store.update(pid,requirements_notes=[*state.get('requirements_notes',[]),text])
            item=dict(id=uuid.uuid4().hex,text=text,kind=kind)
            self.store.update(pid,paused=False,attention=None,queue=[*state['queue'],item])
            self.store.event(pid,'queued',item=item)
            self._start(pid)
            return item

    def propose_criteria(self,pid,text):
        """Add acceptance criteria to existing approved requirements; the owner re-approves them."""
        with self.lock:
            state=self.store.get(pid)
            if pid in self.active or state['running']:
                raise ValueError('Stop the project and wait for its worker to finish before changing acceptance criteria.')
            root=Path(state['root'])
            if not safe_path(root,'requirements.md').is_file() or not state['approvals'].get('prototype'):
                raise ValueError('Acceptance criteria can be added after the requirements and prototype have been reviewed.')
            if any(item['kind'] not in {'requirements','plan'} for item in self.store.inbox(pid)):
                raise ValueError('Resolve the pending question or review before changing acceptance criteria.')
            for item in self.store.inbox(pid):self.store.close(pid,item['id'])
            self.store.checkpoint(pid,'criteria-history:'+uuid.uuid4().hex,dict(phase=state['phase'],approvals=state['approvals']))
            self.store.update(pid,phase='criteria',queue=[],paused=False,attention=None)
            self.store.message(pid,'user',text)
            note=text.split(maxsplit=1)[1] if len(text.split(maxsplit=1))>1 else ''
            return self.submit(pid,'Propose acceptance criteria for the existing requirements. '+note,kind='auto')

    def set_prerequisite(self,pid,ident,done=True):
        """Owner-reported setup. It changes readiness; it never passes a criterion by itself."""
        with self.lock:
            state=self.store.get(pid);root=Path(state['root'])
            spec=acceptance.load(root)
            known={p['id']:p for p in spec['prerequisites']}
            if ident not in known:
                raise ValueError('Unknown setup item for this project.')
            marked=dict(state.get('prerequisites_done') or {})
            if done:marked[ident]=time.time()
            else:marked.pop(ident,None)
            self.store.update(pid,prerequisites_done=marked)
            self.store.event(pid,'prerequisite',id=ident,done=bool(done))
            self.store.message(pid,'assistant',('Setup recorded: ' if done else 'Setup marked as not ready: ')+known[ident]['description'],'status')
            state=self.store.get(pid)
            if done and state['phase']=='implementation_verified' and not state['running'] and pid not in self.active:
                self.submit(pid,f'Setup recorded for {ident}. Verify the pending live acceptance.',kind='auto')
            return dict(ok=True,prerequisites_done=marked)

    def acceptance_status(self,pid):
        state=self.store.get(pid);root=Path(state['root'])
        spec=acceptance.load(root)
        results=acceptance.current(root,spec,acceptance.load_results(root),source_revision(root))
        done=acceptance.readiness(state)
        return dict(phase=state['phase'],derived=bool(spec.get('derived')),criteria=spec['criteria'],
            prerequisites=[dict(p,done=p['id'] in done) for p in spec['prerequisites']],
            results=results,outcome=acceptance.outcome(results) if results else 'not_run')

    def replan(self,pid,feedback):
        """Replace execution planning only, retaining approved intent and code."""
        with self.lock:
            state=self.store.get(pid)
            if pid in self.active or state['running']:
                raise ValueError('Stop the project and wait for its worker to finish before replanning. Existing work will be preserved.')
            root=Path(state['root'])
            for kind in ['requirements','prototype']:
                if not state['approvals'].get(kind) or state['approvals'][kind]!=artifact_revision(root,kind):
                    raise ValueError(f'The current {kind} needs approval before implementation replanning.')
            planning.require_parallel_capacity(self.settings())
            inbox=self.store.inbox(pid)
            if any(item['kind']!='plan' for item in inbox):
                raise ValueError('Resolve the pending question or review before replanning.')
            # Retain the prior graph and approvals without overwriting source or
            # any worker workspace. The new graph requires its own plan approval.
            self.store.checkpoint(pid,'plan-history:'+uuid.uuid4().hex,
                                  dict(tasks=state['tasks'],approvals=state['approvals'],workers=state.get('workers',[])))
            for item in inbox:self.store.close(pid,item['id'])
            approvals={kind:revision for kind,revision in state['approvals'].items() if kind!='plan'}
            self.store.update(pid,phase='plan',approvals=approvals,queue=[],paused=False,execution_mode='planned')
            self.store.message(pid,'user',feedback)
            return self.submit(pid,feedback+'\nReplan implementation only; retain approved requirements/design and existing code.',kind='auto')

    def _start(self,pid):
        if pid in self.active:
            return
        self.active[pid]=True;self.cancelled[pid]=threading.Event()
        self.pool.submit(self._drain,pid)

    def _drain(self,pid):
        try:
            while True:
                with self.lock:
                    state=self.store.get(pid)
                    if len([p for p in self.store.projects() if p.get('running')])>=self.settings().get('parallel_work',{}).get('max_workers',3):
                        limited=True
                    else:
                        limited=False
                    if state['paused'] or not state['queue'] or self.store.inbox(pid):
                        return
                    if self.cancelled[pid].is_set():
                        return
                    if limited:
                        item=None
                    else:
                        item=state['queue'][0]
                        self.store.update(pid,queue=state['queue'][1:],running=True,turn=item,native_helpers={})
                if item is None:
                    if self.cancelled[pid].wait(.2):
                        return
                    continue
                self.store.event(pid,'turn_start',turn=item['id'],text=item['text'],kind=item['kind'])
                from .progress import start as start_progress
                progress_stop,progress_thread=start_progress(self.store,pid)
                status='completed';error=None
                try:
                    self._advance(pid,item['text'])
                except InterruptedError as exc:
                    status='interrupted';self.store.message(pid,'assistant',str(exc),'status')
                except WorkWaiting as exc:
                    status='blocked'
                    self.store.update(pid,paused=True,attention=dict(reason=exc.reason,
                        message=str(exc),blockers=exc.blockers))
                    self.store.message(pid,'assistant',str(exc),'status')
                    self.store.event(pid,'work_waiting',reason=exc.reason,text=str(exc),blockers=exc.blockers)
                except Exception as exc:
                    status='error';error=f'{type(exc).__name__}: {exc}'
                    self.store.event(pid,'problem',text=error)
                    self.store.message(pid,'assistant',error,'status')
                    self.store.update(pid,paused=True)
                finally:
                    progress_stop.set();progress_thread.join(timeout=2)
                    self.store.update(pid,running=False,turn=None,last_completed_turn=item['id'])
                    self.store.event(pid,'turn_end',turn=item['id'],status=status,error=error)
        finally:
            with self.lock:
                self.active.pop(pid,None)
                # A submission can arrive after the drain's final queue check.
                state=self.store.get(pid)
                if state['queue'] and not state['paused'] and not self.store.inbox(pid):
                    self._start(pid)

    def stop(self,pid):
        with self.lock:
            self.cancelled.get(pid,threading.Event()).set()
            self.store.update(pid,paused=True,queue=[])
            for item in self.store.inbox(pid):
                if item.get('runtime'):
                    self.answers[item['id']]='deny';self.store.close(pid,item['id'])
            self.store.event(pid,'stop_requested',cleared_queue=True)

    def runtime_ask(self,pid,kind,question,choices,worker=None,done=None,invocation_id=None):
        if worker:question=f'[{worker["task_id"]} · {worker["role"]}] {question}'
        item=self.store.ask(pid,kind,question,choices,runtime=True,
            invocation_id=invocation_id,
            **({'worker_id':worker['id'],'task_id':worker['task_id']} if worker else {}),
            **({'command':question} if kind=='approval' else {}))
        try:
            while not self.cancelled[pid].wait(.15):
                if done and done.is_set():
                    raise InterruptedError('The task that asked this question has ended.')
                with self.lock:
                    if item['id'] in self.answers:
                        return self.answers.pop(item['id'])
            raise InterruptedError('Stopped while waiting for an answer.')
        finally:
            if any(i['id']==item['id'] for i in self.store.inbox(pid)):
                self.store.close(pid,item['id'])
            self.answers.pop(item['id'],None)

    def answer(self,pid,iid,answer):
        with self.lock:
            item=next((i for i in self.store.inbox(pid) if i['id']==iid),None)
            if item is None:
                raise ValueError('This question has already been answered.')
            if item['kind']=='question':self.store.record_question(pid,item['question'])
            choice=answer.get('choice','') if isinstance(answer,dict) else str(answer)
            if item.get('runtime'):
                if item['kind']=='approval' and choice not in item['choices']:
                    raise ValueError('Choose one of the offered approval options.')
                self.answers[iid]=choice;self.store.close(pid,iid)
                self.store.message(pid,'user',choice,'answer')
                return dict(ok=True)
            state=self.store.get(pid);kind=item['kind']
            if kind in ARTIFACTS:
                root=Path(state['root']);revision=artifact_revision(root,kind)
                if revision!=item['revision'] or (isinstance(answer,dict) and answer.get('revision',revision)!=revision):
                    raise ValueError('The reviewed files changed. Reopen the current review before approving.')
                if choice not in CHOICES[kind]:
                    raise ValueError('Use the approval or request-changes button.')
                if kind=='plan' and choice==CHOICES[kind][0] and state.get('plan_policy')!=planning.POLICY:
                    raise ValueError('This plan uses the previous execution contract. Use /replan to regenerate it before approval.')
                self.store.close(pid,iid)
                if choice==CHOICES[kind][0]:
                    approvals={**state['approvals'],kind:revision}
                    phase={'prototype':'requirements_review','requirements':'plan','plan':'build','blocks':'blocks_build'}[kind]
                    if kind=='requirements' and state.get('execution_mode')=='direct':phase='build'
                    elif kind=='requirements' and state.get('execution_mode')=='blocks':
                        valid=approvals.get('blocks') and approvals['blocks']==artifact_revision(root,'blocks')
                        if valid:
                            # A still-approved plan must cover the current criteria. New or removed checks are fitted to the
                            # blocks that own that requirement instead of replanning; built blocks stay built.
                            from . import blocks as block_plan
                            plan_=block_plan.load(root);spec=acceptance.load(root)
                            ids={c['id'] for c in spec['criteria']}
                            owned=set(plan_['body']['criteria']).union(*(set(b['criteria']) for b in plan_['blocks']))
                            if not (owned<=ids and all(c['id'] in owned for c in acceptance.release_one(spec))):
                                from .blockbuild import adopt_new_criteria
                                fitted=adopt_new_criteria(self,pid,root)
                                valid=bool(fitted)
                                if fitted:approvals['blocks']=fitted
                        phase='blocks_build' if valid else 'blocks_plan'
                    elif kind=='requirements' and approvals.get('plan') and approvals['plan']==artifact_revision(root,'plan'):phase='build'
                    self.store.update(pid,approvals=approvals,phase=phase)
                    self.store.message(pid,'assistant',f'{kind.capitalize()} approved.','status')
                    if kind=='requirements':
                        self._prerequisite_notice(pid,root)
                    self.submit(pid,f'Continue from approved {kind}.',kind='auto')
                else:
                    feedback=answer.get('feedback','Please ask what needs changing.') if isinstance(answer,dict) else 'Ask what needs changing.'
                    phase={'prototype':'requirements','requirements':'requirements','plan':'plan','blocks':'blocks_plan'}[kind]
                    if kind=='prototype':
                        # Design changes are recorded in the requirements first; the prototype is then regenerated.
                        feedback=('Prototype feedback from the owner: '+feedback+'\nRecord this change in requirements.md '
                                  '(keep requirement IDs stable) and return the complete updated requirements.')
                    approvals=dict(state['approvals'])
                    if kind=='requirements' and state.get('execution_mode')=='blocks' and approvals.get('blocks'):
                        # Building has started: edit the requirements in place and keep the approved design and block plan.
                        approvals.pop('requirements',None)
                        self.store.update(pid,phase='requirements_update',approvals=approvals)
                        self.store.message(pid,'user',feedback)
                        self.submit(pid,feedback,kind='auto');return dict(ok=True)
                    for k in list(approvals):
                        if kind=='requirements' or k==kind or k in ('plan','blocks'):
                            approvals.pop(k,None)
                    self.store.update(pid,phase=phase,approvals=approvals)
                    self.store.message(pid,'user',feedback)
                    self.submit(pid,feedback,kind='auto')
            elif item.get('blocks_scope'):
                from .blockbuild import answer as blocks_answer
                blocks_answer(self,pid,item,choice)
            elif item.get('scope'):
                from .direct import KEEP_ALL, PROVIDE_FIRST
                self.store.close(pid,iid);self.store.message(pid,'user',choice,'answer')
                if choice==KEEP_ALL:
                    self.store.update(pid,phase=coding_phase(state),stalled_attempts=0,last_wait_signature=None)
                    self.submit(pid,'The owner chose to keep all remaining parts in this release. Continue building them.',kind='auto')
                elif choice==PROVIDE_FIRST:
                    self.store.update(pid,paused=True)
                    self.store.message(pid,'assistant','OK. Tick each setup item in the Acceptance panel when it is ready, then send "continue". '
                                       'Nothing will run until then.','status')
                else:
                    self.store.update(pid,phase='rescope',rescope=dict(choice=choice,parts=item.get('parts',[])))
                    self.submit(pid,choice,kind='auto')
            else:
                self.store.close(pid,iid);self.store.message(pid,'user',choice,'answer')
                self.submit(pid,choice,kind='auto')
            return dict(ok=True)

    def _prerequisite_notice(self,pid,root):
        spec=acceptance.load(root)
        if spec.get('derived') or not spec['prerequisites']:
            return
        live=[c for c in acceptance.release_one(spec) if c['live']]
        local=len(acceptance.release_one(spec))-len(live)
        lines=[f'Coding can proceed on {local} locally testable criteria. You will be needed for:']
        for p in spec['prerequisites']:
            uses=[c['id'] for c in live if p['id'] in c['prerequisites']]
            lines.append(f"- {p['description']} ({p['kind']}, needed at {p['needed_at']}; affects {', '.join(uses) or 'no release-1 criterion'})")
        lines.append('Mark each item done in Setup when it is ready. Live checks wait for it; they are never counted as passed without evidence.')
        self.store.message(pid,'assistant','\n'.join(lines),'status')

    def review(self,pid,kind):
        root=Path(self.store.get(pid)['root']);revision=artifact_revision(root,kind)
        if not revision:
            raise ValueError(f'The {kind} artifact is missing.')
        question=f'Review the {kind} before continuing.'
        if kind!='prototype':
            question+='\n\n'+safe_path(root,ARTIFACTS[kind]).read_text()
        if kind=='requirements':
            table=acceptance.summary_markdown(acceptance.load(root))
            if table:question+='\n\n'+table
        self.store.ask(pid,kind,question,CHOICES[kind],revision=revision)

    def authorized_inputs(self,pid):
        """Planning needs approved requirements and prototype (not yet a plan)."""
        state=self.store.get(pid);root=Path(state['root'])
        for kind in ['requirements','prototype']:
            if not state['approvals'].get(kind) or state['approvals'][kind]!=artifact_revision(root,kind):
                raise PermissionError(f'The current {kind} needs approval before planning.')

    def authorized(self,pid):
        state=self.store.get(pid);root=Path(state['root'])
        mode=state.get('execution_mode')
        kinds=(['requirements','prototype'] if mode=='direct' else ['requirements','prototype','blocks'] if mode=='blocks'
               else ['requirements','prototype','plan'])
        for kind in kinds:
            if state['approvals'].get(kind)!=artifact_revision(root,kind) or not state['approvals'].get(kind):
                raise PermissionError(f'The current {kind} needs approval before implementation can continue.')

    def scope_remaining_tasks(self,pid):
        """Assess legacy execution metadata without rewriting an approved plan."""
        state=self.store.get(pid);pending=[t for t in state['tasks'] if t['status']!='done']
        if not pending or not any(not t.get('files') for t in pending):
            return
        signature=hashlib.sha256(json.dumps(dict(plan=state['approvals'].get('plan'),revision=state['revision'],
            tasks=[{k:t.get(k) for k in ['id','goal','depends_on']} for t in state['tasks']]),sort_keys=True).encode()).hexdigest()
        if state.get('scope_assessed')==signature:return
        self.authorized(pid)
        result=self.invoke(pid,'task-planner',
            'Assess safe execution ownership for these existing unfinished tasks: '+json.dumps(pending)+'. '
            'Inspect plan.md, shared interfaces and current source. Do not edit files, rewrite task goals, remove dependencies or add scope. '
            'Return {"summary":"brief execution assessment","task_scopes":[{"id":"existing task ID","files":["src/feature/"],"additional_depends_on":[]}]}. '
            'Assign disjoint plain relative files/folders only where independence is clear; folders end in /. '
            'Add dependencies for shared contracts where necessary. Leave files empty for uncertain tasks; these remain serial. '
            'Do not invent tasks or change already assigned ownership.',readonly=True)
        self.authorized(pid)
        updates=result.get('task_scopes',[])
        if not isinstance(updates,list):raise ValueError('Execution ownership assessment must return a list of task scopes.')
        tasks=self.store.get(pid)['tasks'];by={t['id']:t for t in tasks if t['status']!='done'};seen=set()
        for update in updates:
            ident=update.get('id') if isinstance(update,dict) else None
            if ident not in by or ident in seen:raise ValueError('Execution assessment referred to an unknown or duplicated task.')
            seen.add(ident);task=by[ident]
            scopes=ownership(update.get('files',[]));deps=update.get('additional_depends_on',[])
            if not isinstance(deps,list) or any(not isinstance(dep,str) for dep in deps):
                raise ValueError('Execution dependencies must be task IDs.')
            if task.get('files') and scopes!=task['files']:
                raise ValueError('Execution assessment cannot change already assigned file ownership.')
            task['files']=scopes
            task['depends_on']=list(dict.fromkeys([*task['depends_on'],*deps]))
        parse_tasks(tasks)  # Validate the resulting dependency graph before saving anything.
        # The stable assessment key uses the final (possibly stricter) dependency graph.
        signature=hashlib.sha256(json.dumps(dict(plan=state['approvals'].get('plan'),revision=state['revision'],
            tasks=[{k:t.get(k) for k in ['id','goal','depends_on']} for t in tasks]),sort_keys=True).encode()).hexdigest()
        self.store.update(pid,tasks=tasks,scope_assessed=signature)

    def invoke(self,pid,role,goal,readonly=False,workspace=None,worker=None,session_scope=None,planning_context=None):
        if self.cancelled[pid].is_set():
            raise InterruptedError('Stopped before starting the next model invocation. Existing work is saved.')
        invocation_id=uuid.uuid4().hex;done=threading.Event()
        key,conn,selection=self.connection(role)
        state=self.store.get(pid)
        # A changed model/skill gets a new session; existing prefixes stay unchanged.
        mode=state.get('execution_mode','planned')
        instructions=context.instructions(role,'direct' if mode=='blocks' and not worker else mode)
        if self.settings().get('about_me'):
            instructions+='\nOwner preferences (apply only where compatible with project requirements):\n'+self.settings()['about_me']
        instruction_hash=hashlib.sha256(instructions.encode()).hexdigest()
        fingerprint=hashlib.sha256((key+json.dumps(conn,sort_keys=True)+selection.get('model','')+selection.get('effort','')+instructions).encode()).hexdigest()[:16]
        session_key=role+':'+fingerprint+(':'+worker['id'] if worker else ':'+session_scope if session_scope else '')
        self.store.event(pid,'invocation',run_id=invocation_id,role=role,provider=key,
            model=selection.get('model') or 'provider-default',effort=selection.get('effort') or 'provider-default',
            instructions_sha256=instruction_hash,worker_id=worker['id'] if worker else None,
            source_access='verification' if worker and worker.get('kind')=='verification' else 'read-only' if readonly else 'workspace-write')
        self.store.update(pid,engine=key,requirements_started=True)
        usage_baseline=state.get('session_usage',{}).get(session_key,{})
        def save_session(sid):
            with self.lock:
                current=self.store.get(pid);self.store.update(pid,sessions={**current['sessions'],session_key:sid})
        def save_usage(usage):
            if 'total' in usage:
                total=usage['total']
                with self.lock:
                    current=self.store.get(pid)
                    self.store.update(pid,session_usage={**current.get('session_usage',{}),session_key:total})
                usage={name:max(0,total.get(native,0)-usage_baseline.get(native,0)) for name,native in
                       [('input_tokens','inputTokens'),('cached_input_tokens','cachedInputTokens'),('output_tokens','outputTokens')]}
            elif conn['engine']=='claude-cli':
                cached=usage.get('cache_read_input_tokens',0)
                usage=dict(input_tokens=usage.get('input_tokens',0)+cached+usage.get('cache_creation_input_tokens',0),
                           cached_input_tokens=cached,output_tokens=usage.get('output_tokens',0))
            self.store.event(pid,'usage',provider=key,role=role,run_id=invocation_id,worker_id=worker['id'] if worker else None,usage=usage)
        helper_id=worker['id'] if worker else role
        display_goal=worker['goal'] if worker else role
        def emit_event(type_,**fields):
            if type_=='helper' and fields.get('native'):
                with self.lock:
                    helpers=dict(self.store.get(pid).get('native_helpers',{}))
                    helper=fields.get('subagent_id')
                    if fields.get('event')=='start':
                        helpers[helper]=dict(id=helper,goal=fields.get('goal') or 'Codex agent',
                                            **{k:fields[k] for k in ('agent_path','model') if fields.get(k)},
                                            started=time.time(),run_id=invocation_id)
                    else:helpers.pop(helper,None)
                    self.store.update(pid,native_helpers=helpers)
            self.store.event(pid,type_,**fields)
        self.store.event(pid,'helper',event='start',subagent_id=helper_id,goal=display_goal,role=role,run_id=invocation_id)
        try:
            run=Run(root=Path(workspace or state['root']),instructions=instructions,
                managed_worker=bool(worker) or (state['phase']=='build' and state.get('execution_mode') not in {'direct','blocks'}),
                native_delegation=not worker and ((state['phase']=='build' and state.get('execution_mode')=='direct')
                                                  or (state['phase']=='body' and state.get('execution_mode')=='blocks')),
                prompt=context.briefing(self.store,pid,role,goal,workspace=workspace,worker=worker,planning_context=planning_context),model='' if selection.get('model')=='default' else selection.get('model',''),effort=selection.get('effort',''),
                readonly=readonly,session=state['sessions'].get(session_key),cancel=self.cancelled[pid],
                emit=emit_event,
                ask=lambda k,q,c:self.runtime_ask(pid,k,q,c,worker=worker,done=done,invocation_id=invocation_id),recall=lambda q:self.store.search(pid,q),
                save_session=save_session,save_usage=save_usage)
            data=self.execute(conn,run)
            if self.cancelled[pid].is_set():
                raise InterruptedError('Stopped. Files are saved; send a message to continue.')
            if worker:
                self.store.checkpoint(pid,role+':'+worker['id'],dict(goal=goal,outcome=data,workspace=str(workspace),next_action='Integrate and verify.'))
            else:context.checkpoint(self.store,pid,role,goal,data,self.store.get(pid)['phase'])
            self.store.event(pid,'helper',event='complete',subagent_id=helper_id,goal=display_goal,status='completed')
            if data.get('summary'):
                self.store.message(pid,'assistant',data['summary'])
                self.store.event(pid,'interim',text=data['summary'])
            return data
        except BaseException:
            if worker:
                self.store.checkpoint(pid,role+':'+worker['id'],dict(goal=goal,outcome='Interrupted or blocked; inspect existing files before retrying.',workspace=str(workspace),next_action='Resume retained worker.'))
            else:context.checkpoint(self.store,pid,role,goal,'Interrupted or blocked; inspect existing files before retrying.',self.store.get(pid)['phase'])
            self.store.event(pid,'helper',event='complete',subagent_id=helper_id,goal=display_goal,status='error')
            raise
        finally:
            done.set()
            with self.lock:
                helpers=self.store.get(pid).get('native_helpers',{})
                if any(h.get('run_id')==invocation_id for h in helpers.values()):
                    self.store.update(pid,native_helpers={k:h for k,h in helpers.items() if h.get('run_id')!=invocation_id})
                for item in self.store.inbox(pid):
                    if item.get('runtime') and item.get('invocation_id')==invocation_id:
                        self.answers.pop(item['id'],None);self.store.close(pid,item['id'])

    def _write(self,pid,name,text):
        path=safe_path(Path(self.store.get(pid)['root']),name);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text);self.store.remember(pid,name,text)

    def create_plan(self,pid,text):
        limit=planning.require_parallel_capacity(self.settings())
        state=self.store.get(pid);root=Path(state['root'])
        # Bind retained proposals to the actual inputs/source. A saved review is
        # feedback for a new review, never approval or permission to execute.
        signature=hashlib.sha256(json.dumps(dict(policy=planning.POLICY,
            approvals=state['approvals'],source=source_revision(root)),sort_keys=True).encode()).hexdigest()
        draft=state.get('plan_draft') or {}
        if draft.get('signature')!=signature:draft={}
        history=list(draft.get('reviews',[]));candidate=draft.get('candidate');seen=set()
        goal=planning.planning_goal(text,limit)
        if candidate:
            goal+='\nContinue planning.draft.candidate, preserving its useful corrections. Resolve the accumulated review findings; do not restart planning from the old execution ledger.'
        for attempt in range(planning.MAX_PLAN_ATTEMPTS):
            plan_context=dict(stage='proposal')
            if candidate:plan_context['draft']=dict(candidate=candidate,reviews=history)
            result=self.invoke(pid,'task-planner',goal,readonly=True,session_scope='planner-'+planning.SESSION_VERSION,
                               planning_context=plan_context)
            candidate=result;review=None
            self.store.update(pid,plan_draft=dict(signature=signature,candidate=candidate,reviews=history))
            try:
                tasks=parse_tasks(result.get('tasks'))
                if not isinstance(result.get('plan'),str) or not result['plan'].strip():
                    raise ValueError('The readable implementation plan is missing.')
                waves=planning.execution_waves(tasks,limit)
                contract=planning.validate_contract(result,tasks,Path(self.store.get(pid)['root']))
                review=self.invoke(pid,'sw-architect',
                    'Independently review this candidate implementation plan against the approved requirements, current source and host capabilities. '
                    'Do not edit files or grant approval. Check complete user journeys from input through real operations, review/resume and observed results; '
                    'check missing owners, shared interfaces, runtime/bootstrap feasibility, real dependency consumers, independent QA and live blockers. '
                    'Do not pass adapter lists or requirement-ID mentions as end-to-end implementation. '
                    'Audit every approved journey and return all concrete gaps together, including provider-operation-result continuation, '
                    'review/restart/resume, real file transport, and any required device/audio routing. Verify prior findings against this candidate. '
                    'Distinguish missing implementation assignments from execution-time acceptance evidence: this is planning, not release QA. '
                    'Use planning.recovery to check retained worker blockers against the candidate, not as competing task assignments. '
                    'Check every acceptance requires_tasks list against actual routes/factories/identity/device prerequisites. '
                    'Reject semantic dependency cycles: an upstream feature cannot need downstream integration to pass. '
                    'Keep owner-dependent live acceptance as an explicit release gate while allowing independently testable development; '
                    'a fixture or recorded blocker is never a live pass. '
                    'A concrete assigned feasibility check may gate dependent implementation and release; do not require planned code to exist before plan review. '
                    'The sole candidate is supplied in planning.candidate; it has not been adopted or approved yet. '
                    'Return {"verdict":"pass|fail|blocked","summary":"concrete rationale","findings":["actionable gap"]}.',
                    readonly=True,session_scope='plan-review-'+planning.SESSION_VERSION+'-'+uuid.uuid4().hex,
                    planning_context=dict(stage='review',candidate=dict(plan=result['plan'],tasks=tasks,**contract),prior_reviews=history))
                if review.get('verdict')!='pass' or review.get('findings')!=[] or not isinstance(review.get('summary'),str) or not review['summary'].strip():
                    raise ValueError('Independent plan review requires correction: '+json.dumps(review))
                contract['review']=dict(verdict='pass',summary=review['summary'],findings=[])
                return planning.with_schedule(result['plan'],waves,tasks,limit,contract),tasks,contract
            except ValueError as exc:
                feedback=review if isinstance(review,dict) else dict(verdict='fail',summary=str(exc),findings=[str(exc)])
                history.append(feedback)
                self.store.update(pid,plan_draft=dict(signature=signature,candidate=candidate,reviews=history))
                marker=json.dumps(dict(candidate={k:candidate.get(k) for k in ['plan','tasks','runtime','journeys']},
                    verdict=feedback.get('verdict'),findings=feedback.get('findings')),sort_keys=True)
                no_progress=marker in seen;seen.add(marker)
                if no_progress or attempt==planning.MAX_PLAN_ATTEMPTS-1:
                    self.store.event(pid,'plan_validation',status='paused',text=str(exc),attempt=attempt+1,retained=True)
                    raise ValueError('The planner could not produce a safe parallel plan. The draft and review findings are saved for correction. '+str(exc)) from exc
                self.store.event(pid,'plan_validation',status='retry',text=str(exc),attempt=attempt+1)
                goal=planning.planning_goal(text,limit)+'\nCorrect the rejected plan: '+str(exc)+(
                    '\nContinue planning.draft.candidate; address ALL accumulated findings in planning.draft.reviews together, '
                    'preserve resolved corrections and self-audit all journeys before returning the complete replacement. '
                    'Do not merely acknowledge findings or defer controller-supported assignments.')

    def _advance(self,pid,text):
        for step in range(100):
            if self.cancelled[pid].is_set():
                raise InterruptedError('Stopped. Your files and checkpoints are saved.')
            state=self.store.get(pid);phase=state['phase']
            if phase=='requirements':
                result=self.invoke(pid,'req-engineer',f'User input: {text}\nInterview for requirements; ask only unanswered questions, one at a time. '
                    'Respect skip/decide/defaults. For existing apps distinguish explanation or in-scope fixes from material scope changes. '
                    'Return {"summary":"...","question":"one question","choices":["..."]} while gaps remain; '
                    'when ready return {"summary":"...","requirements":"complete Markdown with stable requirement IDs, journeys, assumptions and acceptance criteria; tag each FR/NFR Release: 1 or later",'
                    '"acceptance_criteria":[{"id":"AC-FR-001-1","requirement":"FR-001","description":"observable pass condition","release":"1|later","live":false,"prerequisites":[]}],'
                    '"prerequisites":[{"id":"P-google-login","kind":"account|driver|permission|device|time|service|other","description":"what the owner must provide","needed_at":"build|verification"}],'
                    '"suggested_team":["specialist role IDs from available_roles"]}. '
                    'Every FR/NFR needs at least one criterion. Set live=true only when passing needs real accounts, devices, permissions, other people or elapsed time, '
                    'and name the prerequisite it needs; its code must still be buildable and testable locally. '
                    'If release 1 is large or depends on several external integrations, offer the owner a smaller first release as a question before finishing; '
                    'never move a requirement to later without the owner choosing it. '
                    'Recommend only specialists useful for this project. '
                    'Do not implement the app. Do not ask for approvals yourself; the controller handles those.',readonly=True)
                if result.get('question'):
                    self.store.ask(pid,'question',result['question'],result.get('choices',[]));return
                if not isinstance(result.get('requirements'),str) or not result['requirements'].strip():
                    raise ValueError('Requirements are incomplete. Continue the interview.')
                if not re.search(r'\bFR-\d+\b',result['requirements']):
                    raise ValueError('Requirements need stable FR IDs and acceptance criteria before prototype work.')
                root=Path(state['root'])
                if result.get('acceptance_criteria'):
                    spec=acceptance.normalize(result['acceptance_criteria'],result.get('prerequisites',[]),result['requirements'])
                    self._write(pid,'requirements.md',result['requirements'])
                    acceptance.write(root,spec)
                else:
                    self._write(pid,'requirements.md',result['requirements'])
                    # Never keep criteria approved for a different requirements text.
                    stale=safe_path(root,acceptance.SPEC)
                    if stale.is_file():stale.unlink()
                if state.get('execution_mode')=='direct':
                    valid_roles={entry[0] for entry in context.CATALOG['AGENTS']}
                    suggested=result.get('suggested_team',[])
                    if not isinstance(suggested,list):raise ValueError('Suggested team must be a list of role IDs.')
                    suggested=[r for r in suggested if isinstance(r,str) and r in valid_roles and r!='task-planner']
                    team=list(dict.fromkeys([*state['team'],*suggested]))
                    self.store.update(pid,team=team);state=self.store.get(pid)
                self.store.update(pid,phase='prototype');text='Build the prototype from this draft.'
            elif phase=='prototype':
                result=self.invoke(pid,'ui-designer',f'{text}\nCreate or revise prototypes/index.html and its clickable screens from requirements.md. '
                    'Use realistic sample data and include the main journeys plus empty/error states. Keep prototype assets inside prototypes/. '
                    'Preserve the existing app outside prototypes/. Do not build its backend yet. Return {"summary":"...","status":"completed"}.')
                if result.get('status')!='completed':
                    raise ValueError('Prototype work is not complete.')
                self.store.update(pid,phase='prototype_review');self.review(pid,'prototype');return
            elif phase=='prototype_review':
                self.review(pid,'prototype');return
            elif phase=='rescope':
                root=Path(state['root']);old_requirements=safe_path(root,'requirements.md').read_text()
                request=state.get('rescope') or {}
                result=self.invoke(pid,'req-engineer',f'Owner decision: {text}\nParts that could not be finished: '+json.dumps(request.get('parts',[]))+
                    '\nApply only the owner\'s decision to release scope. Keep every requirement and criterion; change only Release tags '
                    '(in requirements.md and the acceptance criteria) for the parts the owner chose to leave for later. '
                    'If the owner said to build some, keep those in release 1 and move the rest. '
                    'If the owner instead gave instructions for how to build these parts (not a release change), change nothing and return '
                    '{"summary":"...","build_guidance":"the owner\'s instructions, restated faithfully and completely for the builder"}. '
                    'If the decision is unclear, ask one question. '
                    'Return {"summary":"...","question":"only if unclear","choices":["..."]} or {"summary":"plain list of what moved to later and what stays",'
                    '"requirements":"complete updated Markdown","acceptance_criteria":[...all criteria...],"prerequisites":[...]}.',readonly=True)
                if result.get('question'):
                    self.store.ask(pid,'question',result['question'],result.get('choices',[]));return
                if isinstance(result.get('build_guidance'),str) and result['build_guidance'].strip() and not result.get('requirements'):
                    # Keep everything in scope; the builder continues with the owner's own words plus the restatement.
                    guidance=f'Owner instructions: {text}\nRestated: {result["build_guidance"].strip()}'
                    self.store.update(pid,phase=coding_phase(state),rescope=None,stalled_attempts=0,last_wait_signature=None,
                                      owner_guidance=[*state.get('owner_guidance',[]),guidance][-10:])
                    self.store.message(pid,'assistant','Keeping every part in this release and passing your instructions to the builder.','status')
                    text=('The owner kept these parts in release 1 and gave instructions for building them. Follow them:\n'+guidance)
                    continue
                if not isinstance(result.get('requirements'),str) or not result.get('acceptance_criteria'):
                    raise ValueError('The scope change is incomplete. Send your decision again.')
                if set(acceptance.requirement_ids(result['requirements']))!=set(acceptance.requirement_ids(old_requirements)):
                    raise ValueError('A scope change may move requirements to later but cannot add or remove them.')
                spec=acceptance.normalize(result['acceptance_criteria'],result.get('prerequisites',[]),result['requirements'])
                old_spec=acceptance.load(root)
                if old_spec.get('deferred_blocks'):spec['deferred_blocks']=old_spec['deferred_blocks']
                before=artifact_revision(root,'requirements')
                self._write(pid,'requirements.md',result['requirements']);acceptance.write(root,spec)
                if artifact_revision(root,'requirements')==before:
                    self.store.update(pid,phase='blocks_build' if state.get('execution_mode')=='blocks' else 'build',rescope=None)
                    text='Continue building; the release scope did not change.';continue
                approvals={k:v for k,v in state['approvals'].items() if k!='requirements'}
                self.store.update(pid,phase='requirements_review',approvals=approvals,rescope=None)
                self.review(pid,'requirements');return
            elif phase=='requirements_update':
                root=Path(state['root']);old_requirements=safe_path(root,'requirements.md').read_text()
                old_spec=acceptance.load(root)
                result=self.invoke(pid,'req-engineer',f'Owner change request: {text}\nThe prototype and block plan are approved and building has started. '
                    'Apply only this change to requirements.md and the acceptance criteria. You may reword requirements and add or edit '
                    'acceptance criteria and owner prerequisites. Keep every requirement ID; do not add or remove requirements. '
                    'Keep every existing criterion ID and Release tag unless the owner asked to change it; give new criteria new IDs. '
                    'If the change needs a new requirement or a design change, ask one question explaining that. '
                    'Return {"summary":"...","question":"only if needed","choices":["..."]} or {"summary":"plain list of what changed",'
                    '"requirements":"complete updated Markdown","acceptance_criteria":[...all criteria...],"prerequisites":[...]}.',readonly=True)
                if result.get('question'):
                    self.store.ask(pid,'question',result['question'],result.get('choices',[]));return
                if not isinstance(result.get('requirements'),str) or not result.get('acceptance_criteria'):
                    raise ValueError('The requirements update is incomplete. Send your change request again.')
                problem=''
                if set(acceptance.requirement_ids(result['requirements']))!=set(acceptance.requirement_ids(old_requirements)):
                    problem=('That change would add or remove requirements, which needs a new design and block plan, so nothing was changed. '
                             'Approve the current requirements or request a smaller change.')
                else:
                    spec=acceptance.normalize(result['acceptance_criteria'],result.get('prerequisites',[]),result['requirements'])
                    dropped=sorted({c['id'] for c in old_spec['criteria']}-{c['id'] for c in spec['criteria']})
                    if dropped:
                        problem=('The update removed checks ('+', '.join(dropped)+'), so nothing was changed. '
                                 'Request the change again and say which checks to keep.')
                if problem:
                    self.store.message(pid,'assistant',problem,'status')
                    self.store.update(pid,phase='requirements_review');self.review(pid,'requirements');return
                if old_spec.get('deferred_blocks'):spec['deferred_blocks']=old_spec['deferred_blocks']
                self._write(pid,'requirements.md',result['requirements']);acceptance.write(root,spec)
                if result.get('summary'):self.store.message(pid,'assistant',str(result['summary'])[:1200],'status')
                self.store.update(pid,phase='requirements_review')
                self.review(pid,'requirements');return
            elif phase=='criteria':
                root=Path(state['root']);requirements=safe_path(root,'requirements.md').read_text()
                result=self.invoke(pid,'req-engineer',f'{text}\nThe requirements in requirements.md are already written. Do not change them or add scope. '
                    'Propose acceptance criteria and owner prerequisites for every FR/NFR. '
                    'Return {"summary":"...","acceptance_criteria":[{"id":"AC-FR-001-1","requirement":"FR-001","description":"observable pass condition",'
                    '"release":"1","live":false,"prerequisites":[]}],"prerequisites":[{"id":"P-name","kind":"account|driver|permission|device|time|service|other",'
                    '"description":"what the owner must provide","needed_at":"build|verification"}]}. '
                    'Keep every requirement in release 1 unless requirements.md already says otherwise. Set live=true only for checks that need real accounts, '
                    'devices, permissions, other people or elapsed time, and name the prerequisite. The owner approves these criteria.',readonly=True)
                spec=acceptance.normalize(result.get('acceptance_criteria'),result.get('prerequisites',[]),requirements)
                acceptance.write(root,spec)
                approvals={k:v for k,v in state['approvals'].items() if k!='requirements'}
                self.store.update(pid,phase='requirements_review',approvals=approvals)
                self.review(pid,'requirements');return
            elif phase=='requirements_review':
                self.review(pid,'requirements');return
            elif phase=='plan':
                plan,tasks,contract=self.create_plan(pid,text)
                self._write(pid,'plan.md',plan)
                self.store.update(pid,tasks=tasks,phase='plan_review',plan_policy=planning.POLICY,plan_contract=contract,plan_draft=None)
                self.review(pid,'plan');return
            elif phase=='plan_review':
                self.review(pid,'plan');return
            elif phase=='blocks_plan':
                self.authorized_inputs(pid)
                from .blockbuild import plan as plan_blocks
                plan_blocks(self,pid,text);return
            elif phase=='blocks_review':
                self.review(pid,'blocks');return
            elif phase=='blocks_build':
                from .blockbuild import build as build_blocks
                build_blocks(self,pid,text);text='All release-1 blocks are built. Build the app body.';continue
            elif phase=='body':
                self.authorized(pid)
                from .direct import build
                from .blockbuild import body_goal
                plan_=__import__('appling.blocks',fromlist=['load']).load(Path(state['root']))
                build(self,pid,text,goal_prefix=body_goal(plan_,acceptance.load(Path(state['root'])),state.get('block_status')),
                      session_scope='body-v1',protect=['blocks/'])
                continue
            elif phase=='build':
                self.authorized(pid)
                if state.get('execution_mode')=='direct':
                    from .direct import build
                    build(self,pid,text)
                    continue
                if state.get('plan_policy') and state['plan_policy']!=planning.POLICY:
                    raise ValueError('Replan with the current execution contract before starting development.')
                if state.get('plan_policy')==planning.POLICY:
                    planning.require_parallel_capacity(self.settings())
                self.scope_remaining_tasks(pid)
                from .swarm import build_ready
                if not build_ready(self,pid,feedback=text):
                    self.store.update(pid,phase='qa');continue
            elif phase in {'qa','security','code-review','accessibility'}:
                self.authorized(pid)
                role={'qa':'qa-engineer','security':'security-auditor','code-review':'code-reviewer','accessibility':'a11y-auditor'}[phase]
                before=source_revision(Path(state['root']))
                from .swarm import verify_project
                result=verify_project(self,pid,role,
                    'Independently verify the integrated application against approved requirements. Do not edit application source. '
                    'For QA, run real builds/tests and interact with every approved core UI journey using Playwright or available browser tools. '
                    'For requested phone/computer targets, use their actual emulator/device/native automation as well; report missing access as blocked. '
                    'Save raw logs/screenshots under .sdlc/evidence/. A browser UI without browser evidence is BLOCKED. '
                    'For security, check the actual auth/data/dependencies relevant to this app, without destructive external testing. '
                    'Return {"summary":"...","verdict":"pass|fail|blocked","browser_tested":true,"platforms_tested":["web"],'
                    '"checks":[{"command":"actual command or browser actions","exit_code":0,"evidence":".sdlc/evidence/path","requirements":["FR-001"]}],'
                    '"findings":[{"description":"...","severity":"high"}]}.'+(self._criteria_brief(state) if phase=='qa' else ''))
                self.authorized(pid)
                after=source_revision(Path(state['root']))
                if before!=after:
                    raise RuntimeError('Verification changed application source. Its evidence is invalid; inspect the changes and rerun verification.')
                result['source_revision']=after
                root=Path(state['root'])
                evidence_folder=result.pop('_evidence_folder',None)
                self._write(pid,f'.sdlc/{phase}-report.json',json.dumps(result,indent=2))
                if phase=='qa':
                    valid=self.valid_evidence(pid,result,require_browser=state['kind'] in {'app','website'},require_coverage=False)
                    if any(p!='web' and p not in result.get('platforms_tested',[]) for p in state['platforms']):
                        valid=False
                    spec=acceptance.load(root)
                    results=acceptance.evaluate(root,spec,state,result,after,role=role,evidence_prefix=evidence_folder)
                    acceptance.save_results(root,results)
                    status=acceptance.outcome(results)
                    self.store.update(pid,acceptance_outcome=status,readiness_verified=acceptance.readiness(state))
                    self.store.event(pid,'acceptance',outcome=status,counts={k:sum(r['status']==k for r in results.values()) for k in acceptance.STATUSES})
                    failed=[i for i,r in results.items() if r['status']=='failed']
                    if failed or result.get('verdict')=='fail':
                        cycles=state.get('repair_cycles',0)+1
                        if cycles>3:
                            raise RuntimeError('Verification still has unresolved findings after 3 repair cycles. Evidence and findings are saved; review them before continuing.')
                        repair=dict(findings=result.get('findings',[]),failed_criteria={i:results[i] for i in failed})
                        if state.get('execution_mode') in {'direct','blocks'}:
                            self.store.update(pid,phase=coding_phase(state),repair_cycles=cycles)
                            text='Fix these independent review findings without adding scope: '+json.dumps(repair)
                            continue
                        tasks=state['tasks']+[dict(id=f'repair-{state["revision"]}-{cycles}',goal=json.dumps(repair),depends_on=[],role='sw-developer',status='pending')]
                        self.store.update(pid,tasks=tasks,phase='build',repair_cycles=cycles);continue
                    missing=[i for i,r in results.items() if r['status']=='not_run']
                    # The controller judges release-1 criteria itself; a verifier's overall "blocked"
                    # caused only by later-release or owner-pending items does not block.
                    if missing or not valid or result.get('verdict') not in {'pass','blocked'}:
                        detail=('Not verified: '+', '.join(missing[:20])) if missing else 'Evidence is incomplete or the verdict is blocked.'
                        raise RuntimeError('Verification is blocked or has unresolved findings. Evidence and findings are saved; review them before continuing. '+detail)
                else:
                    valid=self.valid_evidence(pid,result,require_browser=False,require_coverage=False)
                    if result.get('verdict')!='pass' or not valid:
                        cycles=state.get('repair_cycles',0)+1
                        if cycles>3 or result.get('verdict')=='blocked' or not valid:
                            raise RuntimeError('Verification is blocked or has unresolved findings. Evidence and findings are saved; review them before continuing.')
                        if state.get('execution_mode') in {'direct','blocks'}:
                            self.store.update(pid,phase=coding_phase(state),repair_cycles=cycles)
                            text='Fix these independent review findings without adding scope: '+json.dumps(result)
                            continue
                        tasks=state['tasks']+[dict(id=f'repair-{state["revision"]}-{cycles}',goal=json.dumps(result),depends_on=[],role='sw-developer',status='pending')]
                        self.store.update(pid,tasks=tasks,phase='build',repair_cycles=cycles);continue
                reviews=[('qa','qa-engineer'),('code-review','code-reviewer'),('security','security-auditor'),('accessibility','a11y-auditor')]
                next_reviews=[name for name,reviewer in reviews[1:] if reviewer in state['team']]
                pipeline=['qa',*next_reviews]
                if phase in pipeline and pipeline.index(phase)+1<len(pipeline):
                    self.store.update(pid,phase=pipeline[pipeline.index(phase)+1]);continue
                spec=acceptance.load(root)
                final=acceptance.current(root,spec,acceptance.load_results(root),source_revision(root))
                outcome=acceptance.outcome(final)
                if outcome in {'pending_owner','passed'} and state.get('execution_mode')=='blocks':
                    from .blockbuild import publish_passed
                    publish_passed(self,pid)
                if outcome=='pending_owner':
                    waiting=[(i,r) for i,r in final.items() if r['status']=='pending_owner']
                    self.store.update(pid,phase='implementation_verified',repair_cycles=0)
                    lines=['Implementation verified; live acceptance pending. This is not delivered yet. Waiting on you:']
                    lines+=[f"- {i}: {r.get('next_action') or 'owner setup'}" for i,r in waiting]
                    lines.append('Mark setup items done when they are ready; only the pending checks and reviews will run again.')
                    self.store.message(pid,'assistant','\n'.join(lines),'status')
                    return
                if outcome!='passed':
                    raise RuntimeError('Acceptance results do not match the current source. Verification must run again before delivery.')
                self.store.update(pid,phase='delivered')
                self.store.message(pid,'assistant','Your app is ready. Use Open app to try it. Verified checks are saved with the project.')
                return
            elif phase=='implementation_verified':
                root=Path(state['root'])
                spec=acceptance.load(root)
                final=acceptance.current(root,spec,acceptance.load_results(root),source_revision(root))
                if acceptance.readiness(state)!=(state.get('readiness_verified') or {}) or acceptance.outcome(final)!='pending_owner':
                    # Setup or source changed: verification only, never the builder.
                    self.store.update(pid,phase='qa')
                    continue
                changed=self._change_request(pid,state,text)
                if changed is None:
                    return
                text=changed;continue
            elif phase=='delivered':
                changed=self._change_request(pid,state,text)
                if changed is None:
                    return
                text=changed;continue
            else:
                raise ValueError('Unknown workflow phase: '+phase)
        raise RuntimeError('Workflow step limit reached. Progress is saved.')

    def _criteria_brief(self,state):
        spec=acceptance.load(Path(state['root']))
        pending=[c['id'] for c in acceptance.release_one(spec) if acceptance.deferrable(spec,c,state)]
        return (' Verify every approved release-1 acceptance criterion in .sdlc/acceptance.json (or derived from requirements.md when absent); '
            'criteria with release "later" are out of scope, so do not test or report them '
            'and add "criteria":[{"id":"AC-...","status":"passed|failed|pending_owner|not_run","implemented":true,'
            '"command":"actual command","exit_code":0,"evidence":"path","detail":"...","next_action":"..."}]. '
            'Confirm each criterion\'s implementation exists in source (real route/adapter/code path, not a stub) and run its locally testable behaviour, '
            'using fixtures or fakes only for the live boundary. Report a missing or stubbed implementation as failed. '
            'Use pending_owner only for these live criteria whose owner setup is not ready: '+(', '.join(pending) or 'none')+
            '; even then include the passing local check and evidence. Never report live acceptance as passed without real live evidence. '
            'List only checks that actually exited 0 in "checks"; record failing commands under the failed criterion.')

    def _change_request(self,pid,state,text):
        """Classify a follow-up; return the next goal when it leads to work, else None."""
        result=self.invoke(pid,'change-manager',f'User input: {text}\nInspect the existing app and approved requirements. '
            'Return {"summary":"answer","action":"explain|fix|scope","goal":"bounded change"}. '
            'Choose fix only for an in-scope change covered by approved requirements; material behavior changes require scope. Do not edit files.',readonly=True)
        if result.get('action')=='scope':
            self.store.update(pid,phase='requirements',revision=state['revision']+1,repair_cycles=0,requirements_notes=[text])
            return result.get('goal',text)
        if result.get('action')=='fix':
            tasks=[dict(id='change-'+uuid.uuid4().hex[:6],goal=result.get('goal',text),depends_on=[],role='sw-developer',status='pending')]
            self.store.update(pid,tasks=tasks if state.get('execution_mode')!='blocks' else state['tasks'],phase=coding_phase(state),repair_cycles=0)
            return result.get('goal',text)
        return None

    def valid_evidence(self,pid,result,require_browser=False,require_coverage=True):
        if require_browser and not result.get('browser_tested'):
            return False
        checks=result.get('checks')
        if not isinstance(checks,list) or not checks:
            return False
        root=Path(self.store.get(pid)['root'])
        covered=set()
        for check in checks:
            if check.get('exit_code')!=0 or not check.get('command') or not check.get('evidence'):
                return False
            p=safe_path(root,check['evidence'])
            if not p.is_file() or p.stat().st_size==0:
                return False
            covered.update(check.get('requirements',[]))
        requirements=safe_path(root,'requirements.md')
        expected=set(re.findall(r'\b(?:N?FR)-\d+\b',requirements.read_text())) if requirements.exists() else set()
        return not require_coverage or expected<=covered

    def shutdown(self):
        for pid in list(self.active):
            self.stop(pid)
        self.pool.shutdown(wait=True,cancel_futures=True)


def default_connections():
    return {
        'codex':dict(engine='codex',label='Codex CLI',models=['default']),
        'claude-cli':dict(engine='claude-cli',label='Claude Code CLI',models=['default','sonnet','opus','haiku']),
        'copilot':dict(engine='copilot',label='GitHub Copilot CLI',models=['auto']),
        'ollama-local':dict(engine='ollama',label='Ollama (local)',base_url='http://127.0.0.1:11434/v1',models=[]),
        'openai':dict(engine='openai-compatible',label='OpenAI API',base_url='https://api.openai.com/v1',api_key_env='OPENAI_API_KEY',models=[]),
        'anthropic':dict(engine='anthropic',label='Anthropic API',base_url='https://api.anthropic.com/v1',api_key_env='ANTHROPIC_API_KEY',models=[]),
        'openrouter':dict(engine='openai-compatible',label='OpenRouter',base_url='https://openrouter.ai/api/v1',api_key_env='OPENROUTER_API_KEY',models=[]),
    }
