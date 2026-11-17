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

ARTIFACTS = {'prototype':'prototypes/index.html','requirements':'requirements.md','plan':'plan.md'}
CHOICES = {'prototype':['Approve prototype','Request changes'],
           'requirements':['Approve requirements','Request changes'],
           'plan':['Approve implementation plan','Request changes']}
ROLES = {'requirements':'req-engineer','prototype':'ui-designer','plan':'task-planner',
         'build':'sw-developer','qa':'qa-engineer','security':'security-auditor','deploy':'devops-engineer'}


def artifact_revision(root, kind):
    names=[ARTIFACTS[kind]]
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
        if not isinstance(task,dict) or not task.get('id') or not task.get('goal'):
            raise ValueError('Every task needs an ID and a goal.')
        if task['id'] in ids:
            raise ValueError('Task IDs must be unique.')
        ids.add(task['id'])
        tasks.append(dict(id=task['id'],goal=task['goal'],depends_on=task.get('depends_on',[]),
                          role=task.get('role','sw-developer'),status='pending'))
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
                store.update(p['id'],running=False,paused=True)
                store.message(p['id'],'assistant','Appling restarted. Your files and task checkpoints are saved. Send a message to continue.','status')
            for item in store.inbox(p['id']):
                if item['kind'] in {'approval','question'} and item.get('runtime'):
                    store.close(p['id'],item['id'])

    def settings(self):
        return self.store.setting('ai',dict(provider='codex',model='',effort='',about_me='',agent_models={},
            parallel_work=dict(max_workers=3),connections=default_connections()))

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
        with self.lock:
            pending=[i for i in self.store.inbox(pid) if i['kind'] in {'question','prototype','requirements','plan'}
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
            self.store.update(pid,paused=False,queue=[*state['queue'],item])
            self.store.event(pid,'queued',item=item)
            self._start(pid)
            return item

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
                        self.store.update(pid,queue=state['queue'][1:],running=True,turn=item)
                if item is None:
                    if self.cancelled[pid].wait(.2):
                        return
                    continue
                self.store.event(pid,'turn_start',turn=item['id'],text=item['text'],kind=item['kind'])
                status='completed';error=None
                try:
                    self._advance(pid,item['text'])
                except InterruptedError as exc:
                    status='interrupted';self.store.message(pid,'assistant',str(exc),'status')
                except Exception as exc:
                    status='error';error=f'{type(exc).__name__}: {exc}'
                    self.store.event(pid,'problem',text=error)
                    self.store.message(pid,'assistant',error,'status')
                    self.store.update(pid,paused=True)
                finally:
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

    def runtime_ask(self,pid,kind,question,choices):
        item=self.store.ask(pid,kind,question,choices,runtime=True,**({'command':question} if kind=='approval' else {}))
        try:
            while not self.cancelled[pid].wait(.15):
                with self.lock:
                    if item['id'] in self.answers:
                        return self.answers.pop(item['id'])
            raise InterruptedError('Stopped while waiting for an answer.')
        finally:
            if any(i['id']==item['id'] for i in self.store.inbox(pid)):
                self.store.close(pid,item['id'])

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
                self.store.close(pid,iid)
                if choice==CHOICES[kind][0]:
                    approvals={**state['approvals'],kind:revision}
                    phase={'prototype':'requirements_review','requirements':'plan','plan':'build'}[kind]
                    self.store.update(pid,approvals=approvals,phase=phase)
                    self.store.message(pid,'assistant',f'{kind.capitalize()} approved.','status')
                    self.submit(pid,f'Continue from approved {kind}.',kind='auto')
                else:
                    feedback=answer.get('feedback','Please ask what needs changing.') if isinstance(answer,dict) else 'Ask what needs changing.'
                    phase={'prototype':'prototype','requirements':'requirements','plan':'plan'}[kind]
                    approvals=dict(state['approvals'])
                    for k in list(approvals):
                        if kind=='requirements' or k==kind or k=='plan':
                            approvals.pop(k,None)
                    self.store.update(pid,phase=phase,approvals=approvals)
                    self.store.message(pid,'user',feedback)
                    self.submit(pid,feedback,kind='auto')
            else:
                self.store.close(pid,iid);self.store.message(pid,'user',choice,'answer')
                self.submit(pid,choice,kind='auto')
            return dict(ok=True)

    def review(self,pid,kind):
        root=Path(self.store.get(pid)['root']);revision=artifact_revision(root,kind)
        if not revision:
            raise ValueError(f'The {kind} artifact is missing.')
        question=f'Review the {kind} before continuing.'
        if kind!='prototype':
            question+='\n\n'+safe_path(root,ARTIFACTS[kind]).read_text()
        self.store.ask(pid,kind,question,CHOICES[kind],revision=revision)

    def authorized(self,pid):
        state=self.store.get(pid);root=Path(state['root'])
        for kind in ARTIFACTS:
            if state['approvals'].get(kind)!=artifact_revision(root,kind) or not state['approvals'].get(kind):
                raise PermissionError(f'The current {kind} needs approval before implementation can continue.')

    def invoke(self,pid,role,goal,readonly=False):
        key,conn,selection=self.connection(role)
        state=self.store.get(pid)
        # A changed model/skill gets a new session; existing prefixes stay unchanged.
        instructions=context.instructions(role)
        if self.settings().get('about_me'):
            instructions+='\nOwner preferences (apply only where compatible with project requirements):\n'+self.settings()['about_me']
        fingerprint=hashlib.sha256((key+json.dumps(conn,sort_keys=True)+selection.get('model','')+instructions).encode()).hexdigest()[:16]
        session_key=role+':'+fingerprint
        self.store.update(pid,engine=key,requirements_started=True)
        usage_baseline=state.get('session_usage',{}).get(session_key,{})
        def save_session(sid):
            current=self.store.get(pid);self.store.update(pid,sessions={**current['sessions'],session_key:sid})
        def save_usage(usage):
            if 'total' in usage:
                total=usage['total']
                current=self.store.get(pid)
                self.store.update(pid,session_usage={**current.get('session_usage',{}),session_key:total})
                usage={name:max(0,total.get(native,0)-usage_baseline.get(native,0)) for name,native in
                       [('input_tokens','inputTokens'),('cached_input_tokens','cachedInputTokens'),('output_tokens','outputTokens')]}
            elif conn['engine']=='claude-cli':
                cached=usage.get('cache_read_input_tokens',0)
                usage=dict(input_tokens=usage.get('input_tokens',0)+cached+usage.get('cache_creation_input_tokens',0),
                           cached_input_tokens=cached,output_tokens=usage.get('output_tokens',0))
            self.store.event(pid,'usage',provider=key,role=role,usage=usage)
        self.store.event(pid,'helper',event='start',subagent_id=role,goal=role)
        try:
            run=Run(root=Path(state['root']),instructions=instructions,
                prompt=context.briefing(self.store,pid,role,goal),model='' if selection.get('model')=='default' else selection.get('model',''),effort=selection.get('effort',''),
                readonly=readonly,session=state['sessions'].get(session_key),cancel=self.cancelled[pid],
                emit=lambda t,**kw:self.store.event(pid,t,**kw),
                ask=lambda k,q,c:self.runtime_ask(pid,k,q,c),recall=lambda q:self.store.search(pid,q),
                save_session=save_session,save_usage=save_usage)
            data=self.execute(conn,run)
            if self.cancelled[pid].is_set():
                raise InterruptedError('Stopped. Files are saved; send a message to continue.')
            context.checkpoint(self.store,pid,role,goal,data,self.store.get(pid)['phase'])
            self.store.event(pid,'helper',event='complete',subagent_id=role,goal=role,status='completed')
            if data.get('summary'):
                self.store.message(pid,'assistant',data['summary'])
                self.store.event(pid,'interim',text=data['summary'])
            return data
        except BaseException:
            context.checkpoint(self.store,pid,role,goal,'Interrupted or blocked; inspect existing files before retrying.',self.store.get(pid)['phase'])
            self.store.event(pid,'helper',event='complete',subagent_id=role,goal=role,status='error')
            raise

    def _write(self,pid,name,text):
        path=safe_path(Path(self.store.get(pid)['root']),name);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text);self.store.remember(pid,name,text)

    def _advance(self,pid,text):
        for step in range(100):
            if self.cancelled[pid].is_set():
                raise InterruptedError('Stopped. Your files and checkpoints are saved.')
            state=self.store.get(pid);phase=state['phase']
            if phase=='requirements':
                result=self.invoke(pid,'req-engineer',f'User input: {text}\nInterview for requirements; ask only unanswered questions, one at a time. '
                    'Respect skip/decide/defaults. For existing apps distinguish explanation or in-scope fixes from material scope changes. '
                    'Return {"summary":"...","question":"one question","choices":["..."]} while gaps remain; '
                    'when ready return {"summary":"...","requirements":"complete Markdown with stable requirement IDs, journeys, assumptions and acceptance criteria"}. '
                    'Do not implement the app. Do not ask for approvals yourself; the controller handles those.',readonly=True)
                if result.get('question'):
                    self.store.ask(pid,'question',result['question'],result.get('choices',[]));return
                if not isinstance(result.get('requirements'),str) or not result['requirements'].strip():
                    raise ValueError('Requirements are incomplete. Continue the interview.')
                if not re.search(r'\bFR-\d+\b',result['requirements']):
                    raise ValueError('Requirements need stable FR IDs and acceptance criteria before prototype work.')
                self._write(pid,'requirements.md',result['requirements'])
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
            elif phase=='requirements_review':
                self.review(pid,'requirements');return
            elif phase=='plan':
                result=self.invoke(pid,'task-planner',f'{text}\nPlan the approved requirements. Use small coherent tasks. '
                    'Return {"summary":"...","plan":"readable Markdown plan including verification commands",'
                    '"tasks":[{"id":"task-1","goal":"bounded goal and acceptance criteria","depends_on":[],"role":"sw-developer"}]}. '
                    'Use selected specialist roles where useful, including architecture, UX writing, documentation or deployment preparation. '
                    'Deployment tasks prepare and locally validate; actual remote deployment requires separate explicit owner authorization. '
                    'Do not implement code. Keep the plan proportional to project size.',readonly=True)
                tasks=parse_tasks(result.get('tasks'))
                if not isinstance(result.get('plan'),str) or not result['plan'].strip():
                    raise ValueError('The readable implementation plan is missing.')
                self._write(pid,'plan.md',result['plan'])
                self.store.update(pid,tasks=tasks,phase='plan_review')
                self.review(pid,'plan');return
            elif phase=='plan_review':
                self.review(pid,'plan');return
            elif phase=='build':
                self.authorized(pid)
                tasks=state['tasks'];done={t['id'] for t in tasks if t['status']=='done'}
                task=next((t for t in tasks if t['status']!='done' and set(t['depends_on'])<=done),None)
                if task is None:
                    if any(t['status']!='done' for t in tasks):
                        raise ValueError('No task is ready; resolve its dependencies.')
                    self.store.update(pid,phase='qa');continue
                task['status']='running';self.store.update(pid,tasks=tasks)
                role=task.get('role','sw-developer')
                if role not in state['team']:
                    role='sw-developer'
                result=self.invoke(pid,role,f'Implement task {task["id"]}: {task["goal"]}. '
                    'Inspect existing work before editing; do not discard it. Leave requirements.md, plan.md and prototypes/ unchanged. '
                    'Run meaningful affected build/tests, save evidence under .sdlc/evidence/. '
                    'Use the installed browser automation for UI verification when relevant. '
                    'Return {"summary":"...","status":"completed|blocked","checks":[{"command":"...","exit_code":0,"evidence":".sdlc/evidence/..."}]}.')
                self.authorized(pid)
                if result.get('status')!='completed':
                    raise RuntimeError('Development is blocked. Review the saved task report and continue when resolved.')
                task['status']='done';self.store.update(pid,tasks=tasks)
            elif phase in {'qa','security'}:
                self.authorized(pid)
                role='qa-engineer' if phase=='qa' else 'security-auditor'
                before=source_revision(Path(state['root']))
                result=self.invoke(pid,role,
                    'Independently verify the integrated application against approved requirements. Do not edit application source. '
                    'For QA, run real builds/tests and interact with every approved core UI journey using Playwright or available browser tools. '
                    'For requested phone/computer targets, use their actual emulator/device/native automation as well; report missing access as blocked. '
                    'Save raw logs/screenshots under .sdlc/evidence/. A browser UI without browser evidence is BLOCKED. '
                    'For security, check the actual auth/data/dependencies relevant to this app, without destructive external testing. '
                    'Return {"summary":"...","verdict":"pass|fail|blocked","browser_tested":true,"platforms_tested":["web"],'
                    '"checks":[{"command":"actual command or browser actions","exit_code":0,"evidence":".sdlc/evidence/path","requirements":["FR-001"]}],'
                    '"findings":[{"description":"...","severity":"high"}]}.')
                self.authorized(pid)
                after=source_revision(Path(state['root']))
                if before!=after:
                    raise RuntimeError('Verification changed application source. Its evidence is invalid; inspect the changes and rerun verification.')
                result['source_revision']=after
                self._write(pid,f'.sdlc/{phase}-report.json',json.dumps(result,indent=2))
                valid=self.valid_evidence(pid,result,require_browser=phase=='qa' and state['kind'] in {'app','website'},require_coverage=phase=='qa')
                if phase=='qa' and any(p!='web' and p not in result.get('platforms_tested',[]) for p in state['platforms']):
                    valid=False
                if result.get('verdict')!='pass' or not valid:
                    cycles=state.get('repair_cycles',0)+1
                    if cycles>3 or result.get('verdict')=='blocked' or not valid:
                        raise RuntimeError('Verification is blocked or has unresolved findings. Evidence and findings are saved; review them before continuing.')
                    tasks=state['tasks']+[dict(id=f'repair-{state["revision"]}-{cycles}',goal=json.dumps(result),depends_on=[],role='sw-developer',status='pending')]
                    self.store.update(pid,tasks=tasks,phase='build',repair_cycles=cycles);continue
                if phase=='qa' and 'security-auditor' in state['team']:
                    self.store.update(pid,phase='security');continue
                self.store.update(pid,phase='delivered')
                self.store.message(pid,'assistant','Your app is ready. Use Open app to try it. Verified checks are saved with the project.')
                return
            elif phase=='delivered':
                result=self.invoke(pid,'change-manager',f'User input: {text}\nInspect the existing app and approved requirements. '
                    'Return {"summary":"answer","action":"explain|fix|scope","goal":"bounded change"}. '
                    'Choose fix only for an in-scope change covered by approved requirements; material behavior changes require scope. Do not edit files.',readonly=True)
                if result.get('action')=='scope':
                    self.store.update(pid,phase='requirements',revision=state['revision']+1,repair_cycles=0,requirements_notes=[text])
                    text=result.get('goal',text);continue
                if result.get('action')=='fix':
                    tasks=[dict(id='change-'+uuid.uuid4().hex[:6],goal=result.get('goal',text),depends_on=[],role='sw-developer',status='pending')]
                    self.store.update(pid,tasks=tasks,phase='build',repair_cycles=0);continue
                return
            else:
                raise ValueError('Unknown workflow phase: '+phase)
        raise RuntimeError('Workflow step limit reached. Progress is saved.')

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
