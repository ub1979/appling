"""Real file tools and the real RPC sandbox must agree on file-read delivery."""
import json
import uuid

from tools.code_execution_tool import execute_code
from tools.file_tools import read_file_tool, reset_file_dedup
from tools.terminal_tool import cleanup_vm


def test_script_can_read_a_region_already_seen_in_chat(tmp_path, monkeypatch):
    monkeypatch.setenv('TERMINAL_ENV', 'local')
    monkeypatch.setenv('TERMINAL_CWD', str(tmp_path))
    source = tmp_path / 'plan.md'
    source.write_text('Approved scope\nOne coherent task\n')
    task = f'ptc-read-{uuid.uuid4().hex}'
    try:
        first = json.loads(read_file_tool(str(source), task_id=task))
        assert 'Approved scope' in first['content']
        result = json.loads(execute_code(
            f'from hermes_tools import read_file\nprint(read_file({str(source)!r})["content"])',
            task_id=task, enabled_tools=['read_file']))
        assert result['status'] == 'success', result
        assert 'Approved scope' in result['output']
    finally:
        reset_file_dedup(task)
        cleanup_vm(task)


def test_repeated_script_reads_do_not_consume_chat_delivery(tmp_path, monkeypatch):
    monkeypatch.setenv('TERMINAL_ENV', 'local')
    monkeypatch.setenv('TERMINAL_CWD', str(tmp_path))
    source = tmp_path / 'task-graph.md'
    source.write_text('Independent work\n')
    task = f'ptc-repeat-{uuid.uuid4().hex}'
    try:
        result = json.loads(execute_code(
            f'from hermes_tools import read_file\nfor _ in range(6):\n print(read_file({str(source)!r})["content"])',
            task_id=task, enabled_tools=['read_file']))
        assert result['status'] == 'success', result
        assert result['output'].count('Independent work') == 6
        first_chat = json.loads(read_file_tool(str(source), task_id=task))
        assert 'Independent work' in first_chat['content']
        cached_chat = json.loads(read_file_tool(str(source), task_id=task))
        assert cached_chat['dedup'] and not cached_chat['content_returned']
    finally:
        reset_file_dedup(task)
        cleanup_vm(task)


def test_script_reads_preserve_chat_loop_guards_and_observe_edits(tmp_path, monkeypatch):
    monkeypatch.setenv('TERMINAL_ENV', 'local')
    monkeypatch.setenv('TERMINAL_CWD', str(tmp_path))
    source = tmp_path / 'plan.md'
    source.write_text('First revision\n')
    task = f'ptc-fresh-{uuid.uuid4().hex}'
    code = f'from hermes_tools import read_file\nprint(read_file({str(source)!r})["content"])'
    try:
        assert 'content' in json.loads(read_file_tool(str(source), task_id=task))
        assert json.loads(read_file_tool(str(source), task_id=task))['dedup']
        result = json.loads(execute_code(code, task_id=task, enabled_tools=['read_file']))
        assert result['status'] == 'success' and 'First revision' in result['output']
        assert 'BLOCKED' in json.loads(read_file_tool(str(source), task_id=task))['error']
        source.write_text('Changed revision\n')
        result = json.loads(execute_code(code, task_id=task, enabled_tools=['read_file']))
        assert result['status'] == 'success' and 'Changed revision' in result['output']
        assert 'Changed revision' in json.loads(read_file_tool(str(source), task_id=task))['content']
    finally:
        reset_file_dedup(task)
        cleanup_vm(task)


def test_programmatic_scope_preserves_path_guards_and_resets_on_error():
    from tools.file_tools import programmatic_file_reads, _programmatic_read
    assert not _programmatic_read.get()
    try:
        with programmatic_file_reads():
            blocked = json.loads(read_file_tool('/dev/zero', task_id='ptc-device-guard'))
            assert 'device' in blocked['error']
            raise ValueError('script failed')
    except ValueError:
        pass
    assert not _programmatic_read.get()


def test_file_rpc_transport_returns_contents_after_chat_read(tmp_path, monkeypatch):
    """Exercise the remote transport with a real local filesystem as its backend."""
    import os
    import subprocess
    import sys
    import threading

    from tools.code_execution_tool import _rpc_poll_loop, generate_hermes_tools_module
    from tools.environments.local import LocalEnvironment

    monkeypatch.setenv('TERMINAL_ENV', 'local')
    monkeypatch.setenv('TERMINAL_CWD', str(tmp_path))
    source = tmp_path / 'plan.md'
    source.write_text('File RPC contents\n')
    task = f'ptc-file-rpc-{uuid.uuid4().hex}'
    rpc = tmp_path / 'rpc'
    rpc.mkdir()
    (tmp_path / 'hermes_tools.py').write_text(generate_hermes_tools_module(['read_file'], transport='file'))
    stop = threading.Event()
    worker = threading.Thread(target=_rpc_poll_loop, args=(
        LocalEnvironment(cwd=str(tmp_path), timeout=10), str(rpc), task, [], [0], 10,
        frozenset({'read_file'}), stop, 'test-rpc-token'), daemon=True)
    try:
        assert 'content' in json.loads(read_file_tool(str(source), task_id=task))
        worker.start()
        run = subprocess.run([sys.executable, '-c',
            f'from hermes_tools import read_file\nprint(read_file({str(source)!r})["content"])'],
            cwd=tmp_path, env={**os.environ, 'HERMES_RPC_DIR': str(rpc), 'HERMES_RPC_TOKEN': 'test-rpc-token'},
            capture_output=True, text=True, timeout=15)
        assert run.returncode == 0, run.stderr
        assert 'File RPC contents' in run.stdout
    finally:
        stop.set()
        if worker.ident is not None:
            worker.join(10)
        reset_file_dedup(task)
        cleanup_vm(task)
    assert not worker.is_alive()


def test_programmatic_scope_keeps_credential_files_blocked():
    import os
    from pathlib import Path
    from tools.file_tools import programmatic_file_reads

    home = Path(os.environ['HERMES_HOME'])
    home.mkdir(parents=True, exist_ok=True)
    credentials = home / 'auth.json'
    credentials.write_text('{"test_only_secret":"must-not-return"}')
    with programmatic_file_reads():
        result = json.loads(read_file_tool(str(credentials), task_id='ptc-protected-read'))
    assert 'error' in result and 'content' not in result
    assert 'must-not-return' not in json.dumps(result)


def test_script_read_scope_does_not_leak_to_concurrent_chat(tmp_path, monkeypatch):
    import threading
    from tools.file_tools import programmatic_file_reads

    monkeypatch.setenv('TERMINAL_ENV', 'local')
    monkeypatch.setenv('TERMINAL_CWD', str(tmp_path))
    source = tmp_path / 'shared.md'
    source.write_text('Current file\n')
    task = f'ptc-thread-{uuid.uuid4().hex}'
    entered, release = threading.Event(), threading.Event()
    results = []
    def script():
        with programmatic_file_reads():
            results.append(json.loads(read_file_tool(str(source), task_id=task)))
            entered.set()
            release.wait(5)
    worker = threading.Thread(target=script)
    try:
        assert 'content' in json.loads(read_file_tool(str(source), task_id=task))
        worker.start()
        assert entered.wait(5)
        assert 'Current file' in results[0]['content']
        chat = json.loads(read_file_tool(str(source), task_id=task))
        assert chat['dedup'] and not chat['content_returned']
    finally:
        release.set()
        if worker.ident is not None:
            worker.join(5)
        reset_file_dedup(task)
        cleanup_vm(task)
    assert not worker.is_alive()
