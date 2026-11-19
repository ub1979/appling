import sys
import time
import pytest
from appling import service


WORKER='''
import sys,time,json,os
from pathlib import Path
from appling.service import lease,atomic
directory=Path(sys.argv[1])
with lease(directory):
    atomic(directory/'server.json',dict(instance='test-instance',pid=os.getpid(),url='http://127.0.0.1:12345'))
    while True:
        try:request=json.loads((directory/'stop.json').read_text())
        except (OSError,ValueError):request={}
        if request.get('instance')=='test-instance':break
        time.sleep(.05)
    (directory/'server.json').unlink(missing_ok=True)
'''


def test_background_start_returns_reuses_instance_and_stops_only_own_checkout(tmp_path):
    directory=tmp_path/'run';other=tmp_path/'other'
    try:
        service.start(['--no-open'],directory=directory,command=[sys.executable,'-c',WORKER,str(directory)],timeout=5)
        assert service.live(directory)
        original=service.read_state(directory)
        service.start(['--no-open'],directory=directory,command=['must-not-be-executed'],timeout=1)
        assert service.read_state(directory)==original
        service.stop(directory=other,timeout=1)
        assert service.live(directory)
        service.stop(directory=directory,timeout=5)
        assert not service.live(directory)
    finally:
        if service.live(directory):service.stop(directory=directory,timeout=5)


def test_stale_pid_never_causes_a_process_signal(tmp_path,monkeypatch):
    directory=tmp_path/'run';service.prepare(directory)
    service.atomic(directory/'server.json',dict(instance='stale',pid=1,url='http://127.0.0.1:1'))
    def fail(*args):raise AssertionError('No process should be signalled')
    monkeypatch.setattr('os.kill',fail)
    service.stop(directory=directory,timeout=.1)
    assert not service.live(directory)


def test_failed_background_start_reports_log_without_waiting_full_timeout(tmp_path):
    started=time.monotonic()
    with pytest.raises(RuntimeError,match='could not start'):
        service.start(['--no-open'],directory=tmp_path/'run',command=[sys.executable,'-c','raise SystemExit(7)'],timeout=10)
    assert time.monotonic()-started<5


def test_start_waits_for_stopping_instance_and_replaces_it(tmp_path):
    directory=tmp_path/'run'
    slow=WORKER.replace("if request.get('instance')=='test-instance':break",
                        "if request.get('instance')=='test-instance':time.sleep(.4);break")
    try:
        service.start(['--no-open'],directory=directory,command=[sys.executable,'-c',slow,str(directory)],timeout=5)
        old=service.read_state(directory)
        service.atomic(directory/'stop.json',dict(instance=old['instance']))
        assert service.stopping(directory)
        # Replacement fixture must ignore the old instance's stop request.
        replacement=WORKER.replace('test-instance','replacement-instance')
        service.start(['--no-open'],directory=directory,command=[sys.executable,'-c',replacement,str(directory)],timeout=5)
        assert service.read_state(directory)['instance']=='replacement-instance'
        assert service.read_state(directory)['pid']!=old['pid']
        assert not service.stopping(directory)
    finally:
        if service.live(directory):service.stop(directory=directory,timeout=5)


def test_uvicorn_shutdown_cancels_open_event_stream_and_runs_lifespan_cleanup(tmp_path,monkeypatch):
    # Exercise real Uvicorn shutdown with an indefinitely pending stream task.
    # No network listener is needed, including in restricted execution hosts.
    import asyncio
    import uvicorn
    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    from types import SimpleNamespace
    cleaned=[];cancelled=[]
    @asynccontextmanager
    async def lifespan(app):
        yield
        cleaned.append(True)
    async def exercise(server):
        server.servers=[]  # Deliberately no listening sockets in this regression.
        server.config.load()
        server.lifespan=server.config.lifespan_class(server.config)
        await server.lifespan.startup()
        async def stream():
            try:await asyncio.Event().wait()
            finally:cancelled.append(True)
        task=asyncio.create_task(stream());server.server_state.tasks.add(task)
        task.add_done_callback(server.server_state.tasks.discard)
        await asyncio.sleep(0)
        await asyncio.wait_for(server.shutdown(),timeout=5)
        await asyncio.gather(task,return_exceptions=True)
    class StreamServer(uvicorn.Server):
        def run(self):asyncio.run(exercise(self))
    directory=tmp_path/'run'
    original_lease=service.lease
    monkeypatch.setattr(service,'RUN',directory)
    monkeypatch.setattr(service,'lease',lambda:original_lease(directory))
    monkeypatch.setattr(uvicorn,'Server',StreamServer)
    service.serve_managed(FastAPI(lifespan=lifespan),SimpleNamespace(fileno=lambda:-1),0,no_open=True)
    assert cleaned==[True] and cancelled==[True]
