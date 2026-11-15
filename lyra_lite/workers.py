"""Shared, Stop-aware execution budget for Appling's Hermes role leads and leaves."""
from __future__ import annotations

import threading
from contextlib import contextmanager

DEFAULT_WORKERS = 10
MAX_WORKERS = 15


def worker_limit() -> int:
    from lyra_lite.settings import _section
    cfg = _section().get("parallel_work")
    raw = cfg.get("max_workers", DEFAULT_WORKERS) if isinstance(cfg, dict) else DEFAULT_WORKERS
    try:
        return min(MAX_WORKERS, max(1, int(raw)))
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_WORKERS


class Stopped:
    def __init__(self, *agents):
        self.agents = agents

    def is_set(self):
        return any(getattr(a, "_interrupt_requested", False) is True for a in self.agents)


class WorkerPool:
    def __init__(self):
        self.condition = threading.Condition()
        self.active = 0
        self.peak = 0

    @contextmanager
    def reserve(self, requested, stopped, *, wait=False, on_wait=None):
        notified = False
        with self.condition:
            while not stopped.is_set():
                count = min(requested, max(0, worker_limit() - self.active))
                if count or not wait:
                    break
                if on_wait is not None and not notified:
                    on_wait()
                    notified = True
                self.condition.wait(.2)
            else:
                count = 0
            self.active += count
            self.peak = max(self.peak, self.active)
        reservation = Reservation(self, count)
        try:
            yield reservation
        finally:
            # Claimed slots belong to their executing threads until they exit,
            # even when Stop lets the parent return before a tool has unwound.
            reservation.release_unclaimed()

    def snapshot(self):
        with self.condition:
            return {"active": self.active, "limit": worker_limit(), "peak": self.peak}


class Reservation:
    def __init__(self, pool, count):
        self.pool, self.count, self.unclaimed = pool, count, count

    @contextmanager
    def use(self, stopped):
        with self.pool.condition:
            admitted = self.unclaimed > 0 and not stopped.is_set()
            if admitted:
                self.unclaimed -= 1
        try:
            yield admitted
        finally:
            if admitted:
                with self.pool.condition:
                    self.pool.active -= 1
                    self.pool.condition.notify_all()

    def release_unclaimed(self):
        with self.pool.condition:
            self.pool.active -= self.unclaimed
            self.unclaimed = 0
            self.pool.condition.notify_all()


WORKERS = WorkerPool()
