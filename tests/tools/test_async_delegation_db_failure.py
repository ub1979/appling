"""Regression: a broken state.db must not leak async slots or lose results.

The capacity slot is claimed in memory before the durable dispatch row is
written. When state.db was corrupted, the write raised, the record stayed
``running`` with no worker behind it, and after ``max_async_children`` such
failures every later ``delegate_task`` was rejected as "at capacity" for the
life of the process (silently forcing all delegations to run synchronously).

These tests use a real unreadable state.db file, not a mocked connection.
"""

import threading

import pytest

from tools import async_delegation as ad
from tools.process_registry import process_registry


@pytest.fixture
def ledger(monkeypatch, tmp_path):
    db = tmp_path / "state.db"
    monkeypatch.setattr(ad, "_db_path", lambda: db)
    ad._reset_for_tests()
    yield db
    ad._reset_for_tests()


def _corrupt(db):
    for suffix in ("", "-wal", "-shm"):
        db.with_name(db.name + suffix).unlink(missing_ok=True)
    db.write_bytes(b"this is not a sqlite database" * 200)


def _dispatch_batch(runner, max_children=3):
    return ad.dispatch_async_delegation_batch(
        goals=["goal"], context=None, toolsets=None, role="leaf", model=None,
        session_key="", runner=runner, max_async_children=max_children,
    )


def _dispatch_single(runner, max_children=3):
    return ad.dispatch_async_delegation(
        goal="goal", context=None, toolsets=None, role="leaf", model=None,
        session_key="", runner=runner, max_async_children=max_children,
    )


@pytest.mark.parametrize("dispatch", [_dispatch_batch, _dispatch_single])
def test_failed_durable_write_releases_slot(ledger, dispatch):
    _corrupt(ledger)

    for _ in range(4):  # more than the cap of 3
        out = dispatch(lambda: {"status": "completed"})
        assert out["status"] == "rejected"
        assert "capacity" not in out["error"]

    assert ad.active_count() == 0

    # Once storage is healthy again, dispatch works: no slot was leaked.
    ledger.unlink()
    release = threading.Event()
    out = dispatch(lambda: (release.wait(5), {"status": "completed", "results": []})[1])
    release.set()
    assert out["status"] == "dispatched"


@pytest.mark.parametrize("dispatch", [_dispatch_batch, _dispatch_single])
def test_failed_completion_write_still_delivers_result(ledger, dispatch):
    while not process_registry.completion_queue.empty():
        process_registry.completion_queue.get_nowait()

    started, release = threading.Event(), threading.Event()

    def runner():
        started.set()
        release.wait(5)
        return {"status": "completed", "summary": "done", "results": []}

    out = dispatch(runner)
    assert out["status"] == "dispatched"
    assert started.wait(5)

    _corrupt(ledger)
    release.set()

    evt = process_registry.completion_queue.get(timeout=5)
    assert evt["delegation_id"] == out["delegation_id"]
    assert evt["status"] == "completed"
    for _ in range(50):
        if ad.active_count() == 0:
            break
        threading.Event().wait(0.05)
    assert ad.active_count() == 0
