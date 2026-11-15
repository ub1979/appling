"""Stop only the selected checkout; never adopt an unrelated port owner."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest


@pytest.fixture
def launcher(tmp_path):
    if not shutil.which('lsof'):
        pytest.skip('lsof required for launcher process checks')
    spec = importlib.util.spec_from_file_location('appling_launch', Path(__file__).resolve().parents[2] / 'scripts/appling-launch.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.BASE = tmp_path / 'Appling with spaces'
    module.BASE.mkdir()
    return module


def test_stop_scripts_preserve_the_other_engine(launcher):
    children = []
    for root, relative, port in [
        (launcher.BASE, '.venv/bin/python', 9200),
        (launcher.BASE / '.worktrees/appling-codex-base', 'apps/appling-runtime/.venv/bin/python', 9201),
    ]:
        python = root / relative
        python.parent.mkdir(parents=True)
        python.symlink_to(sys.executable)
        (root / 'lyra_lite.py').write_text('import time\ntime.sleep(60)\n')
        children.append(subprocess.Popen([str(python), '-m', 'lyra_lite', '--port', str(port)], cwd=root))
    try:
        time.sleep(.2)
        assert launcher.main('hermes', 'stop') == 0
        assert children[0].wait(5) != 0
        assert children[1].poll() is None
        assert launcher.main('codex', 'stop') == 0
        assert children[1].wait(5) != 0
        assert launcher.main('codex', 'stop') == 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
            child.wait(5)


def test_start_refuses_an_unrelated_listener(launcher, monkeypatch):
    class Result:
        returncode = 0
        stdout = '999999\n'
    monkeypatch.setattr(launcher.subprocess, 'check_output', lambda *a, **k: '')
    monkeypatch.setattr(launcher.subprocess, 'run', lambda *a, **k: Result())
    with pytest.raises(RuntimeError, match='belongs to another process'):
        launcher.main('hermes', 'start')
