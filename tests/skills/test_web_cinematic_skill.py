"""web-cinematic's site check catches the bugs a static read misses.

Runs the real checker in a real browser against two tiny pages. Skips when
node, an offline copy of playwright-core in the npm cache, or a browser is
missing — it never downloads anything.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = (Path(__file__).resolve().parents[2] / "plugins" / "ultimate-builder" / "skills"
          / "ultimate-app-builder" / "references" / "workflows" / "web-cinematic" / "scripts"
          / "site-check.mjs")

BROKEN = """<!doctype html><html><head><meta name="viewport" content="width=device-width"></head>
<body style="margin:0;font:20px sans-serif">
<section style="height:100vh;background:#223;color:#fff">Hero</section>
<section style="height:100vh;display:flex;align-items:center">
  <p style="opacity:.1">This sentence should fade in on scroll but never does.</p></section>
<section style="height:100vh"><div style="width:2200px;height:300px;background:#a55"></div></section>
</body></html>"""

CLEAN = """<!doctype html><html><head><meta name="viewport" content="width=device-width"></head>
<body style="margin:0;font:20px sans-serif">
<section style="height:100vh;background:#223;color:#fff">Hero</section>
<section style="height:100vh;display:flex;align-items:center"><p>Readable all the way.</p></section>
<section style="height:100vh;overflow:hidden"><div style="width:2200px;height:300px;background:#5a5"></div></section>
</body></html>"""


@pytest.fixture
def checker_env(tmp_path):
    if not shutil.which("node") or not shutil.which("npm"):
        pytest.skip("node is not installed")
    cache = tmp_path / "hermes" / "cache" / "site-check"
    cache.mkdir(parents=True)
    (cache / "package.json").write_text('{"name":"t","private":true}')
    offline = subprocess.run(["npm", "i", "--offline", "--no-audit", "--no-fund", "playwright-core@1"],
                             cwd=cache, capture_output=True, text=True, timeout=120)
    if offline.returncode != 0:
        pytest.skip("playwright-core is not in the local npm cache")
    return {**os.environ, "HERMES_HOME": str(tmp_path / "hermes")}


def _check(env, page: Path, out: Path) -> tuple[int, dict]:
    run = subprocess.run(["node", str(SCRIPT), str(page), "--out", str(out), "--steps", "5"],
                         env=env, capture_output=True, text=True, timeout=240)
    if run.returncode == 3:
        pytest.skip("no browser available")
    return run.returncode, json.loads((out / "report.json").read_text())


def test_site_check_flags_overflow_and_unrevealed_text(checker_env, tmp_path):
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "index.html").write_text(BROKEN)
    code, report = _check(checker_env, broken, tmp_path / "out-broken")
    text = "\n".join(report["findings"])
    assert code == 1
    assert "scrolls sideways" in text
    assert "never became readable" in text and "never does" in text
    assert "reduced motion" in text
    assert all(Path(s).is_file() for s in report["sheets"])


def test_site_check_passes_a_clean_page(checker_env, tmp_path):
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "index.html").write_text(CLEAN)
    code, report = _check(checker_env, clean, tmp_path / "out-clean")
    assert (code, report["findings"]) == (0, [])
