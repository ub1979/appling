"""One process-wide budget for executing role leads and their workers."""
from __future__ import annotations

import threading
from contextlib import contextmanager

DEFAULT_WORKERS = 10
MAX_WORKERS = 15


def worker_limit() -> int:
    from lyra_lite.settings import _section
    config = _section().get('parallel_work')
    value = config.get('max_workers', DEFAULT_WORKERS) if isinstance(config, dict) else DEFAULT_WORKERS
    try:
        return min(MAX_WORKERS, max(1, int(value)))
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_WORKERS


class WorkerPool:
    def __init__(self):
        self.condition = threading.Condition()
        self.active = 0
        self.peak = 0

    @contextmanager
    def reserve(self, requested, stopped, *, wait=False):
        count = 0
        with self.condition:
            while not stopped.is_set():
                count = min(requested, max(0, worker_limit() - self.active))
                if count or not wait:
                    break
                self.condition.wait(.2)
            if stopped.is_set():
                count = 0
            self.active += count
            self.peak = max(self.peak, self.active)
        reservation = Reservation(self, count)
        try:
            yield reservation
        finally:
            reservation.release_all()

    def snapshot(self):
        with self.condition:
            return {'active': self.active, 'limit': worker_limit(), 'peak': self.peak}


class Reservation:
    def __init__(self, pool, count):
        self.pool, self.count, self.remaining = pool, count, count

    def release(self):
        with self.pool.condition:
            if self.remaining:
                self.remaining -= 1
                self.pool.active -= 1
                self.pool.condition.notify_all()

    def release_all(self):
        with self.pool.condition:
            self.pool.active -= self.remaining
            self.remaining = 0
            self.pool.condition.notify_all()


WORKERS = WorkerPool()
