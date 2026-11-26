"""Explicit recovery for an idle, already-stopping legacy managed server."""
from __future__ import annotations

import os
from pathlib import Path
import shlex
import signal
import sqlite3
import json
import subprocess
import time

from . import service


def inspect_process(pid, root):
    command=subprocess.run(['/bin/ps','-ww','-p',str(pid),'-o','command='],capture_output=True,text=True,check=True)
    args=shlex.split(command.stdout.strip())
    if (not args or not Path(args[0]).name.lower().startswith('python') or '--managed' not in args
            or not any(args[i:i+2]==['-m','appling'] for i in range(len(args)-1))):
        raise RuntimeError('Recovery refused: the recorded process is not a managed Appling server.')
    cwd=subprocess.run(['/usr/sbin/lsof','-a','-p',str(pid),'-d','cwd','-Fn'],
                       capture_output=True,text=True,check=True)
    paths=[Path(line[1:]).resolve() for line in cwd.stdout.splitlines() if line.startswith('n')]
    if paths!=[Path(root).resolve()]:
        raise RuntimeError('Recovery refused: the process belongs to a different checkout.')


def recover(root=service.ROOT, *, timeout=10, inspector=inspect_process):
    root=Path(root).resolve();directory=root/'.appling_c/run'
    if not service.live(directory):
        return False
    state=service.read_state(directory);pid=state.get('pid')
    if type(pid) is not int or pid<=1 or not service.stopping(directory):
        raise RuntimeError('Recovery is only for a managed server that already received a stop request.')
    db=root/'.appling_c/studio.db/studio.sqlite'
    # Recovery must not skip cleanup for active model work. Never edit its ledger.
    with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as connection:
        if any(json.loads(row[0]).get('running') for row in connection.execute('SELECT state FROM projects')):
            raise RuntimeError('Recovery refused: project work is still running. Wait for its checkpoint first.')
    inspector(pid,root)
    if not service.live(directory):return False
    if service.read_state(directory)!=state or not service.stopping(directory):
        raise RuntimeError('Recovery refused: the server instance changed during verification.')
    # The legacy Uvicorn instance is already exiting. SIGINT releases its stuck
    # connection drain; this is not SIGKILL and does not delete any state files.
    os.kill(pid,signal.SIGINT)
    deadline=time.monotonic()+timeout
    while service.live(directory):
        if time.monotonic()>=deadline:
            raise RuntimeError('The verified server did not exit after interruption; no further signal was sent.')
        time.sleep(.1)
    return True


def main():
    if os.name == 'nt':
        print('Recovery uses Linux and macOS process tools. On Windows, end the old server in Task Manager, then run start.bat.')
        raise SystemExit(1)
    try:
        changed=recover()
        print('Recovered the stopped Appling server.' if changed else 'No stuck Appling server remains.')
        subprocess.run([str(service.ROOT/'start.sh')],cwd=service.ROOT,check=True)
    except (OSError,RuntimeError,sqlite3.Error,subprocess.SubprocessError) as exc:
        print('Recovery could not complete: '+str(exc))
        raise SystemExit(1)


if __name__=='__main__':main()
