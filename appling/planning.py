"""Make parallel execution a checked plan contract, using the real scheduler."""
from __future__ import annotations

from .swarm import ready_batch
import json
import re
from .context import CATALOG


POLICY = 'parallel-v2'
# Rotate planner sessions when briefing semantics change, without invalidating
# approved execution contracts or mutating a live session's instructions/tools.
SESSION_VERSION = POLICY + '-acceptance-prerequisites-v3'
MAX_PLAN_ATTEMPTS = 4


def validate_role(kind,role,files):
    if kind not in {'development','integration','verification'}:
        raise ValueError('Task kind must be development, integration or verification.')
    if role not in {entry[0] for entry in CATALOG['AGENTS']}:
        raise ValueError('Unknown task role: '+str(role))
    reviewers={'qa-engineer','security-auditor','code-reviewer','a11y-auditor'}
    if (kind=='verification') != (role in reviewers):
        raise ValueError('Verification tasks require a reviewer role; reviewers cannot implement application source.')
    if kind=='verification' and any(not p.startswith(('tests/','.sdlc/evidence/')) for p in files):
        raise ValueError('Verification ownership is limited to tests/ and .sdlc/evidence/.')


def strings(value,label,allow_empty=False):
    if not isinstance(value,list) or (not value and not allow_empty) or any(not isinstance(v,str) or not v.strip() for v in value):
        raise ValueError(label+' must be a list of nonempty strings.')
    return value


def validate_contract(result,tasks,root):
    """Check executable coverage and contracts, not claims in Markdown."""
    expected=set(re.findall(r'\bN?FR-\d+\b',(root/'requirements.md').read_text()))
    raw={t['id']:t for t in result['tasks']}
    covered=set();by={t['id']:t for t in tasks}
    for task in tasks:
        if 'kind' not in raw[task['id']]:
            raise ValueError('Every task must explicitly declare its kind: '+task['id'])
        refs=set(strings(task.get('requirements'),'Task requirements'))
        if not refs<=expected:raise ValueError('Task references unknown requirements: '+task['id'])
        covered.update(refs)
        strings(task.get('outputs'),'Task outputs')
        checks=task.get('acceptance')
        if not isinstance(checks,list) or not checks or any(not isinstance(c,dict) or
                not isinstance(c.get('command'),str) or not c['command'].strip() or
                not isinstance(c.get('expect'),str) or not c['expect'].strip() for c in checks):
            raise ValueError('Every task needs acceptance commands and expected outcomes: '+task['id'])
        inputs=task.get('inputs')
        if not isinstance(inputs,list) or any(not isinstance(i,dict) or not isinstance(i.get('contract'),str) or
                not i['contract'].strip() or i.get('task') not in task['depends_on'] for i in inputs):
            raise ValueError('Task inputs must name dependency contracts: '+task['id'])
        if {i['task'] for i in inputs}!=set(task['depends_on']):
            raise ValueError('Every dependency needs an input contract: '+task['id'])
    if expected-covered:raise ValueError('Requirements lack implementation/verification ownership: '+', '.join(sorted(expected-covered)))
    def ancestors(task):
        found=set();pending=list(task['depends_on'])
        while pending:
            ident=pending.pop()
            if ident not in found:found.add(ident);pending.extend(by[ident]['depends_on'])
        return found
    for task in tasks:
        available=ancestors(task)
        for check in task['acceptance']:
            required=strings(check.get('requires_tasks'),'Acceptance requires_tasks',allow_empty=True)
            if not set(required)<=available:
                raise ValueError('Acceptance for '+task['id']+' requires tasks outside its upstream dependencies: '+
                                 ', '.join(sorted(set(required)-available))+'. Move the prerequisite earlier or the check after integration.')
    integrations=[t for t in tasks if t['kind']=='integration']
    implementations={t['id'] for t in tasks if t['kind']!='verification'}
    if not any(implementations<={t['id']}|ancestors(t) for t in integrations):
        raise ValueError('A final integration task must consume all implementation outputs.')
    for task in tasks:
        if task['kind']=='verification' and not any(t['id'] in ancestors(task) for t in integrations):
            raise ValueError('Independent verification must follow integration.')
    runtime=result.get('runtime')
    if not isinstance(runtime,dict) or not isinstance(runtime.get('browser'),bool):
        raise ValueError('Declare runtime tools, bootstrap and browser prerequisites.')
    strings(runtime.get('bootstrap'),'Runtime bootstrap',allow_empty=True)
    tools=runtime.get('tools')
    if not isinstance(tools,list) or any(not isinstance(t,dict) or not isinstance(t.get('name'),str) or
            not isinstance(t.get('minimum'),str) or not re.fullmatch(r'[A-Za-z0-9_.+-]+',t['name']) or
            not re.fullmatch(r'\d+(?:\.\d+){0,2}',t['minimum']) for t in tools):
        raise ValueError('Runtime tools need executable names and minimum numeric versions.')
    if len({t['name'] for t in tools})!=len(tools):raise ValueError('Runtime tool names must be unique.')
    journeys=result.get('journeys')
    if not isinstance(journeys,list) or not journeys:raise ValueError('Provide end-to-end acceptance journeys.')
    journey_coverage=set();ids=set()
    for journey in journeys:
        if not isinstance(journey,dict) or not isinstance(journey.get('id'),str) or not journey['id'] or journey['id'] in ids:
            raise ValueError('Acceptance journeys need unique IDs.')
        ids.add(journey['id'])
        refs=set(strings(journey.get('requirements'),'Journey requirements'))
        owners=set(strings(journey.get('tasks'),'Journey task IDs'))
        if not refs<=expected or not owners<=set(by):raise ValueError('Journey references unknown requirements or tasks.')
        if not refs<=set().union(*(set(by[t]['requirements']) for t in owners)):
            raise ValueError('Journey tasks do not own the mapped requirements.')
        for field in ['trigger','operations','review','result','check']:
            if not isinstance(journey.get(field),str) or not journey[field].strip():
                raise ValueError('Every journey needs trigger, operations, review, result and check.')
        journey_coverage.update(refs)
    if expected-journey_coverage:raise ValueError('Requirements lack end-to-end acceptance journeys: '+', '.join(sorted(expected-journey_coverage)))
    return dict(runtime=runtime,journeys=journeys)


def agent_limit(settings):
    return max(1, min(6, settings.get('parallel_work', {}).get('agents_per_project', 3)))


def require_parallel_capacity(settings):
    limit = agent_limit(settings)
    if limit < 2:
        raise ValueError('Parallel app development requires at least 2 development agents per project. '
                         'Increase the limit in Settings before planning or continuing this plan.')
    return limit


def execution_waves(tasks, limit):
    """Preview safe dependency groups, assuming equal task durations, without I/O."""
    if limit < 2:
        raise ValueError('A parallel implementation plan needs capacity for at least 2 agents.')
    missing = [task['id'] for task in tasks if not task.get('files')]
    if missing:
        raise ValueError('Every scheduled task needs explicit file ownership; missing: ' + ', '.join(missing))
    pending = [dict(task, status='pending') for task in tasks]
    waves = []
    while any(task['status'] != 'done' for task in pending):
        batch = ready_batch(pending, limit)
        if not batch:
            raise ValueError('The task plan has missing dependencies or a cycle.')
        waves.append([task['id'] for task in batch])
        for task in batch:
            task['status'] = 'done'
    if not any(len(wave) >= 2 for wave in waves):
        raise ValueError('The implementation plan would run entirely on one agent. '
                         'Split independent implementation or acceptance-test work into scheduled tasks '
                         'with disjoint ownership and real dependencies. Prose-only worker packages do not execute.')
    return waves


def planning_goal(feedback, limit):
    return (
        f'{feedback}\nReplan implementation from the approved requirements and prototype/design. '
        'Inspect current source and checkpoints; preserve useful existing work and approved behavior. '
        'If the briefing supplies a reusable-block catalogue, evaluate compatible verified versions before '
        'planning new code; record pinned versions, configuration and app-specific integration checks. '
        'Do not assume a block catalogue or a previously verified integration exists when none is supplied. '
        'Do not change requirements, design or scope. Do not implement code. '
        f'The host can run up to {limit} development agents concurrently in isolated worktrees. '
        'Return {"summary":"...","plan":"readable Markdown plan including contracts and verification commands",'
        '"tasks":[{"id":"task-1","goal":"bounded goal, requirement IDs, input/output contract and acceptance command",'
        '"depends_on":[],"kind":"development|integration|verification","role":"sw-developer",'
        '"files":["src/feature/"],"requirements":["FR-001"],"inputs":[],"outputs":["exported interface"],'
        '"acceptance":[{"command":"actual test command","expect":"observable outcome","requires_tasks":[]}]}],'
        '"runtime":{"tools":[{"name":"node","minimum":"24.13.0"}],"bootstrap":["npm ci","npm run build"],"browser":true},'
        '"journeys":[{"id":"J01","requirements":["FR-001"],"tasks":["task-1"],"trigger":"user input",'
        '"operations":"actual execution through implemented interfaces","review":"approval or read-only boundary",'
        '"result":"observable persisted result","check":"end-to-end test command"}]}. '
        'Use actual project runtime requirements, not the example versions. Isolated worktrees have no node_modules or dist: '
        'declare bootstrap/build prerequisites. Every dependency needs inputs:[{"task":"dependency-id","contract":"exact consumed output"}]. '
        'Map every FR/NFR in requirements.md to tasks and end-to-end journeys, including verification of optional disabled routes. '
        'A journey must connect the user input to the real operation, review/resume and verified result; listing adapters is insufficient. '
        'Make the final integration depend transitively on all implementation tasks. '
        'Use kind=verification and a qa-engineer/security-auditor/code-reviewer/a11y-auditor role for independent review. '
        'Verification may own only tests/ and .sdlc/evidence/; source changes invalidate its results. '
        'The controller already runs final QA, so do not add a developer task masquerading as independent QA. '
        'Every worker package must be an entry in tasks; the host does not execute nested packages in prose. '
        'Give EVERY task explicit nonempty plain relative file/folder ownership; folders end in /. '
        'Include at least one safe wave with two or more useful independent tasks. '
        'Use selected specialist roles where useful. Personal profile limits product scope, not useful worker count. '
        'Establish shared API/schema contracts and scaffolding in a small foundation task if necessary, '
        'Audit completion prerequisites, not only the dependency DAG. Each acceptance check must declare requires_tasks '
        '(all other task outputs needed to execute it, or []); they must be upstream ancestors. Never require host wiring '
        'from a downstream integration task to complete an upstream feature. Assign prerequisite shared HTTP routes, '
        'authenticated identity and private capability factories to an early bounded task, or test features against '
        'frozen contracts and assign real combined-service checks to dependent integration/verification. '
        'Separate useful implementation from owner-dependent live acceptance without dropping any requirement: '
        'retain early native feasibility evidence and disabled routes, but put permission/account/device/participant '
        'and multi-day acceptance in explicit downstream gates. Missing live evidence must still block release; '
        'never turn nonzero exits or fixture checks into live passes. Do not relax existing approved acceptance in place. '
        'For recovery, inspect planning.recovery retained workspaces, checkpoints and results. Reuse integrated source '
        'as baseline and give replacement tasks exact read-only retained inputs for their owned implementation; '
        'rerun checks on the combined current contracts. Do not redo completed work or impose an arbitrary task count. '
        'then split independent features/frontend/backend/acceptance-test implementation into parallel tasks. '
        'For every dependency name the exact input needed in the readable plan; never chain by list order. '
        'Give shared config and lockfiles one owner. Do not add overlapping writable paths within a wave. '
        'Include a dependent integration task to check the combined app, followed by the controller\'s independent QA. '
        'Preserve browser evidence requirements. Deployment tasks prepare and locally validate only; '
        'remote deployment needs separate explicit owner authorization. '
        'Avoid filler tasks or extra product features to inflate agent count. '
        'If useful parallel work is genuinely impossible, return a concrete blocker instead of a serial plan.'
    )


def with_schedule(plan, waves, tasks, limit, contract=None):
    """Expose the executable schedule in the revision-bound approval document."""
    by_id = {task['id']: task for task in tasks}
    lines = ['## Controller-checked development schedule', '',
             f'Agent limit: {limit}. Every task, including a single task, runs in an isolated workspace. '
             'Available slots refill as each validated result integrates; a slow task does not hold up independent work. '
             'The groups below illustrate dependencies, not batch barriers. '
             'Shared foundations and final integration may run alone. Independent QA follows integration.', '',
             '| Dependency group | Scheduled task IDs | Possible concurrent agents |', '|---|---|---|']
    for number, wave in enumerate(waves, 1):
        ids = ', '.join(ident.replace('|', '\\|').replace('\n', ' ') for ident in wave)
        lines.append(f'| {number} | {ids} | {len(wave)} |')
    lines.extend(['', 'Scheduled ownership and dependencies:', ''])
    for wave in waves:
        for ident in wave:
            task = by_id[ident]
            lines.append(f'- {ident}: owns {task["files"]}; depends on {task["depends_on"] or "approved inputs"}.')
    if contract is not None:
        lines.extend(['','## Validated execution contract','','```json',
            json.dumps(dict(policy=POLICY,tasks=tasks,**contract),indent=2),'```'])
    return plan.rstrip() + '\n\n' + '\n'.join(lines) + '\n'
