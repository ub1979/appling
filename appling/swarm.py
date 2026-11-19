"""Bounded dependency-aware workers, with a single integration owner."""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
import hashlib
import json
import uuid

from . import workspaces
from .store import safe_path


def save_worker(workflow, pid, worker, **fields):
    with workflow.lock:
        worker.update(fields)
        workers = workflow.store.get(pid).get('workers', [])
        workers = [dict(worker) if w['id'] == worker['id'] else w for w in workers]
        if not any(w['id'] == worker['id'] for w in workers):
            workers.append(dict(worker))
        workflow.store.update(pid, workers=workers)
        workflow.store.event(pid, 'worker', worker=dict(worker))


def ready_batch(tasks, limit, *, active=(), exclude=()):
    if limit < 1:
        return []
    done = {t['id'] for t in tasks if t['status'] == 'done'}
    excluded = set(exclude) | {t['id'] for t in active}
    ready = [t for t in tasks if t['status'] != 'done' and t['id'] not in excluded
             and set(t['depends_on']) <= done]
    selected = []
    for task in ready:
        if all(workspaces.independent(task, other) for other in (*active, *selected)):
            selected.append(task)
        if len(selected) >= limit:
            break
    return selected


def identity(state,task):
    return hashlib.sha256(json.dumps(dict(revision=state['revision'],approvals=state['approvals'],
        goal=task['goal'],files=task.get('files',[]),role=task.get('role','sw-developer'),
        kind=task.get('kind','development'),depends_on=task['depends_on'],
        acceptance=task.get('acceptance',[])),sort_keys=True).encode()).hexdigest()


def task_goal(task, evidence=None):
    verification=task.get('kind')=='verification'
    return ((f'Independently verify task {task["id"]}: ' if verification else f'Implement task {task["id"]}: ')+task['goal']+'. '
            + ('Application source is read-only. Do not repair it. Report defects; changed source invalidates all verification. '
               if verification else '')+
            'Inspect existing work before editing; do not discard it. Leave requirements.md, plan.md and prototypes/ unchanged. '
            + (f'You own ONLY these files/folders: {task["files"]}. Other tasks run concurrently in isolated worktrees. '
               'Do not run git commit/checkout/reset or merge other workers. Return blocked if a shared interface or ownership needs changing. '
               f'Save all test logs and browser evidence under {evidence}. ' if evidence else
               'Save evidence under .sdlc/evidence/. ')
            + 'Run meaningful affected builds/tests and use the installed browser runner for UI checks where relevant. '
              'Run each planned acceptance command exactly as declared, including combined commands; list each exact command in checks. '
              'Every evidence file must be nonempty and record the executed command, actual exit status and output. '
              'For silent successful checks, record the command, exit status and that there was no output; an empty log is not evidence. '
              'Return {"summary":"...","status":"completed|blocked",'+
              ('"verdict":"pass|fail|blocked",' if verification else '')+
              '"blockers":[{"kind":"implementation|integration|owner_setup|live_acceptance",'
              '"detail":"specific missing prerequisite","requires_tasks":["task-id"]}],'
              '"checks":[{"command":"...","exit_code":0,"evidence":".sdlc/evidence/..."}]}. '
              'Use an empty blockers list when none remain. If blocked, retain all check results including failures; '
              'identify which other task owns each missing contract and distinguish owner setup from implementation. '
              'Do not waive acceptance or mark a task complete because only its subset checks passed.')


class IncompleteEvidence(ValueError):
    """A recoverable handoff omission; it never counts as a passing check."""


def dependency_gaps(result, depends_on):
    """Blockers saying a block it depends on lacks something: {dependency id: [details]}."""
    gaps={}
    for b in result.get('blockers') or []:
        if not isinstance(b,dict) or b.get('kind') not in {'integration','implementation'}:
            continue
        detail=str(b.get('detail',''))
        named=[b['block']] if b.get('block') in depends_on else [d for d in depends_on if d in detail]
        for dep in named:
            gaps.setdefault(dep,[]).append(detail[:600])
    return gaps


def block_handoff(result, depends_on=()):
    """A block builder's handoff. Live parts waiting on owner setup do not stop a block; integration
    notes that name no dependency are for the app body; failing runs recorded on the way (for example
    tests written first) are history. The controller runs the block's approved test itself afterwards."""
    blockers=[b for b in result.get('blockers') or [] if isinstance(b,dict)]
    if result.get('status')!='blocked' or not blockers or dependency_gaps(result,depends_on):
        return result
    if all(b.get('kind') in {'owner_setup','live_acceptance'} or (b.get('kind')=='integration' and not b.get('block'))
           for b in blockers):
        return dict(result,status='completed')
    return result


def validate_checks(root,task,worker,result):
    if task.get('block'):
        result=block_handoff(result,task.get('depends_on',[]))
        if result.get('status')!='completed':
            summary=result.get('summary')
            raise RuntimeError('Worker reported a blocker: '+(summary[:1200] if isinstance(summary,str) and summary.strip() else 'Inspect its retained workspace.'))
        return
    if result.get('status')!='completed':
        summary=result.get('summary')
        detail=summary[:1200] if isinstance(summary,str) and summary.strip() else 'Inspect its retained workspace and checkpoint.'
        raise RuntimeError('Worker reported a blocker: '+detail)
    checks=result.get('checks')
    if not isinstance(checks,list) or not checks:
        raise IncompleteEvidence('Worker completion needs passing checks and saved evidence.')
    for check in checks:
        if not isinstance(check,dict):raise ValueError('Worker checks must be structured evidence records.')
        evidence=check.get('evidence','')
        command=check.get('command')
        if not isinstance(command,str) or not command.strip():
            raise ValueError('Worker checks must name the actual executed command.')
        if type(check.get('exit_code')) is not int:
            raise ValueError('Worker checks must record an integer exit code: '+command)
        if not isinstance(evidence,str) or not evidence.startswith(worker['evidence']):
            raise ValueError('Worker check evidence must use its assigned evidence folder: '+command)
        path=safe_path(root,evidence)
        if not path.is_relative_to(safe_path(root,worker['evidence'])):
            raise ValueError('Worker evidence must stay inside its assigned evidence folder.')
        if check['exit_code']!=0:
            raise ValueError(f'Worker check failed (exit {check["exit_code"]}): {command}. Evidence: {evidence}')
        if not path.is_file() or not path.stat().st_size:
            raise IncompleteEvidence('Worker check evidence is missing or empty: '+evidence)
    expected={c['command'] for c in task.get('acceptance',[])}
    if not expected<={c['command'] for c in checks}:
        raise IncompleteEvidence('Worker evidence does not cover every planned acceptance command: '+json.dumps(sorted(expected)))
    if task.get('kind')=='verification' and result.get('verdict')!='pass':
        raise ValueError('Independent verification did not pass; preserve evidence and report findings.')


def run_worker(workflow, pid, task, worker):
    from .workflow import ARTIFACTS, artifact_revision
    root = Path(worker['workspace'])
    save_worker(workflow, pid, worker, status='running', error=None)
    try:
        if workflow.cancelled[pid].is_set():
            raise InterruptedError('Stopped before starting the worker. Its workspace is retained.')
        # A completed but unintegrated worker survives a stopped coordinator.
        if worker.get('commit'):
            current=workspaces.snapshot(root,worker['base'],include=[worker['evidence']])
            if workspaces.git(root,'rev-parse',current+'^{tree}')!=workspaces.git(root,'rev-parse',worker['commit']+'^{tree}'):
                # An edited retained worktree needs fresh verification, not reuse
                # of a result describing different bytes.
                save_worker(workflow,pid,worker,commit=None,result=None,integration_started=False)
        result = worker.get('result') if worker.get('commit') else None
        if not result:
            from .preflight import require_runtime
            from .context import ROOT
            require_runtime(root,workflow.store.get(pid).get('plan_contract',{}).get('runtime',{}),ROOT/'scripts/browser-check.mjs')
            before=workspaces.snapshot(root,worker['base'],include=[worker['evidence']]) if task.get('kind')=='verification' else None
            goal=task_goal(task,worker['evidence'])
            if worker.get('recovery'):
                goal+=' A previous conflicting attempt is available as .appling/recovery.patch. Reconcile relevant changes with current source; never blindly overwrite current work or extend ownership.'
            if worker.get('resume_feedback'):
                goal+=' Latest owner guidance: '+worker['resume_feedback']
            for attempt in range(2):
                result=workflow.invoke(pid,worker['role'],goal,workspace=root,worker=worker)
                # A blocked response is still a durable handoff, not completion.
                # Retain evidence and prerequisites for UI, restart and replanning.
                save_worker(workflow,pid,worker,result=result)
                if task.get('kind')=='verification':
                    after=workspaces.snapshot(root,worker['base'],include=[worker['evidence']])
                    changed=workspaces.changes(root,before,after)
                    if any(not workspaces.owns([*task.get('files',[]),worker['evidence']],name) for name in changed):
                        raise ValueError('Verification changed application source. Its evidence is invalid; report a development repair.')
                try:validate_checks(root,task,worker,result)
                except IncompleteEvidence as exc:
                    if attempt:raise
                    workflow.store.event(pid,'worker_evidence',status='retry',worker_id=worker['id'],text=str(exc))
                    goal=task_goal(task,worker['evidence'])+' Repair the incomplete evidence handoff in this retained workspace: '+str(exc)+(
                        ' Preserve finished work. Actually rerun the affected checks; never invent receipts or infer success from prose. '
                        'Return a complete checks array covering every exact planned command, with nonempty command/exit/output receipts.')
                else:break
        validate_checks(root,task,worker,result)
        workflow.authorized(pid)
        for kind, revision in workflow.store.get(pid)['approvals'].items():
            if kind in ARTIFACTS and artifact_revision(root, kind) != revision:
                raise ValueError('A worker modified approved requirements, prototype, or plan.')
        commit = worker.get('commit') or workspaces.snapshot(root, worker['base'], include=[worker['evidence']])
        workspaces.git(root, 'update-ref', 'refs/appling/workers/' + worker['id'], commit)
        save_worker(workflow, pid, worker, status='completed', result=result, commit=commit)
        return worker
    except BaseException as exc:
        status = 'interrupted' if workflow.cancelled[pid].is_set() else 'blocked'
        save_worker(workflow, pid, worker, status=status, error=str(exc))
        raise


def prepare_worker(workflow, pid, state, task, feedback, base=None):
    """Reuse a retained attempt, or snapshot the latest integrated dependencies."""
    from .planning import validate_role
    if not task.get('files'):
        raise ValueError('Task ownership is missing. Replan or assess ownership before execution.')
    validate_role(task.get('kind','development'), task.get('role','sw-developer'), task['files'])
    signature = identity(state, task)
    worker = next((w for w in reversed(state.get('workers', []))
                   if w['task_id'] == task['id'] and w.get('signature') == signature
                   and w['status'] in {'pending', 'interrupted', 'blocked', 'completed', 'conflict', 'integrating'}
                   and Path(w['workspace']).is_dir()), None)
    resuming = worker is not None
    previous = worker if worker and worker['status'] == 'conflict' else None
    if previous:
        worker = None
    if not worker:
        root = Path(state['root'])
        if base is None:
            base = workspaces.snapshot(root)
        ident = uuid.uuid4().hex[:12]
        directory = workflow.store.home / 'workers' / pid / ident
        workspaces.create(root, directory, base)
        worker = dict(id=ident, task_id=task['id'], role=task.get('role','sw-developer'), goal=task['goal'],
                      kind=task.get('kind','development'), signature=signature,
                      workspace=str(directory), base=base, status='pending',
                      evidence=f'.sdlc/evidence/workers/{ident}/')
        if previous:
            recovery = directory / '.appling/recovery.patch'
            recovery.parent.mkdir(exist_ok=True)
            recovery.write_bytes(workspaces.patch(previous['workspace'], previous['base'], previous['commit']))
            worker['recovery'] = previous['id']
            save_worker(workflow, pid, previous, status='retained')
    if resuming and feedback:
        worker['resume_feedback'] = feedback
    save_worker(workflow, pid, worker)
    _task_status(workflow, pid, task['id'], 'running')
    return worker, base


def integrate_worker(workflow, pid, task, worker):
    """Only the coordinator applies results and durably releases dependencies."""
    with workflow.lock:
        if workflow.cancelled[pid].is_set():
            raise InterruptedError('Stopped before integration. Completed work is retained.')
        workflow.authorized(pid)
        root = Path(workflow.store.get(pid)['root'])
        save_worker(workflow, pid, worker, status='integrating', integration_started=True)
        changed = workspaces.integrate(root, worker['workspace'], worker['base'], worker['commit'],
                                       task.get('files', []), worker['evidence'], allow_applied=True)
        worker.update(status='integrated', changed=changed)
        current = workflow.store.get(pid)
        for record in current['workers']:
            if record['id'] == worker['id']:
                record.update(worker)
        for record in current['tasks']:
            if record['id'] == task['id']:
                record['status'] = 'done'
        workflow.store.update(pid, workers=current['workers'], tasks=current['tasks'])
        workflow.store.event(pid, 'worker', worker=dict(worker))
    workflow.store.checkpoint(pid, worker['role'], dict(goal=task['goal'], outcome=worker['result'],
                              next_action='Verify the integrated app.', worker_id=worker['id']))


def build_ready(workflow, pid, feedback=''):
    """Keep eligible slots busy; integrate each completion before refilling them."""
    workflow.authorized(pid)
    from .planning import agent_limit
    attempted = set()
    failures = []
    with ThreadPoolExecutor(max_workers=6, thread_name_prefix='appling-worker') as pool:
        futures = {}
        while True:
            batch = []
            if not workflow.cancelled[pid].is_set():
                state = workflow.store.get(pid)
                limit = agent_limit(workflow.settings())
                batch = ready_batch(state['tasks'], limit - len(futures),
                                    active=[task for task, _ in futures.values()], exclude=attempted)
                base = None
                for task in batch:
                    if workflow.cancelled[pid].is_set():
                        break
                    workflow.authorized(pid)
                    attempted.add(task['id'])
                    try:
                        worker, base = prepare_worker(workflow, pid, state, task, feedback, base)
                        future = pool.submit(run_worker, workflow, pid, task, worker)
                        futures[future] = (task, worker)
                    except Exception as exc:
                        failures.append(task['id'] + ': ' + str(exc))
            if not futures:
                if batch and not workflow.cancelled[pid].is_set():
                    continue  # Failed setup must not hide other eligible tasks.
                break
            finished, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in finished:
                task, worker = futures.pop(future)
                try:
                    future.result()
                except BaseException as exc:
                    _task_status(workflow, pid, task['id'], 'pending')
                    failures.append(task['id'] + ': ' + str(exc))
                    continue
                if workflow.cancelled[pid].is_set():
                    _task_status(workflow, pid, task['id'], 'pending')
                    continue
                try:
                    integrate_worker(workflow, pid, task, worker)
                except InterruptedError:
                    _task_status(workflow, pid, task['id'], 'pending')
                    if not workflow.cancelled[pid].is_set():
                        raise
                except Exception as exc:
                    save_worker(workflow, pid, worker, status='conflict', error=str(exc))
                    _task_status(workflow, pid, task['id'], 'pending')
                    failures.append(task['id'] + ': ' + str(exc))
    if workflow.cancelled[pid].is_set():
        raise InterruptedError('Stopped all project workers. Isolated workspaces and sessions are retained.')
    if failures:
        raise RuntimeError('Project work needs attention; completed safe changes are integrated and other work is retained. ' + '; '.join(failures))
    if any(t['status'] != 'done' for t in workflow.store.get(pid)['tasks']):
        raise ValueError('No task is ready; resolve its dependencies.')
    return bool(attempted)


def _task_status(workflow, pid, ident, status):
    with workflow.lock:
        tasks = workflow.store.get(pid)['tasks']
        for task in tasks:
            if task['id'] == ident:
                task['status'] = status
        workflow.store.update(pid, tasks=tasks)


def verify_project(workflow,pid,role,goal):
    """Run controller QA in a fresh snapshot; integrate only its new evidence."""
    workflow.authorized(pid)
    state=workflow.store.get(pid);root=Path(state['root'])
    base=workspaces.snapshot(root);ident=uuid.uuid4().hex[:12]
    directory=workflow.store.home/'workers'/pid/ident
    workspaces.create(root,directory,base)
    worker=dict(id=ident,task_id='controller-'+role,role=role,kind='verification',goal='Independent '+role,
                workspace=str(directory),base=base,status='running',evidence=f'.sdlc/evidence/workers/{ident}/')
    save_worker(workflow,pid,worker)
    try:
        result=workflow.invoke(pid,role,goal+' Save all new evidence ONLY under '+worker['evidence']+
            '. Application source and prior evidence are read-only; report repairs without editing them.',
            workspace=directory,worker=worker)
        commit=workspaces.snapshot(directory,base,include=[worker['evidence']])
        names=workspaces.changes(directory,base,commit)
        if any(not workspaces.owns([worker['evidence']],name) for name in names):
            raise ValueError('Verification changed application source or prior evidence. Its evidence is invalid; inspect its retained workspace.')
        workflow.authorized(pid)
        workspaces.integrate(root,directory,base,commit,[],worker['evidence'])
        save_worker(workflow,pid,worker,status='integrated',result=result,commit=commit)
        return dict(result,_evidence_folder=worker['evidence'])
    except BaseException as exc:
        save_worker(workflow,pid,worker,status='blocked',error=str(exc))
        raise
