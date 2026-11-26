"""Start, stop and lock the same way on Linux, macOS and Windows.

Every helper program Appling starts (AI programs, test commands, previews) must be stoppable together
with everything it started in turn.

Linux and macOS: the program gets its own session, so its process group belongs to it alone. Stopping
sends SIGTERM to the group, then SIGKILL after a grace period.

Windows: there are no process groups to signal. Each program is placed in its own job object that ends
every process in it when the job is closed. Stopping terminates the job. If Appling itself is force-quit,
Windows closes the job and the programs stop with it, so no leftover ledger is needed there.
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path

WINDOWS = os.name == 'nt'

if WINDOWS:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    _kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    class _IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            'ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
            'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]

    class _BasicLimits(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                    ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                    ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                    ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = [('BasicLimitInformation', _BasicLimits), ('IoInfo', _IoCounters),
                    ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                    ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]

    _EXTENDED_LIMIT_INFORMATION = 9
    _KILL_ON_JOB_CLOSE = 0x2000
else:
    import fcntl


# ----- finding the program -------------------------------------------------------------------------

_NPM_SHIM_TARGET = re.compile(r'"%dp0%\\([^"]+)"\s+%\*')


def command(args):
    """The argument list to start. On Windows a bare program name is resolved through PATH and PATHEXT,
    because the system only finds .exe files by itself. Programs installed by npm are .cmd wrappers; they
    are started as `node <script>` instead, so the prompt is never re-read by cmd.exe, which would break
    quotes, ampersands and long text."""
    if not WINDOWS or isinstance(args, (str, bytes)):
        return args
    args = [str(a) for a in args]
    found = shutil.which(args[0])
    if not found:
        return args
    if found.lower().endswith(('.cmd', '.bat')):
        script = _npm_script(Path(found))
        if script:
            local_node = Path(found).parent / 'node.exe'
            node = str(local_node) if local_node.exists() else shutil.which('node')
            if node:
                return [node, str(script), *args[1:]]
    return [found, *args[1:]]


def _npm_script(shim):
    try:
        text = shim.read_text(errors='replace')
    except OSError:
        return None
    matches = _NPM_SHIM_TARGET.findall(text)
    if not matches:
        return None
    script = shim.parent.joinpath(*matches[-1].split('\\'))
    return script if script.is_file() else None


# ----- environment ---------------------------------------------------------------------------------

# Windows programs cannot find the user's profile, sign-ins, temp folder or even the network stack without these.
WINDOWS_SYSTEM = {'SYSTEMROOT', 'SYSTEMDRIVE', 'WINDIR', 'COMSPEC', 'PATHEXT', 'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH',
                  'APPDATA', 'LOCALAPPDATA', 'PROGRAMDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)', 'PROGRAMW6432',
                  'COMMONPROGRAMFILES', 'COMMONPROGRAMFILES(X86)', 'USERNAME', 'USERDOMAIN', 'COMPUTERNAME',
                  'NUMBER_OF_PROCESSORS', 'PROCESSOR_ARCHITECTURE', 'OS', 'PYTHONUTF8'}


def pick(names, source=None):
    """The variables from `source` (default os.environ) whose names are listed. Windows names ignore case."""
    source = os.environ if source is None else source
    if not WINDOWS:
        return {k: v for k, v in source.items() if k in names}
    wanted = {n.upper() for n in names} | WINDOWS_SYSTEM
    return {k: v for k, v in source.items() if k.upper() in wanted}


# ----- starting and stopping -----------------------------------------------------------------------

def spawn(args, **kwargs):
    """subprocess.Popen for a helper program that must be stoppable with everything it starts."""
    if not WINDOWS:
        return subprocess.Popen(args, start_new_session=True, **kwargs)
    flags = kwargs.pop('creationflags', 0)
    # CREATE_NO_WINDOW: a console program never opens a window on the owner's screen.
    flags |= subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    proc = subprocess.Popen(command(args), creationflags=flags, **kwargs)
    proc._appling_job = _job(proc)
    return proc


def _job(proc):
    """A job that holds this program and, automatically, everything it starts. None if Windows refused."""
    job = _kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    limits = _ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = _KILL_ON_JOB_CLOSE
    if (_kernel32.SetInformationJobObject(job, _EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits), ctypes.sizeof(limits))
            and _kernel32.AssignProcessToJobObject(job, int(proc._handle))):
        return job
    _kernel32.CloseHandle(job)
    return None


def _signal_group(proc, sig):
    try:
        os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError):
        if proc.poll() is None:
            proc.terminate() if sig == signal.SIGTERM else proc.kill()


def stop(proc, grace=3.0, *, sweep=False):
    """Stop a program started by spawn() and everything it started.

    Linux and macOS: SIGTERM to its process group, SIGKILL if it is still running after `grace` seconds.
    With sweep, the group is signalled even when the program itself already exited, so tools it left
    behind (for example one that ignores SIGTERM) are stopped too.

    Windows: the job is terminated, which ends every process in it at once. Windows has no polite stop
    for a program without a window, so there is no grace period.
    """
    if WINDOWS:
        job = getattr(proc, '_appling_job', None)
        if job:
            _kernel32.TerminateJobObject(job, 1)
            _kernel32.CloseHandle(job)
            proc._appling_job = None
        elif proc.poll() is None:
            subprocess.run(['taskkill', '/T', '/F', '/PID', str(proc.pid)], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        return
    if proc.poll() is None or sweep:
        _signal_group(proc, signal.SIGTERM)
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            pass
        if proc.poll() is None or sweep:
            _signal_group(proc, signal.SIGKILL)
    proc.wait()


def detached(args, **kwargs):
    """Start a program that must keep running after the program that started it exits (the server)."""
    if not WINDOWS:
        return subprocess.Popen(args, start_new_session=True, **kwargs)
    # A hidden console of its own, not none at all: console programs it starts later (git, npm) share
    # that hidden console instead of each opening a window on the owner's screen.
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        # A terminal can hold its programs in a job that ends them when the window closes; leave it.
        return subprocess.Popen(args, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kwargs)
    except OSError:
        return subprocess.Popen(args, creationflags=flags, **kwargs)


# ----- file locks ----------------------------------------------------------------------------------

def try_lock(handle):
    """Take an exclusive lock on an open file without waiting. False when another process holds it."""
    if not WINDOWS:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return True
    except OSError:
        return False


def lock(handle):
    """Take an exclusive lock on an open file, waiting as long as it takes."""
    if not WINDOWS:
        fcntl.flock(handle, fcntl.LOCK_EX)
        return
    while not try_lock(handle):     # Windows' own blocking lock gives up after about ten seconds
        time.sleep(.1)


def unlock(handle):
    if not WINDOWS:
        fcntl.flock(handle, fcntl.LOCK_UN)
        return
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass


def replace(source, target, attempts=50):
    """Path.replace that waits briefly when Windows reports the target open in another process."""
    for attempt in range(attempts):
        try:
            return Path(source).replace(target)
        except PermissionError:
            if not WINDOWS or attempt == attempts - 1:
                raise
            time.sleep(.05)
