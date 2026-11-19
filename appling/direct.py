"""One native builder session, followed by the controller's independent reviews."""
from pathlib import Path
import hashlib
import json
import uuid

from . import acceptance, checkpoints, swarm

MAX_CONTINUATIONS = 3
KEEP_ALL = 'Keep building all of them'
BUILD_SOME = 'Build some now, leave the rest for later'
LEAVE_ALL = 'Leave all of them for later'
PROVIDE_FIRST = "I'll provide the access first"
SCOPE_CHOICES = [BUILD_SOME, LEAVE_ALL, KEEP_ALL, PROVIDE_FIRST]


def ask_scope(workflow, pid, parts, intro):
    """Put unfinishable parts to the owner. Only the owner may move scope to a later release."""
    for item in workflow.store.inbox(pid):
        if item.get('scope'):workflow.store.close(pid, item['id'])
    lines = [intro, '']
    lines += [f'- {p}' for p in parts[:12]]
    lines += ['', 'These usually need real accounts, devices or services to build and test properly. '
              'You can keep them, build only some (say which), leave them for a later release, or set up access first. '
              'Moving anything to later changes the requirements, so you will review that change before coding continues.']
    return workflow.store.ask(pid, 'question', '\n'.join(lines), SCOPE_CHOICES, scope=True, parts=parts[:12])


def _blockers(result):
    value = result.get('blockers', [])
    if not isinstance(value, list) or any(not isinstance(b, dict) or
            b.get('kind') not in {'implementation','owner_setup','live_acceptance'} or
            not isinstance(b.get('detail'), str) or not b['detail'].strip() for b in value):
        raise ValueError('Builder blockers need a supported kind and a specific detail.')
    return value


def outcomes(result):
    """Stable facts from a handoff: check commands/exit codes and blocker kinds/criteria.

    Receipt bytes and wording differ on every run (timestamps, durations), so they
    cannot tell progress from a repeat.
    """
    result = result or {}
    checks = sorted((str(c.get('command')), c.get('exit_code')) for c in result.get('checks') or [] if isinstance(c, dict))
    blockers = sorted((str(b.get('kind')), tuple(sorted(str(x) for x in b.get('criteria') or [])))
                      for b in result.get('blockers') or [] if isinstance(b, dict))
    return dict(status=result.get('status'), checks=checks, blockers=blockers)


def progress_signature(root, state, result=None):
    """What a retry could have changed: source, approved criteria, owner setup and check outcomes."""
    from .workflow import source_revision
    root = Path(root)
    return hashlib.sha256(json.dumps(dict(
        source=source_revision(root),
        criteria=acceptance.spec_digest(root),
        readiness=acceptance.readiness(state),
        outcomes=outcomes(result)), sort_keys=True, default=str).encode()).hexdigest()


def deferred_failures(result, spec, state):
    """Split failing builder checks: those tied only to deferrable live criteria may wait."""
    deferrable = {c['id'] for c in acceptance.release_one(spec) if acceptance.deferrable(spec, c, state)}
    allowed, unlinked = [], []
    for check in result.get('checks') or []:
        if not isinstance(check, dict) or check.get('exit_code') == 0:
            continue
        linked = check.get('criteria') if isinstance(check.get('criteria'), list) else []
        (allowed if linked and set(linked) <= deferrable else unlinked).append(check)
    return allowed, unlinked


def save_checkpoint(workflow, pid, message):
    """A milestone commit on the project branch; failures are reported, not fatal."""
    state = workflow.store.get(pid)
    try:
        root = Path(state['root'])
        if not (root / '.git').exists():
            # Same repository bootstrap the QA snapshots use, so the first handoff is kept.
            from .workspaces import git
            git(root, 'init', '-b', 'main')
        saved = checkpoints.checkpoint(root, message, label=state.get('name') or pid)
    except Exception as exc:  # A checkpoint must never discard or block retained work.
        workflow.store.event(pid, 'checkpoint', status='failed', text=str(exc)[:800])
        return None
    if saved and saved.get('changed'):
        workflow.store.update(pid, last_checkpoint=dict(commit=saved['commit'], ref=saved['ref'], message=message))
        workflow.store.event(pid, 'checkpoint', status='saved', commit=saved['commit'], ref=saved['ref'],
                             branch_updated=saved.get('branch_updated'), skipped=len(saved.get('skipped', [])),
                             text=saved.get('note') or message)
    return saved


def actionable(blockers, spec):
    """Give every blocker an owner, a next action and, where stated, criteria and evidence."""
    known = {c['id'] for c in spec['criteria']}
    out = []
    for b in blockers:
        item = dict(kind=b['kind'], detail=b['detail'],
                    owner='builder' if b['kind'] == 'implementation' else 'you',
                    next_action=str(b.get('next_action') or b['detail'])[:500])
        criteria = [c for c in b.get('criteria', []) if isinstance(c, str) and c in known] if isinstance(b.get('criteria'), list) else []
        if criteria:item['criteria'] = criteria
        if isinstance(b.get('evidence'), str) and b['evidence'].strip():item['evidence'] = b['evidence']
        out.append(item)
    return out


def set_mode(workflow, pid, mode):
    if mode not in {'direct', 'planned', 'blocks'}:
        raise ValueError('Choose direct, planned or blocks execution.')
    with workflow.lock:
        state = workflow.store.get(pid)
        if pid in workflow.active or state['running']:
            raise ValueError('Stop the project and wait for its agents before changing build coordination.')
        if mode == state.get('execution_mode', 'planned'):
            return
        if any(item.get('runtime') for item in workflow.store.inbox(pid)):
            raise ValueError('Resolve the pending operation before changing build coordination.')
        workflow.store.checkpoint(pid, 'execution-history:'+uuid.uuid4().hex,
            {k:state.get(k) for k in ('phase','tasks','workers','approvals','execution_mode')})
        phase = state['phase']
        coding = {'build','plan','plan_review','qa','security','code-review','accessibility','delivered',
                  'blocks_plan','blocks_review','blocks_build','body','implementation_verified'}
        if phase in coding:
            for item in workflow.store.inbox(pid):
                if item['kind'] in {'plan','blocks'}:workflow.store.close(pid, item['id'])
            if mode == 'direct':
                phase = 'build'
            elif mode == 'planned':
                phase = 'plan'
            else:
                from .workflow import artifact_revision
                ok = state['approvals'].get('blocks') and state['approvals']['blocks'] == artifact_revision(Path(state['root']), 'blocks')
                phase = 'blocks_build' if ok else 'blocks_plan'
        workflow.store.update(pid, execution_mode=mode, phase=phase, tasks=[], paused=True,
                              queue=[], plan_draft=None)
        workflow.store.message(pid, 'assistant',
            'Build coordination changed. Files, approvals and retained work are saved. Send a message to continue.', 'status')


def _folder_digest(root, folders):
    """Source content only: build output, caches, dependencies and virtual environments are ignored."""
    digest = hashlib.sha256()
    for folder in folders:
        base = Path(root) / folder
        for p in sorted(base.rglob('*')) if base.is_dir() else []:
            rel = p.relative_to(root).as_posix()
            if (not p.is_file() or p.is_symlink() or checkpoints.denied(rel) or '.pytest_cache' in p.parts
                    or '.build' in p.parts or '.swiftpm' in p.parts or p.name.endswith('.tsbuildinfo')):
                continue
            digest.update(rel.encode()); digest.update(p.read_bytes())
    return digest.hexdigest()


def build(workflow, pid, feedback, goal_prefix='', session_scope='direct-build-v1', protect=()):
    from .workflow import WorkWaiting, source_revision
    workflow.authorized(pid)
    state = workflow.store.get(pid)
    task_id = 'direct-build'
    worker = next((w for w in state.get('workers', []) if w['id'] == state.get('direct_worker_id')), None)
    if worker is None:
        worker = dict(id=uuid.uuid4().hex[:12], task_id=task_id, role='sw-developer', kind='development',
                      workspace=state['root'], goal='Build the approved requirements',
                      evidence='.sdlc/evidence/direct-build/', status='pending')
    workflow.store.update(pid, direct_worker_id=worker['id'], tasks=[dict(
        id=task_id, goal=worker['goal'], role='sw-developer', depends_on=[], status='running')])
    swarm.save_worker(workflow, pid, worker, status='running', error=None)
    try:
        goal = f'{feedback}\n{goal_prefix}\nBuild and integrate the approved requirements in this project using your native tools. ' + (
            'Inspect current source, saved progress and retained handoffs first; preserve useful work. '
            'There is no mandatory implementation-plan document, task graph, host worktree pool or task ownership split in direct mode. '
            'You own implementation and wiring across the application; organize the work using the execution engine. '
            'Respect the approved design when supplied. Do not edit requirements.md, plan.md, prototypes/ or controller approvals. '
            'Run affected builds/tests and real browser checks for UI. Retain concrete owner/device/account blockers; '
            'do not install untrusted drivers, grant OS permissions or perform unapproved external actions. '
            'Save fresh nonempty command/exit/output receipts only under .sdlc/evidence/direct-build/. '
            'Return {"status":"completed|blocked","summary":"...","checks":'
            '[{"command":"actual command","exit_code":0,"evidence":".sdlc/evidence/direct-build/..."}],'
            '"blockers":[{"kind":"implementation|owner_setup|live_acceptance","detail":"...","criteria":["AC-..."],"evidence":"path","next_action":"..."}]}. '
            'Implement and locally test the code paths of live criteria too; owner setup postpones only the live check. '
            'A completed response hands the built application to independent QA; it never declares delivery. '
            'Build only release-1 requirements; anything tagged Release: later is out of scope for now. '
            'Write progress commentary for a non-technical owner: name the app feature you are working on and what now works, '
            'without file, function or test names.')
        current = workflow.store.get(pid)
        if (current.get('last_wait_reason') == 'prerequisites' and current.get('stalled_attempts', 0) >= 1
                and current.get('last_wait_signature') == progress_signature(state['root'], current, worker.get('result'))):
            # Two identical setup-blocked attempts already ran; do not spend a third builder run.
            raise WorkWaiting('Still waiting; nothing changed since the last two attempts, so the builder was not run again. '
                              'Record the setup, change the approved criteria (/criteria) or change the code first.\n'
                              + '\n'.join(f"- {b['kind'].replace('_',' ')} ({b['owner']}): {b['next_action']}"
                                           for b in current.get('last_wait_blockers', [])),
                              reason='no_progress', blockers=current.get('last_wait_blockers', []))
        save_checkpoint(workflow, pid, 'Appling checkpoint before resuming the build')
        turn = (state.get('turn') or {}).get('id')
        saved = state.get('direct_continuation') or {}
        retries = saved.get('retries', 0) if saved.get('turn') == turn else 0
        last_signature = None
        while True:
            # Compare with the tested blocks recorded when block building finished, so an earlier edit is never accepted.
            protected_before = ((workflow.store.get(pid).get('blocks_digest') or _folder_digest(state['root'], protect))
                                if protect else None)
            result = workflow.invoke(pid, 'sw-developer', goal, session_scope=session_scope)
            if protect and _folder_digest(state['root'], protect) != protected_before:
                raise ValueError('The app body changed files inside ' + ', '.join(protect) +
                                 '. Blocks change only through their own builder; report the needed interface change instead.')
            reopen = [b for b in (result.get('blockers') or []) if isinstance(b, dict) and b.get('block') and protect]
            if reopen:
                from .blockbuild import reopen_blocks
                if reopen_blocks(workflow, pid, reopen):
                    return
                # Unknown or deferred block ids are ordinary blockers handled below, never a silent rerun.
            swarm.save_worker(workflow, pid, worker, result=result)
            workflow.authorized(pid)
            if workflow.cancelled[pid].is_set():
                raise InterruptedError('Stopped. Builder files and session are retained.')
            if result.get('status') not in {'completed','blocked'}:
                raise ValueError('Builder must return a completed or blocked handoff.')
            spec = acceptance.load(Path(state['root']))
            later = {c['id'] for c in spec['criteria'] if c['release'] == 'later'}
            # Blockers that concern only parts the owner moved to a later release are out of scope now.
            blockers = [b for b in _blockers(result)
                        if not (isinstance(b.get('criteria'), list) and b['criteria'] and set(b['criteria']) <= later)]
            if not blockers and result['status'] == 'blocked' and len(_blockers(result)) > 0:
                result = dict(result, status='completed')
            if result['status'] == 'completed' and not blockers:
                break
            current = workflow.store.get(pid)
            allowed_failures, unlinked_failures = deferred_failures(result, spec, current)
            implementation = [b for b in blockers if b['kind'] == 'implementation'] + [
                dict(kind='implementation', detail=f"Check failed (exit {c.get('exit_code')}): {c.get('command')}",
                     evidence=c.get('evidence')) for c in unlinked_failures]
            signature = progress_signature(state['root'], current, result)
            changed = last_signature is None or signature != last_signature
            last_signature = signature
            if implementation and retries < MAX_CONTINUATIONS and (not retries or changed):
                retries += 1
                workflow.store.update(pid,direct_continuation=dict(turn=turn,retries=retries),attention=None)
                workflow.store.event(pid,'build_continuation',attempt=retries,blockers=blockers,
                    text='Continuing remaining implementation; setup and live checks remain blocked.')
                workflow.store.message(pid,'assistant',
                    'Continuing the remaining coding work. Setup, permission and live-test blockers are retained; no additional access is granted.','progress')
                workflow.store.event(pid,'status_update',text='Continuing remaining implementation.')
                goal = ('Continue the retained implementation and session; inspect the latest handoff and source. '
                    'Complete the remaining in-scope coding work listed below using native specialists when useful. '
                    'Work independently of missing owner setup and live acceptance where possible. '
                    'Do not retry denied operations, change approvals, install drivers, grant permissions or perform '
                    'external actions without their existing authorization. Preserve all prior evidence, including failures. '
                    'Actually run affected checks and return the same structured status/checks/blockers contract. '
                    'Owner setup and live acceptance remain release blockers, never a passing substitute. '
                    'Retained handoff: '+json.dumps(result))
                continue
            if blockers and not implementation and acceptance.has_deferrable(spec, current):
                # Only approved live criteria with unmet recorded prerequisites can wait;
                # independent QA still verifies the implementation and local behaviour.
                # A failed live attempt tied only to such criteria is retained, not validated as a pass.
                passing = [c for c in result.get('checks') or [] if c not in allowed_failures]
                swarm.validate_checks(Path(state['root']), {}, worker, dict(result, status='completed', checks=passing))
                save_checkpoint(workflow, pid, 'Appling checkpoint: builder handoff with owner setup pending')
                swarm.save_worker(workflow, pid, worker, status='integrated')
                tasks = workflow.store.get(pid)['tasks']
                for task in tasks:task['status'] = 'done'
                workflow.store.update(pid, tasks=tasks, phase='qa', direct_continuation=None, attention=None,
                                      builder_blockers=actionable(blockers, spec), last_wait_signature=None, stalled_attempts=0)
                workflow.store.message(pid, 'assistant', 'Coding handoff saved with setup still pending. Independent QA will now verify '
                                       'everything that can run without it; live checks stay pending, never passed.', 'progress')
                return
            reason = 'implementation' if implementation else 'prerequisites' if blockers else 'handoff'
            message = ('Coding needs a decision after bounded continuation; retained work is saved.' if implementation else
                       'Waiting for setup or live verification; retained work is saved. No approved acceptance criterion records this setup, '
                       'so it cannot be deferred: use /criteria to approve live criteria and prerequisites, or provide the setup and resume.' if blockers else
                       'Builder requested attention without specific blockers; inspect the retained handoff.')
            blockers = actionable([*blockers, *implementation[len([b for b in blockers if b['kind'] == 'implementation']):]], spec)
            stalled = current.get('stalled_attempts', 0) + 1 if current.get('last_wait_signature') == signature else 0
            if stalled:
                message += (f'\nNo progress since the previous attempt ({stalled} in a row): the source, builder evidence, '
                            'approved criteria and recorded setup are unchanged. Change one of them before resuming.')
            workflow.store.update(pid, last_wait_signature=signature, stalled_attempts=stalled, last_wait_reason=reason,
                                  last_wait_message=message, last_wait_blockers=blockers)
            save_checkpoint(workflow, pid, 'Appling checkpoint: partial builder handoff')
            details = '\n'.join(f"- {b['kind'].replace('_',' ')} ({b['owner']}): {b['next_action']}"
                                + (f" [criteria: {', '.join(b['criteria'])}]" if b.get('criteria') else '')
                                + (f" [evidence: {b['evidence']}]" if b.get('evidence') else '') for b in blockers)
            if implementation:
                ask_scope(workflow, pid, [str(b.get('next_action') or b['detail'])[:300] for b in blockers if b['kind'] == 'implementation'],
                          f"Some parts of {current.get('name') or 'the app'} could not be finished after several coding rounds:")
            raise WorkWaiting(message+('\n'+details if details else ''),reason=reason,blockers=blockers)
        # Reuse the receipt/exit/path checks, without inventing a planned graph.
        swarm.validate_checks(Path(state['root']), {}, worker, result)
        if workflow.cancelled[pid].is_set():
            raise InterruptedError('Stopped. Builder files and session are retained.')
        save_checkpoint(workflow, pid, 'Appling checkpoint: builder handoff ready for QA')
        swarm.save_worker(workflow, pid, worker, status='integrated')
        tasks = workflow.store.get(pid)['tasks']
        for task in tasks:
            task['status'] = 'done'
        workflow.store.update(pid, tasks=tasks, phase='qa',direct_continuation=None,attention=None,
                              builder_blockers=[],last_wait_signature=None,stalled_attempts=0)
    except BaseException as exc:
        swarm.save_worker(workflow, pid, worker,
                          status='interrupted' if workflow.cancelled[pid].is_set() else 'blocked', error=str(exc))
        tasks = workflow.store.get(pid)['tasks']
        for task in tasks:
            task['status'] = 'pending'
        workflow.store.update(pid, tasks=tasks)
        raise
