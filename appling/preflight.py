"""Read-only runtime probes. Dependency installation stays in approved tasks."""
from __future__ import annotations
import json
from pathlib import Path
import re
import shutil
import subprocess


def version(value):
    match=re.search(r'\d+(?:\.\d+){0,2}',value)
    if not match:raise ValueError('Could not determine runtime version.')
    return tuple((list(map(int,match[0].split('.')))+[0,0])[:3])


def require_runtime(root,runtime,browser_runner):
    """Fail before model execution; never run a model-provided setup command."""
    requirements={t['name']:t['minimum'] for t in runtime.get('tools',[])}
    manifest=Path(root)/'package.json'
    if manifest.exists():
        node=json.loads(manifest.read_text()).get('engines',{}).get('node')
        if node:
            match=re.fullmatch(r'\s*>=\s*(\d+(?:\.\d+){0,2})\s*',node)
            if not match:
                raise ValueError('Runtime preflight needs a supported explicit Node minimum in package.json (>=major.minor.patch).')
            if 'node' not in requirements or version(match[1])>version(requirements['node']):requirements['node']=match[1]
    observed={}
    for tool,minimum in requirements.items():
        executable=shutil.which(tool)
        if not executable:raise ValueError(f'Runtime preflight: {tool} is missing. Install it before retrying.')
        try:
            checked=subprocess.run([executable,'--version'],cwd=root,capture_output=True,text=True,timeout=15)
            actual=version(checked.stdout or checked.stderr)
        except (OSError,subprocess.TimeoutExpired,ValueError) as exc:
            raise ValueError(f'Runtime preflight: cannot verify {tool}.') from exc
        if checked.returncode or actual<version(minimum):
            raise ValueError(f'Runtime preflight: {tool} requires >= {minimum}; found '+'.'.join(map(str,actual))+'. Update the runtime, restart Appling and retry.')
        observed[tool]='.'.join(map(str,actual))
    if runtime.get('browser'):
        node=shutil.which('node')
        if not node:raise ValueError('Browser preflight needs Node and the supplied browser setup script.')
        probe="const {createRequire}=require('node:module');const fs=require('node:fs');const r=createRequire(process.argv[1]);const p=r('playwright').chromium.executablePath();if(!fs.existsSync(p))process.exit(2);"
        try:
            result=subprocess.run([node,'-e',probe,str(Path(browser_runner).resolve())],cwd=root,capture_output=True,timeout=15)
        except (OSError,subprocess.TimeoutExpired) as exc:
            raise ValueError('Browser preflight failed. Run scripts/setup-browser.sh before retrying.') from exc
        if result.returncode:raise ValueError('Browser preflight: host Playwright or matching Chromium is missing. Run scripts/setup-browser.sh before retrying.')
        observed['browser']='installed; actual journeys still require browser evidence'
    return observed
