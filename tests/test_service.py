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
