"""The shared start/stop/lock helper. Real processes and real files; Windows-only parsing is checked
with a written npm wrapper because it is plain text handling."""
import os
import subprocess
import sys
import time

import pytest

from appling import procs

posix_only = pytest.mark.skipif(procs.WINDOWS, reason='process groups exist only on Linux and macOS')


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def wait_gone(pid, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and alive(pid):
        time.sleep(.05)
    return not alive(pid)


def started_child(tmp_path, ignore_term=False):
    """A program that starts a grandchild and writes the grandchild's id to a file."""
    note = tmp_path / 'child.pid'
    grandchild = ('import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(300)'
                  if ignore_term else 'import time; time.sleep(300)')
    code = (f'import subprocess,sys,time; p=subprocess.Popen([sys.executable,"-c",{grandchild!r}]); '
            f'open({str(note)!r},"w").write(str(p.pid)); time.sleep(300)')
    proc = procs.spawn([sys.executable, '-c', code])
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not (note.exists() and note.read_text()):
        time.sleep(.05)
    return proc, int(note.read_text())


def test_stop_ends_the_program_and_everything_it_started(tmp_path):
    proc, grandchild = started_child(tmp_path)
    procs.stop(proc, 2)
    assert proc.poll() is not None and wait_gone(grandchild)


@posix_only
def test_a_sweep_also_stops_a_leftover_that_ignores_a_polite_stop_after_its_parent_exited(tmp_path):
    proc, grandchild = started_child(tmp_path, ignore_term=True)
    proc.kill(); proc.wait()                     # the parent is gone; the grandchild stays in its group
    assert alive(grandchild)
    procs.stop(proc, .3)                         # without a sweep an exited program is left alone
    assert alive(grandchild)
    procs.stop(proc, .3, sweep=True)
    assert wait_gone(grandchild)


def test_only_one_holder_of_a_lock_at_a_time(tmp_path):
    path = tmp_path / 'server.lock'
    with path.open('a') as first, path.open('a') as second:
        assert procs.try_lock(first)
        held = subprocess.run([sys.executable, '-c', (
            'import sys; sys.path.insert(0, sys.argv[2]); from appling import procs; '
            'print(procs.try_lock(open(sys.argv[1], "a")))'), str(path), os.getcwd()],
            capture_output=True, text=True)
        assert held.stdout.strip() == 'False'
        procs.unlock(first)
        assert procs.try_lock(second)
        procs.unlock(second)


def test_npm_wrappers_are_started_through_node_so_cmd_never_rereads_the_prompt(tmp_path, monkeypatch):
    shim_dir = tmp_path / 'npm'
    script = shim_dir / 'node_modules' / '@github' / 'copilot' / 'index.js'
    script.parent.mkdir(parents=True); script.write_text('')
    shim = shim_dir / 'copilot.cmd'
    shim.write_text('@ECHO off\r\nGOTO start\r\n:find_dp0\r\nSET dp0=%~dp0\r\nEXIT /b\r\n:start\r\nSETLOCAL\r\nCALL :find_dp0\r\n'
                    'endLocal & goto #_undefined_# 2>NUL || title %COMSPEC% & "%_prog%"  '
                    '"%dp0%\\node_modules\\@github\\copilot\\index.js" %*\r\n')
    node = tmp_path / 'node.exe'; node.write_text('')
    found = {'copilot': str(shim), 'node': str(node), 'codex': str(tmp_path / 'codex.exe')}
    monkeypatch.setattr(procs, 'WINDOWS', True)
    monkeypatch.setattr(procs.shutil, 'which', lambda name: found.get(name))
    prompt = 'Fix "this" & that | 100%'
    resolved = procs.command(['copilot', '-p', prompt])
    assert resolved[0] == str(node) and procs.Path(resolved[1]) == script and resolved[2:] == ['-p', prompt]
    assert procs.command(['codex', 'app-server']) == [str(tmp_path / 'codex.exe'), 'app-server']
    assert procs.command('npm test') == 'npm test'          # shell commands are left to the shell
    assert procs.command(['missing', 'x']) == ['missing', 'x']


def test_windows_setting_names_match_whatever_their_case(monkeypatch):
    source = {'Path': 'C:\\bin', 'NPM_CONFIG_CACHE': 'C:\\cache', 'APPDATA': 'C:\\Users\\a\\AppData', 'SECRET_TOKEN': 'x'}
    monkeypatch.setattr(procs, 'WINDOWS', True)
    picked = procs.pick({'PATH', 'npm_config_cache'}, source)
    assert picked == {'Path': 'C:\\bin', 'NPM_CONFIG_CACHE': 'C:\\cache', 'APPDATA': 'C:\\Users\\a\\AppData'}
    monkeypatch.setattr(procs, 'WINDOWS', False)
    assert procs.pick({'PATH', 'npm_config_cache'}, source) == {}
