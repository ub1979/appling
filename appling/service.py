"""Checkout-local background service lifecycle; stop requests never signal PIDs."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
import webbrowser

ROOT=Path(__file__).resolve().parent.parent
RUN=ROOT/'.appling_c/run'


def prepare(directory):
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)


@contextmanager
def lease(directory=RUN):
    prepare(directory)
    with (directory/'server.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Appling is already running for this checkout.')
        try:yield
        finally:fcntl.flock(lock,fcntl.LOCK_UN)


def live(directory=RUN):
    if not (directory/'server.lock').exists():return False
    with (directory/'server.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return True
        fcntl.flock(lock,fcntl.LOCK_UN)
        return False


def read_state(directory=RUN):
    try:return json.loads((directory/'server.json').read_text())
    except (OSError,ValueError):return {}


def atomic(path,data):
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(data));temporary.chmod(0o600);temporary.replace(path)


def serve_managed(app,listener,port,no_open=False):
    import uvicorn
    with lease():
        instance=uuid.uuid4().hex
        (RUN/'server.json').unlink(missing_ok=True);(RUN/'stop.json').unlink(missing_ok=True)
        url=f'http://127.0.0.1:{port}'
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,fd=listener.fileno(),log_level='info'))
        finished=threading.Event()
        def watch():
            while not finished.wait(.1):
                if server.started:break
            if finished.is_set():return
            atomic(RUN/'server.json',dict(instance=instance,pid=os.getpid(),url=url))
            if not no_open:webbrowser.open(url)
            while not finished.wait(.2):
                try:request=json.loads((RUN/'stop.json').read_text())
                except (OSError,ValueError):continue
                if request.get('instance')==instance:
                    server.should_exit=True;return
        monitor=threading.Thread(target=watch,daemon=True);monitor.start()
        try:server.run()
        finally:
            finished.set();monitor.join(timeout=2)
            (RUN/'server.json').unlink(missing_ok=True);(RUN/'stop.json').unlink(missing_ok=True)


def start(args,*,directory=RUN,command=None,timeout=20):
    prepare(directory)
    # Serialize launchers while the child takes its lifetime lease.
    with (directory/'launch.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if live(directory):
            state=read_state(directory)
            if state.get('url'):
                print(f'Appling is already running: {state["url"]}')
                if '--no-open' not in args:webbrowser.open(state['url'])
                return
            raise RuntimeError('Appling is starting or stopping. Try again shortly.')
        (directory/'server.json').unlink(missing_ok=True)
        log_path=directory/'server.log'
        with log_path.open('ab') as log:
            child=subprocess.Popen(command or [sys.executable,'-m','appling',*args,'--managed'],cwd=ROOT,
                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if child.poll() is not None:raise RuntimeError(f'Appling could not start. See {log_path}')
            state=read_state(directory)
            if state.get('pid')==child.pid and state.get('url') and live(directory):
                print(f'Appling is running: {state["url"]}\nLogs: {log_path}\nStop with ./stop.sh')
                return
            time.sleep(.1)
        raise RuntimeError(f'Appling is still starting. Check ./status.sh or {log_path}')


def stop(*,directory=RUN,timeout=20):
    if not live(directory):
        print('Appling is not running for this checkout.');return
    state=read_state(directory)
    if not state.get('instance'):raise RuntimeError('Appling has not finished starting; try stopping it again shortly.')
    atomic(directory/'stop.json',dict(instance=state['instance']))
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if not live(directory):
            print('Appling stopped.');return
        time.sleep(.1)
    raise RuntimeError(f'Appling is still shutting down its tasks. Check {directory / "server.log"}; no process was force-killed.')


def main():
    parser=argparse.ArgumentParser(description='Manage this Appling checkout')
    parser.add_argument('action',choices=['start','stop','status'])
    parser.add_argument('--quiet',action='store_true')
    args,remaining=parser.parse_known_args()
    try:
        if args.action=='start':
            if '--foreground' in remaining:
                remaining.remove('--foreground')
                os.execv(sys.executable,[sys.executable,'-m','appling',*remaining])
            start(remaining)
        elif args.action=='stop':stop()
        else:
            running=live()
            if not args.quiet:print(f'Appling is running: {read_state().get("url","starting")}' if running else 'Appling is not running.')
            raise SystemExit(0 if running else 1)
    except RuntimeError as exc:
        print(str(exc),file=sys.stderr);raise SystemExit(1)


if __name__=='__main__':main()
