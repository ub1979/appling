"""Exercise the shared budget, nested admission and Stop with real threads."""
import threading
from types import SimpleNamespace

import pytest

from lyra_lite.workers import Stopped, WorkerPool


def test_nested_capacity_is_shared_and_never_waits_while_holding_a_slot(monkeypatch):
    monkeypatch.setattr('lyra_lite.workers.worker_limit', lambda: 10)
    pool, stopped = WorkerPool(), threading.Event()
    with pool.reserve(1, stopped) as lead:
        with lead.use(stopped) as admitted:
            assert admitted
            with pool.reserve(15, stopped) as wave:
                assert wave.count == 9
                assert pool.snapshot()['active'] == 10
                with pool.reserve(1, stopped) as other_project:
                    assert other_project.count == 0
    assert pool.snapshot()['active'] == 0
    assert pool.snapshot()['peak'] == 10


def test_stopped_wave_keeps_running_slots_until_tools_exit(monkeypatch):
    monkeypatch.setattr('lyra_lite.workers.worker_limit', lambda: 15)
    pool, stopped = WorkerPool(), threading.Event()
    started, release = threading.Event(), threading.Event()
    def run(reservation):
        with reservation.use(stopped) as admitted:
            assert admitted
            started.set()
            assert release.wait(5)
    with pool.reserve(15, stopped) as wave:
        thread = threading.Thread(target=run, args=(wave,))
        thread.start()
        assert started.wait(5)
        stopped.set()
    assert pool.snapshot()['active'] == 1
    try:
        with wave.use(threading.Event()) as admitted:
            assert not admitted  # Unstarted workers were cancelled.
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert pool.snapshot()['active'] == 0


def test_queued_role_can_be_stopped_without_running_model(monkeypatch):
    monkeypatch.setattr('lyra_lite.workers.worker_limit', lambda: 1)
    pool, stopped = WorkerPool(), threading.Event()
    entered, finished = threading.Event(), threading.Event()
    counts = []
    def queued():
        entered.set()
        with pool.reserve(1, stopped, wait=True) as job:
            counts.append(job.count)
        finished.set()
    with pool.reserve(1, threading.Event()):
        thread = threading.Thread(target=queued)
        thread.start()
        assert entered.wait(5)
        stopped.set()
        assert finished.wait(5)
        thread.join(5)
        assert counts == [0] and pool.snapshot()['active'] == 1
    assert pool.snapshot()['active'] == 0


def test_interrupt_proxy_observes_parent_and_child():
    parent, child = SimpleNamespace(_interrupt_requested=False), SimpleNamespace(_interrupt_requested=False)
    stopped = Stopped(parent, child)
    assert not stopped.is_set()
    parent._interrupt_requested = True
    assert stopped.is_set()


@pytest.mark.parametrize('raw', [True, 0, 16, 1.5, '15', None])
def test_worker_setting_rejects_invalid_values(raw):
    from lyra_lite.settings import validate_parallel_work
    with pytest.raises(ValueError):
        validate_parallel_work({'max_workers': raw})
