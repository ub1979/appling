"""Real native protocol peers and Git worktrees exercise the shared worker budget."""
import json
import threading
from pathlib import Path

import pytest

from lyra_lite import review, settings
from lyra_lite.development import git
from lyra_lite.engines.codex import CodexEngine
from lyra_lite.engines.codex_jobs import dispatch
from lyra_lite.engines.worker_pool import WORKERS, WorkerPool
from tests.lyra_lite.test_codex_engine import engine, Hooks, records


@pytest.fixture
def project(engine):
    root = engine.store.root
    git(root, 'init')
    (root / 'contract.txt').write_text('Frozen source contract\n')
    (root / 'requirements.md').write_text('# Requirements\nPreserve user data.\n')
    (root / 'plan.md').write_text('# Plan\nIndependent changes, combined gate.\n')
    git(root, 'add', 'contract.txt', 'requirements.md', 'plan.md');git(root, 'commit', '-m', 'Approved baseline')
    revision = review.requirements_revision(root)
    engine.store.update_state(team=['sw-developer', 'qa-engineer', 'researcher', 'code-reviewer', 'ui-designer'],
                              requirements_approved=revision, plan_requirements=revision,
                              plan_approved=review.implementation_plan(root)['revision'])
    engine._hooks = Hooks()
    assert WORKERS.snapshot()['active'] == 0
    yield engine
    assert WORKERS.snapshot()['active'] == 0


def barrier(project, monkeypatch, count):
    directory = project.store.root.parent / 'barrier'
    monkeypatch.setenv('FAKE_CODEX_BARRIER', str(directory))
    monkeypatch.setenv('FAKE_CODEX_EXPECTED', str(count))


@pytest.mark.parametrize('limit', [10, 15])
def test_full_shared_capacity_runs_read_only_qa_on_fixed_baseline(project, monkeypatch, limit):
    settings.save_section({'parallel_work': {'max_workers': limit}})
    barrier(project, monkeypatch, limit)
    base = git(project.store.root, 'rev-parse', 'HEAD')
    response = json.loads(dispatch(project, {'parallel': True, 'workers': limit,
        'reason': 'Independent QA journeys against one committed version; no source changes.',
        'tasks': [{'agent': 'qa-engineer', 'goal': f'Check journey {i}', 'read_only': True} for i in range(limit)]}))
    assert 'error' not in response, response
    assert response['baseline'] == base and git(project.store.root, 'rev-parse', 'HEAD') == base
    assert git(project.store.root, 'status', '--porcelain') == ''
    calls = [r for r in records(project) if r.get('method') == 'thread/start']
    assert len(calls) == limit
    assert all(c['params']['sandbox'] == 'read-only' for c in calls)
    assert all('delegate_task' not in [t['name'] for t in c['params']['dynamicTools']] for c in calls)
    events, _ = project.store.read_events(0)
    wave = next(e for e in events if e['type'] == 'worker_wave_end')
    assert wave['peak_workers'] == limit
    assert any(m.get('kind') == 'status' and f'using {limit} workers' in m['content'] for m in project.store.transcript())


def test_ten_coding_workers_integrate_only_owned_files(project, monkeypatch):
    barrier(project, monkeypatch, 10)
    response = json.loads(dispatch(project, {'parallel': True, 'workers': 10,
        'reason': 'Ten independent source files with a frozen interface; integration checked together.',
        'tasks': [{'agent': 'sw-developer', 'goal': f'write part{i}.txt', 'owned_paths': [f'part{i}.txt']} for i in range(10)]}))
    assert 'error' not in response, response
    assert all((project.store.root / f'part{i}.txt').exists() for i in range(10))
    assert git(project.store.root, 'status', '--porcelain') == ''
    assert 'combined validation' in response['integration']


def test_role_lead_counts_toward_shared_limit_and_queues_excess_tasks(project, monkeypatch):
    project.role = 'qa-engineer'
    barrier(project, monkeypatch, 9)
    with WORKERS.reserve(1, project._stopped) as lead:
        assert lead.count == 1
        result = json.loads(dispatch(project, {'workers': 15, 'reason': 'Independent QA cases; lead combines reports.',
            'tasks': [{'goal': f'Check {i}', 'read_only': True} for i in range(15)]}))
        assert 'error' not in result, result
        events, _ = project.store.read_events(0)
        plan = next(e for e in events if e['type'] == 'worker_plan')
        assert plan['requested'] == 15 and plan['chosen'] == 9
        assert plan['pool']['active'] == 10
        assert len(result['results']) == 15
        assert WORKERS.snapshot()['active'] == 1


def test_full_pool_returns_to_lead_without_nested_deadlock(project):
    project.role = 'researcher'
    with WORKERS.reserve(10, project._stopped):
        result = json.loads(dispatch(project, {'goal': 'Research one point', 'read_only': True}))
        assert 'No shared worker slots' in result['error']
        assert project.helpers() == []


def test_read_only_worker_mutation_is_rejected_and_preserved(project):
    base = git(project.store.root, 'rev-parse', 'HEAD')
    result = json.loads(dispatch(project, {'parallel': True, 'reason': 'Read-only verification', 'tasks': [
        {'agent': 'qa-engineer', 'goal': 'write contract.txt', 'read_only': True}]}))
    assert 'read-only worker modified' in result['error']
    assert git(project.store.root, 'rev-parse', 'HEAD') == base
    assert (project.store.root / 'contract.txt').read_text() == 'Frozen source contract\n'
    assert (Path(result['recovery']) / 'worker-0/contract.txt').read_text().startswith('written')


def test_all_selected_roles_can_analyse_in_parallel_and_requirements_cannot_interview(project):
    roles = ['researcher', 'code-reviewer', 'ui-designer', 'task-planner', 'req-engineer']
    result = json.loads(dispatch(project, {'parallel': True, 'workers': 5,
        'reason': 'Independent read-only investigations; lead keeps final decisions.',
        'tasks': [{'agent': role, 'goal': f'Analyse {role}', 'read_only': True} for role in roles]}))
    assert 'error' not in result, result
    worker = CodexEngine(workspace=str(project.store.root), session_key='leaf', store=project.store,
                         role='researcher', worker=True, command=project.command)
    assert 'Leaf workers' in pytest.raises(ValueError, dispatch, worker, {'goal': 'more'}).value.args[0]
    assert 'Return this question' in worker._call_tool('clarify', {'question': 'Approve?'})
    worker.close()


def test_unsafe_or_unexplained_batches_do_not_start_workers(project):
    with pytest.raises(ValueError, match='Explain why'):
        dispatch(project, {'parallel': True, 'tasks': [
            {'agent': 'researcher', 'goal': 'A', 'read_only': True}, {'agent': 'researcher', 'goal': 'B', 'read_only': True}]})
    result = json.loads(dispatch(project, {'parallel': True, 'reason': 'Attempt overlapping writes', 'tasks': [
        {'agent': 'sw-developer', 'goal': 'A', 'owned_paths': ['src/']},
        {'agent': 'sw-developer', 'goal': 'B', 'owned_paths': ['src/a.py']}]}))
    assert 'overlapping' in result['error']
    assert project.helpers() == []
    assert not any(e['type'] == 'worker_plan' for e in project.store.read_events(0)[0])


def test_stop_cancels_all_running_workers_and_leaves_primary_unchanged(project):
    result = []
    task = threading.Thread(target=lambda: result.append(json.loads(dispatch(project, {
        'parallel': True, 'workers': 5, 'reason': 'Independent read-only tasks to test cancellation.',
        'tasks': [{'agent': 'qa-engineer', 'goal': 'wait', 'read_only': True} for _ in range(5)]}))))
    task.start()
    import time
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and len(project.helpers()) != 5:
        time.sleep(.02)
    assert len(project.helpers()) == 5
    project.interrupt()
    task.join(15)
    assert not task.is_alive()
    assert 'did not finish' in result[0]['error']
    assert project.helpers() == []
    assert git(project.store.root, 'status', '--porcelain') == ''


def test_reservations_across_projects_never_exceed_budget_and_release_on_error():
    pool = WorkerPool()
    stop = threading.Event()
    with pool.reserve(8, stop) as first:
        with pool.reserve(8, stop) as second:
            assert first.count + second.count == 10
            first.release()
            with pool.reserve(2, stop) as third:
                assert third.count == 1
                assert pool.snapshot()['active'] == 10
    assert pool.snapshot()['active'] == 0
    with pytest.raises(RuntimeError):
        with pool.reserve(10, stop):
            raise RuntimeError('failed job')
    assert pool.snapshot()['active'] == 0


def test_stop_reaches_other_children_while_one_is_slow(project):
    slow_started, fast_reached, release = threading.Event(), threading.Event(), threading.Event()
    class Slow:
        def interrupt(self):
            slow_started.set()
            release.wait(10)
    class Fast:
        def interrupt(self):
            fast_reached.set()
    project._children = {'slow': Slow(), 'fast': Fast()}
    task = threading.Thread(target=project.stop_helpers)
    task.start()
    try:
        assert slow_started.wait(5)
        assert fast_reached.wait(5)
    finally:
        release.set();task.join(5)
        project._children = {}


def test_single_read_only_assignment_uses_snapshot_even_without_parallel_flag(project):
    result = json.loads(dispatch(project, {'agent': 'qa-engineer', 'goal': 'Inspect one journey', 'read_only': True}))
    assert 'error' not in result, result
    start = next(r for r in records(project) if r.get('method') == 'thread/start')
    assert start['params']['sandbox'] == 'read-only'
    assert Path(start['cwd']) != project.store.root


def test_checks_on_changed_primary_are_rejected_without_losing_worker_report(project, monkeypatch):
    def worker(parent, task, **kwargs):
        (parent.store.root / 'contract.txt').write_text('Owner changed source during QA\n')
        return {'status': 'completed', 'exit_reason': 'completed', 'summary': 'Findings for the old baseline', 'usage': {'input': 100}}
    monkeypatch.setattr('lyra_lite.engines.codex_jobs._run', worker)
    result = json.loads(dispatch(project, {'agent': 'qa-engineer', 'goal': 'Inspect', 'read_only': True}))
    assert 'only to the saved baseline' in result['error']
    assert result['results'][0]['summary'] == 'Findings for the old baseline'
    assert (project.store.root / 'contract.txt').read_text() == 'Owner changed source during QA\n'


def test_mixed_reading_and_writing_wave_requires_checks_after_integration(project):
    result = json.loads(dispatch(project, {'parallel': True, 'reason': 'Independent source work and baseline inspection',
        'tasks': [{'agent': 'sw-developer', 'goal': 'write new.txt', 'owned_paths': ['new.txt']},
                  {'agent': 'code-reviewer', 'goal': 'Inspect previous baseline', 'read_only': True}]}))
    assert 'error' not in result, result
    assert result['checks_require_rerun'] is True
