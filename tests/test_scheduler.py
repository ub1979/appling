"""Exercise rolling scheduling against real isolated project files."""
import json
import threading
from pathlib import Path
import pytest

from appling import swarm
from appling.swarm import build_ready
from appling.workflow import Workflow, parse_tasks
from test_swarm import fixture, write_result


def background_build(workflow, pid):
    errors = []
    def build():
        try:
            build_ready(workflow, pid)
        except BaseException as exc:
            errors.append(exc)
    thread = threading.Thread(target=build)
    thread.start()
    return thread, errors


@pytest.mark.parametrize('depends_on', [[], ['back']])
def test_free_slot_integrates_and_starts_next_task_while_slow_worker_runs(tmp_path, depends_on):
    slow_started = threading.Event()
    release_slow = threading.Event()
    follower_started = threading.Event()
    running = set()
    peak = []
    lock = threading.Lock()
    def execute(conn, run):
        task = json.loads(run.prompt)['worker']['task_id']
        with lock:
            running.add(task)
            peak.append(len(running))
        try:
            if task == 'front':
                slow_started.set()
                assert release_slow.wait(8), 'Test did not release the slow worker'
            elif task == 'back':
                assert slow_started.wait(5)
            else:
                # Both the source snapshot and durable state must include the
                # finished prerequisite before this worker can start.
                assert (run.root/'back.txt').read_text() == 'done'
                state = store.get(pid)
                assert state['tasks'][1]['status'] == 'done'
                assert state['tasks'][0]['status'] == 'running'
                assert not release_slow.is_set()
                follower_started.set()
            return write_result(run)
        finally:
            with lock:
                running.remove(task)
    store, w, pid, root = fixture(tmp_path, execute)
    settings = w.settings()
    settings['parallel_work']['agents_per_project'] = 2
    store.save_setting('ai', settings)
    tasks = store.get(pid)['tasks']
    tasks[2]['depends_on'] = depends_on
    store.update(pid, tasks=tasks)
    approvals = store.get(pid)['approvals']
    thread, errors = background_build(w, pid)
    try:
        assert follower_started.wait(6), errors
        assert (root/'back.txt').read_text() == 'done'
        assert not (root/'front.txt').exists()
    finally:
        release_slow.set()
        thread.join(8)
        w.shutdown()
    assert not thread.is_alive() and not errors
    assert max(peak) == 2
    state = store.get(pid)
    assert all(t['status'] == 'done' for t in state['tasks'])
    assert all(w['status'] == 'integrated' for w in state['workers'])
    assert state['approvals'] == approvals


def test_refill_skips_ownership_conflicts_without_wasting_free_slot(tmp_path):
    release_slow = threading.Event()
    independent_started = threading.Event()
    overlap_started = threading.Event()
    def execute(conn, run):
        task = json.loads(run.prompt)['worker']['task_id']
        if task == 'front':
            assert release_slow.wait(8)
            name, text = 'shared/source.txt', 'foundation'
        elif task == 'overlap':
            assert release_slow.is_set()
            assert (run.root/'shared/source.txt').read_text() == 'foundation'
            assert store.get(pid)['tasks'][0]['status'] == 'done'
            overlap_started.set()
            name, text = 'shared/source.txt', 'extended'
        else:
            if task == 'independent':independent_started.set()
            name, text = task+'.txt', 'done'
        path = run.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        brief = json.loads(run.prompt)
        log = run.root/brief['worker']['evidence']/'check.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text('Fixture checked '+name)
        return dict(status='completed', checks=[dict(command='check '+name, exit_code=0,
                    evidence=str(log.relative_to(run.root)))])
    store, w, pid, root = fixture(tmp_path, execute)
    settings = w.settings()
    settings['parallel_work']['agents_per_project'] = 2
    store.save_setting('ai', settings)
    store.update(pid, tasks=parse_tasks([
        dict(id='front', goal='foundation', files=['shared/']),
        dict(id='back', goal='independent backend', files=['back.txt']),
        dict(id='overlap', goal='extend foundation', files=['shared/source.txt']),
        dict(id='independent', goal='other independent work', files=['independent.txt']),
    ]))
    thread, errors = background_build(w, pid)
    try:
        assert independent_started.wait(6), errors
        assert not overlap_started.is_set()
    finally:
        release_slow.set()
        thread.join(8)
        w.shutdown()
    assert not thread.is_alive() and not errors
    assert overlap_started.is_set()
    assert (root/'shared/source.txt').read_text() == 'extended'


def test_failed_branch_does_not_retry_or_block_unrelated_dependents(tmp_path):
    calls = []
    def execute(conn, run):
        task = json.loads(run.prompt)['worker']['task_id']
        calls.append(task)
        if task == 'front':raise RuntimeError('Actual worker blocker')
        assert task != 'blocked-child'
        if task == 'join':assert (run.root/'back.txt').read_text() == 'done'
        return write_result(run)
    store, w, pid, root = fixture(tmp_path, execute)
    tasks = store.get(pid)['tasks']
    tasks[2]['depends_on'] = ['back']
    tasks.append(dict(id='blocked-child', goal='needs failed work', depends_on=['front'],
                      files=['child.txt'], role='sw-developer', status='pending'))
    store.update(pid, tasks=tasks)
    try:
        with pytest.raises(RuntimeError, match='Actual worker blocker'):
            build_ready(w, pid)
        assert sorted(calls) == ['back', 'front', 'join']
        assert [t['status'] for t in store.get(pid)['tasks']] == ['pending', 'done', 'done', 'pending']
        assert (root/'joined.txt').exists() and not (root/'front.txt').exists()
    finally:
        w.shutdown()


def test_failed_setup_does_not_hide_other_ready_tasks(tmp_path):
    calls = []
    def execute(conn, run):
        calls.append(json.loads(run.prompt)['worker']['task_id'])
        return write_result(run)
    store, w, pid, root = fixture(tmp_path, execute)
    tasks = store.get(pid)['tasks']
    tasks[0]['files'] = []
    tasks[2]['depends_on'] = ['back']
    store.update(pid, tasks=tasks)
    try:
        with pytest.raises(RuntimeError, match='Task ownership is missing'):
            build_ready(w, pid)
        assert calls == ['back', 'join']
        assert (root/'back.txt').exists() and (root/'joined.txt').exists()
        assert store.get(pid)['tasks'][0]['status'] == 'pending'
    finally:
        w.shutdown()


@pytest.mark.parametrize('boundary', ['dispatch', 'integration'])
def test_stop_at_controller_boundary_cannot_start_or_apply_more_work(tmp_path, monkeypatch, boundary):
    calls = []
    def execute(conn, run):
        calls.append(json.loads(run.prompt)['worker']['task_id'])
        run.save_session('saved-before-stop')
        return write_result(run)
    store, w, pid, root = fixture(tmp_path, execute)
    store.update(pid, tasks=store.get(pid)['tasks'][:1], running=True)
    helper = 'prepare_worker' if boundary == 'dispatch' else 'integrate_worker'
    original = getattr(swarm, helper)
    def stop_at_boundary(*args, **kwargs):
        if boundary == 'dispatch':
            prepared = original(*args, **kwargs)
            w.stop(pid)
            return prepared
        w.stop(pid)
        return original(*args, **kwargs)
    monkeypatch.setattr(swarm, helper, stop_at_boundary)
    try:
        with pytest.raises(InterruptedError):
            build_ready(w, pid)
        assert calls == ([] if boundary == 'dispatch' else ['front'])
        assert not (root/'front.txt').exists()
        state = store.get(pid)
        assert state['tasks'][0]['status'] == 'pending'
        assert state['workers'][0]['status'] == ('interrupted' if boundary == 'dispatch' else 'completed')
    finally:
        w.shutdown()
    monkeypatch.setattr(swarm, helper, original)
    def resume(conn, run):
        assert boundary == 'dispatch', 'A verified result must integrate without model execution'
        return write_result(run)
    w2 = Workflow(store, resume)
    w2.cancelled[pid] = threading.Event()
    try:
        assert build_ready(w2, pid)
        assert (root/'front.txt').read_text() == 'done'
        assert store.get(pid)['workers'][0]['workspace'] == state['workers'][0]['workspace']
    finally:
        w2.shutdown()


@pytest.mark.parametrize('new_limit', [1, 3])
def test_refill_honors_changed_capacity(tmp_path, monkeypatch, new_limit):
    release = threading.Event()
    front_started = threading.Event()
    fast_integrated = threading.Event()
    followers_started = threading.Barrier(3)
    started = set()
    def execute(conn, run):
        task = json.loads(run.prompt)['worker']['task_id']
        started.add(task)
        run.save_session('session-'+task)
        if task == 'back':
            assert front_started.wait(5)
            settings = w.settings()
            settings['parallel_work']['agents_per_project'] = new_limit
            store.save_setting('ai', settings)
        elif task == 'front':
            front_started.set()
            assert release.wait(8)
        return write_result(run)
    store, w, pid, root = fixture(tmp_path, execute)
    settings = w.settings()
    settings['parallel_work']['agents_per_project'] = 2
    store.save_setting('ai', settings)
    tasks = store.get(pid)['tasks'][:2]
    # These read-only tasks add only their private receipt, never shared source.
    tasks.extend([dict(id='follower-'+str(n), goal='verify completed backend',
                 kind='verification', role='qa-engineer', files=['tests/'+str(n)+'/'], depends_on=['back'])
                 for n in range(2)])
    store.update(pid, tasks=parse_tasks(tasks))
    # Keep the fixture's development writer for the first two tasks; verify
    # followers against the newly integrated backend without changing source.
    original_execute = execute
    def check(conn, run):
        task = json.loads(run.prompt)['worker']['task_id']
        if not task.startswith('follower-'):
            return original_execute(conn, run)
        started.add(task)
        assert (run.root/'back.txt').read_text() == 'done'
        if new_limit == 3:
            followers_started.wait(timeout=6)
            assert release.wait(8)
        else:
            assert release.is_set()
        log = run.root/json.loads(run.prompt)['worker']['evidence']/'check.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text('Backend snapshot verified')
        return dict(status='completed', verdict='pass', checks=[dict(command='verify backend',
                    exit_code=0, evidence=str(log.relative_to(run.root)))])
    w.execute = check
    original = swarm.integrate_worker
    def integrate(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[2]['id'] == 'back':fast_integrated.set()
        return result
    monkeypatch.setattr(swarm, 'integrate_worker', integrate)
    thread, errors = background_build(w, pid)
    try:
        assert fast_integrated.wait(6), errors
        if new_limit == 3:
            followers_started.wait(timeout=6)
        else:
            assert started == {'front', 'back'}
    finally:
        release.set()
        thread.join(8)
        w.shutdown()
    assert not thread.is_alive() and not errors
    assert all(t['status'] == 'done' for t in store.get(pid)['tasks'])
    assert (root/'front.txt').read_text() == 'done'


def test_restart_before_worker_dispatch_reuses_prepared_workspace(tmp_path):
    store, w, pid, root = fixture(tmp_path, lambda c, r: pytest.fail('Unexpected model call'))
    store.update(pid, tasks=store.get(pid)['tasks'][:1], running=True)
    state = store.get(pid)
    worker, _ = swarm.prepare_worker(w, pid, state, state['tasks'][0], '')
    prepared = Path(worker['workspace'])
    (prepared/'front.txt').write_text('retained initial work')
    w.shutdown()
    def resume(conn, run):
        assert run.root == prepared and (run.root/'front.txt').read_text() == 'retained initial work'
        return write_result(run)
    w2 = Workflow(store, resume)
    w2.cancelled[pid] = threading.Event()
    try:
        assert build_ready(w2, pid)
        assert len(store.get(pid)['workers']) == 1
        assert (root/'front.txt').read_text() == 'done'
    finally:
        w2.shutdown()


def test_stop_during_refill_preserves_integrated_work_and_resumes_active_sessions(tmp_path):
    follower_started = threading.Event()
    def execute(conn, run):
        task = json.loads(run.prompt)['worker']['task_id']
        run.save_session('retained-'+task)
        if task == 'back':return write_result(run)
        if task == 'join':follower_started.set()
        assert run.cancel.wait(8)
        raise InterruptedError('Stopped active lane')
    store, w, pid, root = fixture(tmp_path, execute)
    tasks = store.get(pid)['tasks']
    tasks[2]['depends_on'] = ['back']
    tasks.append(dict(id='later', goal='after follower', depends_on=['join'], files=['later.txt'],
                      role='sw-developer', status='pending'))
    settings = w.settings()
    settings['parallel_work']['agents_per_project'] = 2
    store.save_setting('ai', settings)
    store.update(pid, tasks=tasks, running=True)
    thread, errors = background_build(w, pid)
    try:
        assert follower_started.wait(6), errors
    finally:
        w.stop(pid)
        thread.join(8)
        w.shutdown()
    assert not thread.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], InterruptedError)
    state = store.get(pid)
    assert [t['status'] for t in state['tasks']] == ['pending', 'done', 'pending', 'pending']
    old = {worker['task_id']: worker['workspace'] for worker in state['workers']}
    assert 'later' not in old
    resumed = []
    def resume(conn, run):
        task = json.loads(run.prompt)['worker']['task_id']
        resumed.append(task)
        assert task != 'back', 'Integrated work must not execute again'
        if task in old:
            assert str(run.root) == old[task] and run.session == 'retained-'+task
        else:
            assert task == 'later' and run.session is None
            assert (run.root/'joined.txt').read_text() == 'done'
            (run.root/'later.txt').write_text('done')
            log = run.root/json.loads(run.prompt)['worker']['evidence']/'check.log'
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text('Fixture checked later.txt')
            return dict(status='completed', checks=[dict(command='check later.txt', exit_code=0,
                        evidence=str(log.relative_to(run.root)))])
        return write_result(run)
    w2 = Workflow(store, resume)
    w2.cancelled[pid] = threading.Event()
    try:
        assert build_ready(w2, pid)
        assert set(resumed) == {'front', 'join', 'later'}
        assert all(t['status'] == 'done' for t in store.get(pid)['tasks'])
        assert (root/'back.txt').read_text() == 'done'
    finally:
        w2.shutdown()
