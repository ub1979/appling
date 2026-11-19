"""Blocks mode: plan blocks, build independent blocks in parallel, then merge the body.

Every agent here is independent: the planner sees only the approved documents
and the library catalogue; each block builder works in its own worktree and
fresh session on one block; the body builder wires blocks through their
declared interfaces. The controller runs each block's approved test command
itself and never treats a builder's report as a pass.
"""
from __future__ import annotations

import json
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from . import acceptance, blocks, swarm

LEAVE = 'Leave these blocks for later'
RETRY = 'Try them again'
PROVIDE = "I'll provide the access first"
EXTEND = 'Extend the blocks they need, then rebuild them'
BLOCK_CHOICES = [LEAVE, RETRY, PROVIDE]
MAX_TEST_REPAIRS = 1


def plan(workflow, pid, text):
    state = workflow.store.get(pid); root = Path(state['root'])
    spec = acceptance.load(root)
    catalogue = blocks.catalogue()
    goal = (f'{text}\nSplit the approved requirements into independent reusable blocks plus one app body. '
            'Read only requirements.md, .sdlc/acceptance.json and prototypes/. Do not write files. '
            'A block is a generic package (blocks/<id>/) with its own interface, tests and README that another project could reuse: '
            'e.g. an AI-provider connector, a Telegram or WhatsApp integration, an admin panel, authentication, a scheduler, a speech engine. '
            'Prefer reusing a compatible library block from this catalogue (source "library:<name>@<version>"): '
            + json.dumps([{k: b[k] for k in ('name', 'version', 'status', 'purpose', 'interface')} for b in catalogue]) + '. '
            'Keep blocks independent; use depends_on only when a block truly needs another block\'s interface. '
            'Keep the body (app/) thin: it is built by one agent after every block finishes, so anything in it is not parallel. '
            'The body only connects blocks: app entry point, configuration, routing and wiring blocks to each other. '
            'Turn each feature area into its own block with a clean interface, even when it serves this app: '
            'e.g. a screens/UI package that takes data and callbacks, a task engine, a report or briefing builder, a sign-in flow. '
            'Keep such blocks generic (settings instead of project names). The body may also list the end-to-end checks it wires, '
            'but nearly every release-1 criterion should be owned by a block. Every release-1 criterion must be covered by a block or the body. '
            'Use runtime "service" only for parts that must run as their own process (another language runtime or long-lived bridge). '
            'Each block needs one self-contained test command run from the project root (and an optional setup command), '
            'for example "cd blocks/telegram-bot && npm install && npm test". '
            'Return {"summary":"plain one-paragraph overview","blocks":[{"id":"telegram-bot","name":"Telegram bot","purpose":"...",'
            '"interface":"exported functions/routes/events with types","runtime":"in-process|service","criteria":["AC-..."],'
            '"depends_on":[],"prerequisites":["P-..."],"source":"new","setup":"","test":"..."}],'
            '"body":{"purpose":"...","criteria":["AC-..."],"files":["package.json"],"test":"..."}}.')
    error = None; fallback = None
    for attempt in range(2):
        result = workflow.invoke(pid, 'sw-architect', goal + (f'\nCorrect this problem in the previous proposal: {error}' if error else ''),
                                 readonly=True, session_scope='blocks-plan-' + uuid.uuid4().hex[:8])
        try:
            checked = blocks.validate(result, spec, catalogue)
        except ValueError as exc:
            error = str(exc)
            if attempt and fallback is None:
                raise ValueError('The block plan is not valid yet: ' + error) from exc
            if attempt:
                checked = fallback   # the earlier valid plan; its review shows the body-size warning
            else:
                continue
        if not attempt and blocks.body_heavy(checked, spec):
            alone = blocks.body_only(checked, spec)
            fallback = checked
            error = (f'The body alone covers {len(alone)} release-1 checks ({", ".join(alone)}). The body is built by one agent '
                     'after the blocks, so it is not parallel. Move those feature areas into blocks and keep the body to wiring.')
            continue
        if attempt and fallback is not None and len(blocks.body_only(checked, spec)) > len(blocks.body_only(fallback, spec)):
            checked = fallback
        blocks.write(root, checked, spec)
        workflow.store.update(pid, phase='blocks_review', block_status={}, tasks=blocks.block_tasks(checked, spec))
        workflow.review(pid, 'blocks')
        return


def _set_status(workflow, pid, ident, **fields):
    with workflow.lock:
        status = dict(workflow.store.get(pid).get('block_status') or {})
        status[ident] = {**status.get(ident, {}), **fields}
        workflow.store.update(pid, block_status=status)
        workflow.store.event(pid, 'block', id=ident, **fields)


FINISHED = {'tested', 'merged'}


def _tasks(workflow, pid, plan_, spec):
    """Rebuild block tasks from the plan. block_status, not the shared task list, records finished blocks
    (the body builder replaces the task list with its own)."""
    state = workflow.store.get(pid)
    status = state.get('block_status') or {}
    wanted = {t['id']: t for t in blocks.block_tasks(plan_, spec)}
    current = {t['id']: t for t in state.get('tasks', []) if t.get('block')}
    tasks = []
    for ident, task in wanted.items():
        old = current.get(ident)
        if status.get(ident, {}).get('status') in FINISHED or (old and old.get('status') == 'done' and ident not in status):
            task['status'] = 'done'
        tasks.append(task)
    workflow.store.update(pid, tasks=tasks)
    return tasks


def _test_and_record(workflow, pid, root, block):
    """Controller-run block test; any crash is a failed test, never an untested pass."""
    try:
        return blocks.run_block_tests(root, block)
    except Exception as exc:
        return dict(passed=False, exit_code=-1, evidence=None, error=str(exc)[:600])


def build(workflow, pid, feedback=''):
    """Build every pending release-1 block, in parallel where independent."""
    from .direct import save_checkpoint, _folder_digest
    from .planning import agent_limit
    from .workflow import WorkWaiting
    workflow.authorized(pid)
    state = workflow.store.get(pid); root = Path(state['root'])
    spec = acceptance.load(root); plan_ = blocks.load(root)
    if plan_ is None:
        raise ValueError('There is no approved block plan yet.')
    by_id = {b['id']: b for b in plan_['blocks']}
    for ident in blocks.deferred(plan_, spec):
        _set_status(workflow, pid, ident, status='later')
    tasks = _tasks(workflow, pid, plan_, spec)
    save_checkpoint(workflow, pid, 'Appling checkpoint before building blocks')
    state = workflow.store.get(pid)
    status_now = state.get('block_status') or {}
    changes_now = state.get('block_change_requests') or {}
    for task in tasks:
        block = by_id[task['id']]
        info = status_now.get(block['id'], {})
        # A block integrated before a restart but never tested by the controller is tested now.
        if task['status'] == 'done' and info.get('status') not in FINISHED and not block['source'].startswith('library:'):
            test = _test_and_record(workflow, pid, root, block)
            _set_status(workflow, pid, block['id'], status='tested' if test['passed'] else 'failed', test=test)
            if not test['passed']:
                swarm._task_status(workflow, pid, block['id'], 'pending')
            continue
        if not block['source'].startswith('library:'):
            continue
        if info.get('local') or info.get('library_failed') or block['id'] in changes_now:
            # Already rebuilt here, failed as a library copy, or needs a change: never reinstall over it.
            block['source'] = 'new'
            continue
        if task['status'] == 'done':
            continue
        try:
            blocks.install(root, block)
            test = _test_and_record(workflow, pid, root, block)
        except (ValueError, OSError) as exc:
            test = dict(passed=False, exit_code=-1, evidence=None, error=str(exc)[:600])
        _set_status(workflow, pid, block['id'], status='tested' if test['passed'] else 'failed', test=test,
                    library=block['source'][8:], library_failed=not test['passed'])
        if test['passed']:
            swarm._task_status(workflow, pid, block['id'], 'done')
        else:
            block['source'] = 'new'   # rebuilt as new work in this project
    stuck, attempted, repairs, counts = {}, set(), {}, {}
    with ThreadPoolExecutor(max_workers=6, thread_name_prefix='appling-block') as pool:
        futures = {}
        while True:
            ready = []
            if not workflow.cancelled[pid].is_set():
                current = workflow.store.get(pid)
                ready = swarm.ready_batch(current['tasks'], agent_limit(workflow.settings()) - len(futures),
                                          active=[t for t, _ in futures.values()], exclude=attempted | set(stuck))
                for task in ready:
                    block = by_id[task['id']]
                    changes = (current.get('block_change_requests') or {}).get(task['id'])
                    note = repairs.get(task['id']) or ('Requested changes for this block (keep everything that already works): ' + '; '.join(changes) if changes else '')
                    # The note is part of the goal, so a repair gets a fresh worker that sees it.
                    task = dict(task, goal=blocks.builder_goal(block, plan_, spec) + (f'\n{note}' if note else ''))
                    attempted.add(task['id'])
                    try:
                        worker, _ = swarm.prepare_worker(workflow, pid, current, task, feedback)
                    except Exception as exc:
                        stuck[task['id']] = str(exc); _set_status(workflow, pid, task['id'], status='blocked', reason=str(exc)[:600])
                        continue
                    _set_status(workflow, pid, task['id'], status='building', worker=worker['id'], local=True)
                    futures[pool.submit(swarm.run_worker, workflow, pid, task, worker)] = (task, worker)
            if not futures:
                if ready and not workflow.cancelled[pid].is_set():
                    continue   # failed setup must not hide other eligible blocks
                break
            finished, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in finished:
                task, worker = futures.pop(future)
                try:
                    future.result()
                    if workflow.cancelled[pid].is_set():
                        raise InterruptedError('Stopped.')
                except InterruptedError:
                    swarm._task_status(workflow, pid, task['id'], 'pending')
                    continue
                except Exception as exc:   # run_worker already saved the worker as blocked
                    swarm._task_status(workflow, pid, task['id'], 'pending')
                    result = worker.get('result') or {}
                    gaps = swarm.dependency_gaps(result, task.get('depends_on', []))
                    if gaps:
                        names = ', '.join(by_id[d]['name'] for d in gaps)
                        stuck[task['id']] = f'Needs changes in {names} before it can be built'
                        _set_status(workflow, pid, task['id'], status='blocked', reason=stuck[task['id']], needs=gaps)
                    else:
                        stuck[task['id']] = str(exc)
                        # Clear requests from an earlier attempt, or the owner is offered a stale "extend" choice.
                        _set_status(workflow, pid, task['id'], status='blocked', reason=str(exc)[:600], needs=None)
                    continue
                try:
                    swarm.integrate_worker(workflow, pid, task, worker)
                except InterruptedError:
                    swarm._task_status(workflow, pid, task['id'], 'pending')
                    continue
                except Exception as exc:
                    # As in build_ready: the next attempt gets a fresh worker with a recovery patch, not a replay.
                    swarm.save_worker(workflow, pid, worker, status='conflict', error=str(exc))
                    swarm._task_status(workflow, pid, task['id'], 'pending')
                    stuck[task['id']] = 'Its changes could not be merged: ' + str(exc)
                    _set_status(workflow, pid, task['id'], status='blocked', reason=stuck[task['id']][:600])
                    continue
                block = by_id[task['id']]
                notes = [str(b.get('detail', ''))[:600] for b in (worker.get('result') or {}).get('blockers') or []
                         if isinstance(b, dict) and b.get('kind') == 'integration']
                test = _test_and_record(workflow, pid, root, block)
                if test['passed']:
                    _set_status(workflow, pid, block['id'], status='tested', test=test, reason=None, host_notes=notes, needs=None)
                    save_checkpoint(workflow, pid, f"Appling checkpoint: block {block['name']} built and tested")
                    try:
                        swarm.workspaces.remove(root, worker['workspace'])
                    except Exception:
                        pass
                    continue
                # Integrated but its own tests fail when the controller runs them: one repair round.
                swarm._task_status(workflow, pid, block['id'], 'pending')
                count = counts.get(block['id'], 0)
                evidence = test.get('evidence')
                log = (root / evidence).read_text(errors='replace')[-3000:] if evidence and (root / evidence).is_file() else test.get('error', '')
                if count < MAX_TEST_REPAIRS:
                    counts[block['id']] = count + 1
                    repairs[block['id']] = 'The controller ran the approved test command and it failed. Fix the block. Output:\n' + log
                    attempted.discard(block['id'])
                    _set_status(workflow, pid, block['id'], status='failed', test=test)
                else:
                    stuck[block['id']] = 'Its tests still fail when Appling runs them.'
                    _set_status(workflow, pid, block['id'], status='blocked', reason=stuck[block['id']], test=test)
    if workflow.cancelled[pid].is_set():
        raise InterruptedError('Stopped. Built blocks and retained block workspaces are saved.')
    remaining = [t for t in workflow.store.get(pid)['tasks'] if t['status'] != 'done']
    if stuck or remaining:
        waiting = sorted(set(stuck) | {t['id'] for t in remaining})
        parts = [f"{by_id[i]['name']}: {(stuck.get(i) or 'waits for a block that could not be finished')[:240]}" for i in waiting]
        needs = {}
        for ident in waiting:
            for dep, details in ((workflow.store.get(pid).get('block_status') or {}).get(ident, {}).get('needs') or {}).items():
                needs.setdefault(dep, []).extend(details)
        ask_blocks(workflow, pid, waiting, parts, needs, by_id)
        raise WorkWaiting('Some blocks could not be finished. The others are built and tested. Decide what to do with:\n'
                          + '\n'.join('- ' + p for p in parts), reason='blocks', blockers=[dict(kind='implementation', detail=p, owner='you',
                                                                                                 next_action='Choose: leave for later, try again, or provide access') for p in parts])
    # The body may not change blocks; remember exactly what the tested blocks looked like.
    workflow.store.update(pid, phase='body', block_change_requests={}, blocks_digest=_folder_digest(root, ['blocks/']))


def ask_blocks(workflow, pid, ids, parts, needs=None, by_id=None):
    for item in workflow.store.inbox(pid):
        if item.get('blocks_scope'):
            workflow.store.close(pid, item['id'])
    needs = needs or {}
    lines = ['These blocks could not be finished; the other blocks are built and tested:', ''] + ['- ' + p for p in parts]
    if needs:
        lines += ['', 'Some of them need a block they depend on to offer more:']
        for dep, details in needs.items():
            name = by_id[dep]['name'] if by_id and dep in by_id else dep
            lines += [f'- {name} needs: ' + '; '.join(d[:200] for d in details[:4])]
        lines += ['', f'"{EXTEND}" sends those requests to that block\'s builder, then rebuilds the blocks that need it.']
    lines += ['', 'You can also leave them for a later release (their checks move to "later" and you review that change), '
              'try them again as they are, or set up the access they need first. You can type which ones to keep.']
    choices = ([EXTEND] if needs else []) + BLOCK_CHOICES
    return workflow.store.ask(pid, 'question', '\n'.join(lines), choices, blocks_scope=True, block_ids=ids, needs=needs)


def answer(workflow, pid, item, choice):
    """Owner decision about stuck blocks."""
    from .direct import BUILD_SOME
    state = workflow.store.get(pid); root = Path(state['root'])
    workflow.store.close(pid, item['id']); workflow.store.message(pid, 'user', choice, 'answer')
    ids = item.get('block_ids', [])
    if choice == EXTEND and item.get('needs'):
        needs = item['needs']
        status = dict(state.get('block_status') or {})
        for dep in needs:
            status.setdefault(dep, {}).update(status='planned', local=True,
                                              reason='Extending its interface for the blocks that need it')
        for ident in ids:
            status.setdefault(ident, {}).update(status='planned')
        workflow.store.update(pid, phase='blocks_build', block_status=status, block_change_requests=needs)
        workflow.submit(pid, 'Extend ' + ', '.join(needs) + ' as requested, then rebuild the blocks that need it.', kind='auto')
        return
    if choice == RETRY:
        status = dict(state.get('block_status') or {})
        for ident in ids:
            status.setdefault(ident, {})['status'] = 'planned'
        workflow.store.update(pid, phase='blocks_build', block_status=status)
        workflow.submit(pid, 'The owner asked to try these blocks again: ' + ', '.join(ids), kind='auto')
    elif choice == PROVIDE:
        workflow.store.update(pid, paused=True)
        workflow.store.message(pid, 'assistant', 'OK. Tick each setup item in the Acceptance panel when it is ready, then send "continue". '
                               'Nothing will run until then.', 'status')
    elif choice == LEAVE:
        plan_ = blocks.load(root); spec = acceptance.load(root)
        # Record the owner's choice itself. A deferred block's checks move to later unless another block that stays
        # also implements them; the body's integration coverage does not keep a feature nobody will build.
        spec['deferred_blocks'] = sorted(set(spec.get('deferred_blocks') or []) | set(ids))
        left = set(spec['deferred_blocks'])
        moving = {c for b in plan_['blocks'] if b['id'] in ids for c in b['criteria']}
        keep = set().union(*(set(b['criteria']) for b in plan_['blocks'] if b['id'] not in left))
        for criterion in spec['criteria']:
            if criterion['id'] in moving - keep:
                criterion['release'] = 'later'
        acceptance.write(root, spec)
        for ident in ids:
            _set_status(workflow, pid, ident, status='later')
        approvals = {k: v for k, v in state['approvals'].items() if k != 'requirements'}
        workflow.store.update(pid, phase='requirements_review', approvals=approvals)
        shared = sorted(moving & keep)
        workflow.store.message(pid, 'assistant', 'Left for later: ' + ', '.join(ids) + '. '
                               + (f'Checks shared with other parts stay in this release: {", ".join(shared)}. ' if shared else '')
                               + 'Review the updated requirements; the other blocks stay built.', 'status')
        workflow.review(pid, 'requirements')
    else:
        workflow.store.update(pid, phase='rescope', rescope=dict(choice=choice, parts=ids))
        workflow.submit(pid, choice if choice != BUILD_SOME else 'Build some blocks now, leave the rest for later', kind='auto')


def body_goal(plan_, spec, status=None):
    usable = [b for b in plan_['blocks'] if b['id'] not in blocks.deferred(plan_, spec)]
    return ('Build the app body in app/ (and the root files it owns: ' + ', '.join(plan_['body']['files']) + ') and wire in the finished blocks. '
            f"Body purpose: {plan_['body']['purpose']}. Use blocks only through their documented interfaces (README.md and block.json): "
            + json.dumps([dict(id=b['id'], folder=b['folder'], interface=b['interface']) for b in usable]) + '. '
            'Do not edit anything under blocks/. If a block interface must change, report an implementation blocker with "block":"<id>" '
            'and what must change, instead of editing it. Blocks moved to a later release are out of scope. '
            + (('Block builders left these items for the app to provide: ' + json.dumps({k: v.get('host_notes') for k, v in (status or {}).items()
                                                                                          if v.get('host_notes')}) + '. ') if status else '')
            + (f"Run the body test: {plan_['body']['test']}. " if plan_['body'].get('test') else ''))


def publish_passed(workflow, pid):
    """Save blocks that passed their own tests and project QA to the shared library."""
    state = workflow.store.get(pid); root = Path(state['root'])
    plan_ = blocks.load(root)
    if not plan_:
        return []
    spec = acceptance.load(root)
    status = state.get('block_status') or {}
    results = acceptance.load_results(root)
    commit = None
    try:
        commit = swarm.workspaces.git(root, 'rev-parse', 'HEAD')
    except Exception:
        pass
    published = []
    for block in plan_['blocks']:
        info = status.get(block['id'], {})
        if info.get('status') not in {'tested', 'merged'} or block['id'] in blocks.deferred(plan_, spec):
            continue
        if any(results.get(c, {}).get('status') == 'failed' for c in block['criteria']):
            continue
        fully = all(results.get(c, {}).get('status') == 'passed' for c in block['criteria'])
        meta = blocks.publish(root, block, state.get('name') or pid, commit=commit, evidence=(info.get('test') or {}).get('evidence'),
                              verified=fully)
        if meta:
            published.append(f"{meta['name']} {meta['version']} ({meta['status']})")
            _set_status(workflow, pid, block['id'], status='merged', library=f"{meta['name']}@{meta['version']}")
    if published:
        workflow.store.message(pid, 'assistant', 'Saved to your block library: ' + ', '.join(published) + '.', 'status')
    return published


def adopt_new_criteria(workflow, pid, root):
    """After the owner approves updated requirements, give new checks to the blocks that own that requirement.
    Finished blocks that receive a check are reopened with a change request. Returns the new plan revision
    owner-approved by the requirements approval, or None when the plan cannot be fitted (it is then replanned)."""
    plan_ = blocks.load(root); spec = acceptance.load(root)
    if not plan_:
        return None
    fitted, added = blocks.adopt_criteria(plan_, spec)
    try:
        # Library sources were checked when the plan was approved; only coverage and structure are rechecked.
        pinned = [dict(zip(('name', 'version'), b['source'][8:].rsplit('@', 1))) for b in fitted['blocks']
                  if b['source'].startswith('library:') and '@' in b['source']]
        fitted = blocks.validate(fitted, spec, pinned)
    except ValueError:
        return None
    blocks.write(root, fitted, spec)
    status = workflow.store.get(pid).get('block_status') or {}
    described = {c['id']: c['description'] for c in spec['criteria']}
    notes = dict(workflow.store.get(pid).get('block_change_requests') or {})
    reopened = []
    for cid, owners in added.items():
        for ident in owners:
            if ident == 'body':
                continue
            notes.setdefault(ident, []).append(f'New release-1 check {cid}: {described[cid]}')
            if status.get(ident, {}).get('status') in FINISHED:
                _set_status(workflow, pid, ident, status='planned', local=True, reason=f'New check {cid} added by the owner')
                reopened.append(ident)
    workflow.store.update(pid, block_change_requests=notes)
    if added:
        names = {b['id']: b['name'] for b in fitted['blocks']}
        parts = [f"{cid} → " + ', '.join(names.get(o, 'the app body') for o in owners) for cid, owners in added.items()]
        workflow.store.message(pid, 'assistant', 'New checks added to the block plan: ' + '; '.join(parts) + '. '
                               + (f"Reopening finished blocks to add them: {', '.join(names[i] for i in dict.fromkeys(reopened))}. " if reopened else '')
                               + 'Other blocks stay built.', 'status')
    from .workflow import artifact_revision
    return artifact_revision(root, 'blocks')


def reopen_blocks(workflow, pid, blockers):
    """The body needs a block interface change: send that block back to its own builder. Returns True if any reopened."""
    state = workflow.store.get(pid); root = Path(state['root'])
    plan_ = blocks.load(root); spec = acceptance.load(root)
    if not plan_:
        return False
    known = {b['id'] for b in plan_['blocks']} - set(blocks.deferred(plan_, spec))
    notes = {}
    for b in blockers:
        if b.get('block') in known:
            notes.setdefault(b['block'], []).append(str(b.get('detail', ''))[:600])
    if not notes:
        return False
    for ident, details in notes.items():
        _set_status(workflow, pid, ident, status='planned', local=True,
                    reason='Interface change requested by the app body: ' + '; '.join(details))
    workflow.store.update(pid, phase='blocks_build', block_change_requests=notes)
    _tasks(workflow, pid, plan_, spec)
    return True
