"""Programs a force-quit Appling left running are stopped by the next start, and nothing else is ever signalled.

Every test uses real processes and a temporary ledger folder."""
import json
import os
import signal
import subprocess
import sys
import time

import pytest

from appling import children

SERVER = '''
import os, subprocess, sys, time
from appling import children
children.enable(sys.argv[1])
pids = []
for command in sys.argv[2:]:
    proc = subprocess.Popen(command, shell=True, start_new_session=True, stdin=subprocess.DEVNULL, env=dict(os.environ))
    children.track(proc); pids.append(proc.pid)
print(*pids, flush=True)
time.sleep(600)
'''
PY = sys.executable


def alive(pid):
    return bool(children.started(pid))


def wait_gone(pids, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and any(alive(p) for p in pids):
        time.sleep(.05)
    return [p for p in pids if alive(p)]


@pytest.fixture
def server(tmp_path):
    """Start a stand-in Appling server that records the commands it starts; everything is cleaned up afterwards."""
    started = []

    def launch(*commands):
        proc = subprocess.Popen([PY, '-c', SERVER, str(tmp_path / 'ledger'), *commands], stdout=subprocess.PIPE, text=True)
        pids = [int(p) for p in proc.stdout.readline().split()]
        started.append((proc, pids))
        return proc, pids

    yield launch
    for proc, pids in started:
        for pid in pids:
            try:
                os.killpg(pid, signal.SIGKILL)       # these groups were created by this test alone
            except (ProcessLookupError, PermissionError):
                pass
        if proc.poll() is None:
            proc.kill()
        proc.wait()


def crash(proc):
    proc.kill(); proc.wait()


def test_programs_left_by_a_force_quit_server_are_stopped_at_the_next_start(tmp_path, server):
    ledger = tmp_path / 'ledger'
    ignores_term = f"{PY} -c \"import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(300)\""
    proc, pids = server('sleep 300', ignores_term)
    assert len(list(ledger.glob('*.json'))) == 2
    crash(proc)
    time.sleep(.3)
    assert all(alive(p) for p in pids)                      # a force-quit server cannot stop them: this is the leftover
    stopped, unverified = children.reap(ledger, grace=.5)
    assert set(pids) <= set(stopped) and unverified == []
    assert wait_gone(pids) == []                            # the one ignoring a polite stop was killed after the wait
    assert list(ledger.glob('*.json')) == []


def test_a_running_servers_programs_are_never_touched(tmp_path, server):
    ledger = tmp_path / 'ledger'
    proc, pids = server('sleep 300')
    sent = []
    assert children.reap(ledger, send=lambda pid, sig: sent.append(pid)) == ([], [])
    assert sent == [] and alive(pids[0]) and len(list(ledger.glob('*.json'))) == 1


def test_a_reused_process_id_is_never_signalled(tmp_path):
    """After a crash the recorded id can belong to anything, for example the owner's own Codex."""
    ledger = tmp_path / 'ledger'; ledger.mkdir()
    bystander = subprocess.Popen(['sleep', '300'], start_new_session=True)
    try:
        dead_owner = dict(pid=bystander.pid, started='Mon Jan  1 00:00:00 2001')
        (ledger / f'{bystander.pid}.json').write_text(json.dumps(dict(
            pid=bystander.pid, started='Mon Jan  1 00:00:00 2001', owner=dead_owner, marker='abc')))
        (ledger / 'broken.json').write_text('{not json')
        sent = []
        assert children.reap(ledger, send=lambda pid, sig: sent.append(pid)) == ([], [])
        assert sent == [] and bystander.poll() is None
        assert list(ledger.glob('*.json')) == []            # the stale entries are dropped without a signal
    finally:
        bystander.kill(); bystander.wait()


def test_only_a_process_leading_its_own_group_is_recorded(tmp_path):
    """Signalling the group of a process that shares Appling's own group would stop Appling itself."""
    ledger = tmp_path / 'ledger'
    shares_our_group = subprocess.Popen(['sleep', '300'])
    leader = subprocess.Popen(['sleep', '300'], start_new_session=True)
    try:
        children.track(leader)
        assert not ledger.exists()                          # recording is off until a server turns it on
        children.enable(ledger)
        children.track(shares_our_group)
        assert list(ledger.glob('*.json')) == []
        children.track(leader)
        entry = json.loads((ledger / f'{leader.pid}.json').read_text())
        assert entry['owner']['pid'] == os.getpid() and entry['started'] == children.started(leader.pid)
        children.forget(leader)
        assert list(ledger.glob('*.json')) == []
    finally:
        children.disable()
        for proc in (shares_our_group, leader):
            proc.kill(); proc.wait()


def test_after_the_leader_exits_only_processes_carrying_the_marker_are_stopped(tmp_path, server):
    """A leaderless group cannot be proven ours by its id, so each member must prove itself."""
    ledger = tmp_path / 'ledger'; note = tmp_path / 'pids'
    leader = (f"{PY} -c \"import subprocess,sys; a=subprocess.Popen([sys.executable,'-c','import time;time.sleep(300)']); "
              f"b=subprocess.Popen(['sleep','300'], env={{'PATH':'/bin:/usr/bin'}}); open(sys.argv[1],'w').write(f'{{a.pid}} {{b.pid}}')\" {note}")
    proc, pids = server(leader)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not (note.exists() and len(note.read_text().split()) == 2):
        time.sleep(.05)
    carries, stripped = [int(p) for p in note.read_text().split()]
    try:
        crash(proc)                                         # only now can the finished leader fully go away
        assert wait_gone([pids[0]]) == [] and alive(carries) and alive(stripped)
        stopped, unverified = children.reap(ledger, grace=.5)
        assert stopped == [carries] and unverified == [stripped]
        assert wait_gone([carries]) == [] and alive(stripped)    # no proof, no signal
        assert list(ledger.glob('*.json')) == []
    finally:
        for pid in (carries, stripped):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_a_failed_cleanup_never_stops_the_server_from_starting(tmp_path, monkeypatch):
    lines = []
    monkeypatch.setattr(children, 'reap', lambda directory: (_ for _ in ()).throw(OSError('disk problem')))
    children.start(tmp_path / 'ledger', log=lines.append)
    try:
        assert lines == ['Leftover cleanup was skipped: disk problem']
        assert children.DIRECTORY == tmp_path / 'ledger'      # this server's own programs are still recorded
    finally:
        children.disable()


def test_ai_programs_and_test_commands_are_recorded_while_they_run_and_cleared_when_they_end(tmp_path):
    """The ledger is only useful if the real spawn sites write to it, and only safe if they clear it."""
    import textwrap
    from appling import blocks
    from appling.engines import Run
    from appling.engines.cli import execute as cli_execute
    ledger = tmp_path / 'ledger'; seen = tmp_path / 'seen.json'
    fake = tmp_path / 'fake-engine'
    fake.write_text('#!' + PY + '\n' + textwrap.dedent(f'''
        import json, os
        json.dump(dict(pid=os.getpid(), marker=os.environ.get('APPLING_RUN'), ledger=os.listdir({str(ledger)!r})), open({str(seen)!r}, 'w'))
        print(json.dumps({{'type': 'result', 'result': json.dumps({{'summary': 'Built', 'status': 'completed'}})}}), flush=True)
    '''))
    fake.chmod(0o755)
    children.enable(ledger)
    try:
        result = cli_execute({'engine': 'claude-cli', 'binary': str(fake)}, Run(tmp_path, 'instructions', 'task', readonly=True))
        assert result['status'] == 'completed'
        during = json.loads(seen.read_text())
        assert during['ledger'] == [f"{during['pid']}.json"] and during['marker'] == children.MARKER
        assert list(ledger.glob('*')) == []
        blocks._run(f'ls {ledger}', tmp_path, tmp_path / 'test.log')
        assert '.json' in (tmp_path / 'test.log').read_text() and list(ledger.glob('*')) == []
    finally:
        children.disable()
