"""A ledger of the process groups this server started.

A server that is force-quit cannot stop its AI programs, test commands and previews: they run in their
own sessions and keep going. Each start reads the ledger and stops what a dead server left behind.

A signal is sent only on positive proof. A process counts as ours when its process id AND its start
time match what was recorded, or, for a group whose leader has gone, when it visibly carries this
ledger entry's marker in its environment. Anything else is left alone and reported.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid

DIRECTORY = None    # tracking is off until a server entry point calls enable()
OWNER = None
MARKER = None
ENV = 'APPLING_RUN'


def _ps(*args):
    """The output of ps, '' when it found nothing, or None when the lookup itself failed.
    A failed lookup is never read as "that process is gone": it proves nothing, so nothing is signalled."""
    try:
        done = subprocess.run(['ps', *args], capture_output=True, text=True, timeout=10, env={**os.environ, 'LC_ALL': 'C'})
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode == 0:
        return done.stdout
    return '' if done.returncode == 1 and not done.stdout.strip() else None     # 1 with no rows: no such process


def started(pid):
    """The start time of a live process, '' when it is gone, None when that could not be found out.
    With the id, the start time names one process."""
    found = _ps('-o', 'lstart=', '-p', str(int(pid)))
    return None if found is None else ' '.join(found.split())


def table():
    """Every process as {pid: (process group, start time)}, or None when the listing failed."""
    listing = _ps('-ax', '-o', 'pid=,pgid=,lstart=')
    if listing is None:
        return None
    found = {}
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) > 2 and parts[0].isdigit() and parts[1].isdigit():
            found[int(parts[0])] = (int(parts[1]), ' '.join(parts[2:]))
    return found


def marked(pid, marker):
    """True only when this process's environment visibly carries the marker. The system hides the
    environment of some programs (on macOS, the built-in ones); those are never treated as ours."""
    if not marker:
        return False
    needle = f'{ENV}={marker}'
    try:
        return needle.encode() in Path(f'/proc/{int(pid)}/environ').read_bytes().split(b'\0')
    except OSError:
        pass
    plain = (_ps('-ww', '-o', 'command=', '-p', str(int(pid))) or '').rstrip('\n')
    full = (_ps('-E', '-ww', '-o', 'command=', '-p', str(int(pid))) or '').rstrip('\n')
    # Only the part after the command line is environment; the same text in an argument proves nothing.
    return bool(plain) and full.startswith(plain) and needle in full[len(plain):].split()


def enable(directory):
    """Start recording. Children inherit the marker through the environment."""
    global DIRECTORY, OWNER, MARKER
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    begun = started(os.getpid())
    if not begun:       # without it nobody could tell this server from a dead one, so nothing is recorded
        raise OSError('this process could not read its own start time')
    MARKER = uuid.uuid4().hex
    OWNER = dict(pid=os.getpid(), started=begun)
    os.environ[ENV] = MARKER
    DIRECTORY = directory


def disable():
    global DIRECTORY, OWNER, MARKER
    DIRECTORY = OWNER = MARKER = None
    os.environ.pop(ENV, None)


def track(proc):
    """Record a process that leads its own group. Never raises: recording must not break a task."""
    if DIRECTORY is None:
        return
    try:
        pid = proc.pid
        if os.getpgid(pid) != pid:      # its group is somebody else's, so the group must never be signalled
            return
        begun = started(pid)
        if not begun:
            return
        path = DIRECTORY / f'{pid}.json'
        temporary = path.with_name(f'{pid}.{uuid.uuid4().hex}.tmp')
        temporary.write_text(json.dumps(dict(pid=pid, started=begun, owner=OWNER, marker=MARKER)))
        temporary.replace(path)
    except (OSError, ValueError):
        pass


def forget(proc):
    if DIRECTORY is None:
        return
    try:
        (DIRECTORY / f'{proc.pid}.json').unlink(missing_ok=True)
    except OSError:
        pass


def _send(targets, sig, send):
    """Signal each process that is still the one we verified."""
    for pid, begun in targets:
        if started(pid) == begun:
            try:
                send(pid, sig)
            except (ProcessLookupError, PermissionError):
                pass


def reap(directory, *, send=os.kill, grace=3):
    """Stop what dead servers left behind. Returns (stopped, unverified) process ids.

    Entries of a server that is still running are not touched, so two servers never stop each other's work.
    """
    directory = Path(directory)
    stopped, unverified = [], []
    if not directory.is_dir():
        return stopped, unverified
    for stale in directory.glob('*.tmp'):
        try:
            if time.time() - stale.stat().st_mtime > 60:      # a fresh one may be another server's write in progress
                stale.unlink(missing_ok=True)
        except OSError:
            pass
    for path in sorted(directory.glob('*.json')):
        try:
            entry = json.loads(path.read_text())
            pid = int(entry['pid']); begun = entry['started']
            owner = entry['owner']; owner_pid = int(owner['pid']); owner_started = owner['started']
            marker = str(entry.get('marker') or '')
        except (OSError, ValueError, TypeError, KeyError):
            path.unlink(missing_ok=True)
            continue
        if pid <= 1 or not (isinstance(begun, str) and begun) or not (isinstance(owner_started, str) and owner_started):
            path.unlink(missing_ok=True)
            continue
        owner_now = started(owner_pid)
        if owner_now is None or owner_now == owner_started:
            continue                                   # alive, or unknown: that server looks after its own children
        processes = table()
        if processes is None:
            continue                                   # could not look, so nothing is proven; try again next start
        members = [(member, info[1]) for member, info in processes.items() if info[0] == pid]
        if processes.get(pid) == (pid, begun):
            targets = members                          # the recorded leader itself: its whole group is ours
        elif pid in processes:
            targets = []; members = []                 # the id was reused by an unrelated program: hands off
        else:
            targets = [m for m in members if marked(m[0], marker)]
            unverified += [m[0] for m in members if m not in targets]
        if targets:
            _send(targets, signal.SIGTERM, send)
            deadline = time.monotonic() + grace
            while time.monotonic() < deadline and any(started(p) == b for p, b in targets):
                time.sleep(.1)
            _send(targets, signal.SIGKILL, send)
            stopped += [p for p, _ in targets]
        path.unlink(missing_ok=True)
    return stopped, unverified


def start(directory, log=print):
    """Called once by a server entry point before it accepts work. Never raises."""
    if os.name == 'nt':
        return      # Windows ends a force-quit server's programs itself: each one runs in a job (see procs.py)
    try:
        stopped, unverified = reap(directory)
        if stopped:
            log(f'Appling stopped {len(stopped)} program(s) left running by an earlier Appling that ended unexpectedly: {stopped}')
        if unverified:
            log(f'Appling left {len(unverified)} program(s) running because it could not prove they were its own: {unverified}')
    except Exception as exc:      # cleanup is a convenience; the server must still start
        log(f'Leftover cleanup was skipped: {exc}')
    try:
        enable(directory)
    except OSError as exc:
        log(f'Appling cannot record the programs it starts: {exc}')
