"""CLI browser capability at the edge: no additional model tool schemas."""
from __future__ import annotations

import hashlib
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from lyra_lite.store import _atomic_write_json


class BrowserTools:
    def __init__(self, engine):
        self.node = shutil.which('node')
        self.wrapper = Path(__file__).resolve().parents[2] / 'apps/appling-browser/browser.cjs'
        self.available = bool(self.node and self.wrapper.is_file() and (self.wrapper.parent / 'node_modules/@playwright/cli/playwright-cli.js').is_file())
        self.used = False
        self.env = {}
        self.instructions = ''
        if not self.available:
            self.instructions = '\nBrowser QA: the optional Appling Playwright package is not installed. Report unavailable browser checks; do not claim they passed.'
            return
        directory = engine._session.get('browser_directory')
        if not directory or not Path(directory).is_dir():
            directory = tempfile.mkdtemp(prefix='appling-browser-')
            engine._save(browser_directory=directory)
        root = Path(directory)
        config = root / 'config.json'
        _atomic_write_json(config, {'browser': {'browserName': 'chromium', 'launchOptions': {'headless': True}},
                                   'outputDir': str(root / 'artifacts')})
        self.env = {'APPLING_BROWSER_CACHE': str(root / 'cache'),
                    'APPLING_BROWSER_OUTPUT': str(root / 'artifacts'),
                    'APPLING_BROWSER_SESSION': hashlib.sha256(engine.session_key.encode()).hexdigest()[:16],
                    'APPLING_BROWSER_CONFIG': str(config)}
        command = shlex.join([self.node, str(self.wrapper)])
        self.instructions = (f'\nBrowser QA: use the bundled official Playwright CLI via `{command} --help`, '
                             f'`{command} open <url>`, then snapshot/click/press/resize/reload/run-code/screenshot. '
                             'It has a private headless Chromium session; no desktop CUA/native pipe is needed. '
                             'For run-code use `async page => { /* await page... */ }` (the argument is page, not {page}). '
                             'Use this path instead of cua.getState or the desktop browser bridge. '
                             'Keep screenshots/evidence in its configured artifact directory, not unowned source files. '
                             'Use a localhost preview/server URL if file URLs are restricted. '
                             'You may also use the bundled Playwright Node API for a full assertion script; close it in finally. '
                             'A sandbox browser-launch restriction needs an explicit once approval, not a product-code change. '
                             'Close your session when finished. Do not install dependencies or retry unavailable tools repeatedly.')

    def close(self, workspace):
        if self.available and self.used:
            try:
                subprocess.run([self.node, str(self.wrapper), 'close'], cwd=workspace,
                               env={**os.environ, **self.env}, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=5)
            except (OSError, subprocess.SubprocessError):
                pass
            self.used = False
