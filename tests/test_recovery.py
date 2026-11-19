import subprocess
import sys
import time

import pytest

from appling import recovery, service
from appling.store import Store


@pytest.fixture
def stuck(tmp_path):
    directory=tmp_path/'.appling_c/run'
    store=Store(tmp_path/'.appling_c/studio.db')
    project=store.add(tmp_path/'project')
    code='''
import os,sys,time
from pathlib import Path
from appling.service import lease,atomic
d=Path(sys.argv[1])
with lease(d):
 atomic(d/'server.json',dict(pid=os.getpid(),instance='legacy',url='http://127.0.0.1:12345'))
 atomic(d/'stop.json',dict(instance='legacy'))
 while True:time.sleep(.1)
'''
    child=subprocess.Popen([sys.executable,'-c',code,str(directory)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    deadline=time.monotonic()+5
    while not service.stopping(directory):
        assert child.poll() is None and time.monotonic()<deadline
        time.sleep(.01)
    yield tmp_path,directory,store,project,child
    if child.poll() is None:child.terminate()
    child.wait(timeout=5)


def test_recovery_interrupts_verified_idle_stopping_process_and_preserves_ledger(stuck):
    root,directory,store,project,child=stuck
    before=store.get(project['id']);inspected=[]
    def inspect(pid,checkout):
        assert pid==child.pid and checkout==root
        inspected.append(pid)
    assert recovery.recover(root,inspector=inspect,timeout=5)
    child.wait(timeout=5)
    assert inspected==[child.pid] and child.returncode!=0
    assert not service.live(directory) and store.get(project['id'])==before


@pytest.mark.parametrize('reason',['active','wrong_process','changed_instance','not_stopping'])
def test_recovery_refuses_unverified_or_active_process_without_signalling(stuck,reason):
    root,directory,store,project,child=stuck
    if reason=='active':store.update(project['id'],running=True)
    if reason=='not_stopping':service.atomic(directory/'stop.json',dict(instance='different'))
    def inspect(pid,checkout):
        if reason=='wrong_process':raise RuntimeError('process belongs to another checkout')
        if reason=='changed_instance':service.atomic(directory/'server.json',dict(pid=pid,instance='new'))
    with pytest.raises(RuntimeError):recovery.recover(root,inspector=inspect,timeout=.1)
    assert child.poll() is None and service.live(directory)
