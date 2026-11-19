"""Blocked work survives recovery without becoming approved or integrated."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from appling import context, planning
from appling.swarm import build_ready
from appling.workflow import Workflow, parse_tasks
from plan_fixtures import plan_result
from test_planning import parallel_tasks
from test_swarm import fixture, write_result


def test_blocked_worker_preserves_results_evidence_and_recovery_context(tmp_path):
    handoff = {}
    def execute(conn, run):
        brief = json.loads(run.prompt)
        if brief['worker']['task_id'] != 'front':
            return write_result(run)
        run.save_session('retained-session')
        (run.root/'front.txt').write_text('retained implementation')
        command = [sys.executable, '-c', 'from pathlib import Path; assert Path("front.txt").read_text()=="retained implementation"']
        result = subprocess.run(command, cwd=run.root, capture_output=True, text=True)
        log = run.root/brief['worker']['evidence']/'check.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(f'command: {command}\nexit: {result.returncode}\n{result.stdout or "(no output)"}')
        handoff.update(status='blocked', summary='Production host route is owned by downstream join',
            checks=[dict(command='check retained source', exit_code=result.returncode, evidence=str(log.relative_to(run.root)))],
            blockers=[dict(kind='integration', detail='Need host route', requires_tasks=['join'])])
        return copy.deepcopy(handoff)
    store, workflow, pid, root = fixture(tmp_path, execute)
    approvals = store.get(pid)['approvals']
    try:
        with pytest.raises(RuntimeError, match='Production host route'):
            build_ready(workflow, pid)
        state = store.get(pid)
        worker = next(w for w in state['workers'] if w['task_id'] == 'front')
        assert worker['status'] == 'blocked' and worker['result'] == handoff
        assert state['tasks'][0]['status'] == 'pending'
        assert not (root/'front.txt').exists() and not (root/'joined.txt').exists()
        assert (root/'back.txt').exists()  # An unrelated worker still integrates.
        assert (Path(worker['workspace'])/'front.txt').read_text() == 'retained implementation'
        assert (Path(worker['workspace'])/handoff['checks'][0]['evidence']).is_file()
    finally:
        workflow.shutdown()

    workflow = Workflow(store, lambda *_: pytest.fail('Reading recovery must not execute workers'))
    try:
        before = store.get(pid)
        for stage in ['proposal', 'review']:
            payload = json.loads(context.briefing(store, pid, 'task-planner' if stage == 'proposal' else 'sw-architect',
                'Repair task boundaries', planning_context=dict(stage=stage)))
            recovered = next(w for w in payload['planning']['recovery'] if w['id'] == worker['id'])
            assert recovered['result'] == handoff
            assert recovered['workspace'] == worker['workspace']
            assert recovered['checkpoint']['outcome'] == handoff
            assert 'tasks' not in payload  # Historical assignments cannot override the candidate.
        assert store.get(pid) == before and before['approvals'] == approvals
    finally:
        workflow.shutdown()


@pytest.mark.parametrize('prerequisite', ['integration', 'unknown', 'ui'])
def test_acceptance_cannot_depend_on_downstream_unknown_or_self_task(tmp_path, prerequisite):
    (tmp_path/'requirements.md').write_text('FR-1: approved behavior')
    candidate = plan_result(parallel_tasks())
    candidate['tasks'][1]['acceptance'][0]['requires_tasks'] = [prerequisite]
    with pytest.raises(ValueError, match='outside its upstream dependencies'):
        planning.validate_contract(candidate, parse_tasks(candidate['tasks']), tmp_path)


def test_early_host_wiring_unlocks_parallel_features_before_final_acceptance(tmp_path):
    (tmp_path/'requirements.md').write_text('FR-1: approved behavior')
    tasks = parallel_tasks()
    tasks.insert(1, dict(id='host', goal='Establish routes', files=['main.py'], depends_on=['contracts']))
    for task in tasks:
        if task['id'] in {'ui', 'api'}:
            task['depends_on'] = ['host']
    candidate = plan_result(tasks)
    # Transitive prerequisites count; every final consumer still follows features.
    candidate['tasks'][-1]['acceptance'][0]['requires_tasks'].append('host')
    parsed = parse_tasks(candidate['tasks'])
    planning.validate_contract(candidate, parsed, tmp_path)
    assert planning.execution_waves(parsed, 3) == [['contracts'], ['host'], ['ui', 'api'], ['integration']]


def test_missing_acceptance_prerequisite_declaration_is_not_assumed_empty(tmp_path):
    (tmp_path/'requirements.md').write_text('FR-1: approved behavior')
    candidate = plan_result(parallel_tasks())
    del candidate['tasks'][1]['acceptance'][0]['requires_tasks']
    with pytest.raises(ValueError, match='Acceptance requires_tasks'):
        planning.validate_contract(candidate, parse_tasks(candidate['tasks']), tmp_path)
