"""Reusable blocks: the block plan, its checks, and the shared block library.

A project is split into independent blocks (packages under `blocks/<id>/`,
each with its own interface, tests, README and block.json) and a
project-specific body (`app/`) that wires them together. The owner approves
the block plan; the controller validates folders, dependencies and criteria
coverage, builds independent blocks in parallel, runs each block's approved
test command itself, and publishes passing blocks to a shared library at
`~/.appling/blocks/` (override with APPLING_BLOCKS_HOME).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import acceptance
from .store import safe_path

PLAN = '.sdlc/blocks.json'
DOC = 'blocks.md'
BODY_FOLDER = 'app/'
BLOCK_ID = re.compile(r'[a-z][a-z0-9-]{1,40}')
RUNTIMES = {'in-process', 'service'}
STATUS_LABELS = {'planned': 'Planned', 'building': 'Building', 'tested': 'Tested', 'blocked': 'Needs a decision',
                 'later': 'Left for later', 'merged': 'Merged', 'failed': 'Tests failed'}


def library_home():
    return Path(os.environ.get('APPLING_BLOCKS_HOME') or Path.home() / '.appling' / 'blocks')


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + ' must be nonempty text.')
    return value.strip()


def _strings(value, label):
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise ValueError(label + ' must be a list of text values.')
    return list(dict.fromkeys(v.strip() for v in value))


def validate(raw, spec, catalogue=()):
    """Check a proposed block plan; return the normalized plan or raise ValueError."""
    if not isinstance(raw, dict) or not isinstance(raw.get('blocks'), list):
        raise ValueError('The block plan needs a list of blocks.')
    criteria = {c['id']: c for c in spec['criteria']}
    prerequisites = {p['id'] for p in spec['prerequisites']}
    available = {f"{b['name']}@{b['version']}" for b in catalogue}
    blocks, ids = [], set()
    for item in raw['blocks']:
        if not isinstance(item, dict):
            raise ValueError('Each block must be an object.')
        ident = _text(item.get('id'), 'Block id')
        if not BLOCK_ID.fullmatch(ident) or ident in ids or ident == 'body':
            raise ValueError('Block IDs must be unique lowercase names like "telegram-bot": ' + ident)
        ids.add(ident)
        source = item.get('source') or 'new'
        if source != 'new' and not (source.startswith('library:') and source[8:] in available):
            raise ValueError(f'{ident} uses an unknown library block: {source}')
        runtime = item.get('runtime') or 'in-process'
        if runtime not in RUNTIMES:
            raise ValueError(f'{ident} runtime must be in-process or service.')
        covers = _strings(item.get('criteria'), f'{ident} criteria')
        unknown = [c for c in covers if c not in criteria]
        if unknown:
            raise ValueError(f'{ident} covers unknown criteria: ' + ', '.join(unknown))
        needs = _strings(item.get('prerequisites'), f'{ident} prerequisites')
        if any(n not in prerequisites for n in needs):
            raise ValueError(f'{ident} names an unknown setup item.')
        blocks.append(dict(
            id=ident, name=_text(item.get('name'), f'{ident} name'), purpose=_text(item.get('purpose'), f'{ident} purpose'),
            interface=_text(item.get('interface'), f'{ident} interface'), folder=f'blocks/{ident}/', runtime=runtime,
            criteria=covers, depends_on=_strings(item.get('depends_on'), f'{ident} depends_on'), prerequisites=needs,
            source=source, setup=str(item.get('setup') or '').strip(), test=_text(item.get('test'), f'{ident} test command')))
    for block in blocks:
        missing = [d for d in block['depends_on'] if d not in ids]
        if missing or block['id'] in block['depends_on']:
            raise ValueError(f"{block['id']} depends on unknown blocks: " + ', '.join(missing or [block['id']]))
    done, order = set(), []
    while len(done) < len(blocks):
        ready = [b for b in blocks if b['id'] not in done and set(b['depends_on']) <= done]
        if not ready:
            raise ValueError('Block dependencies form a cycle.')
        done.update(b['id'] for b in ready)
        order.append([b['id'] for b in ready])
    body = raw.get('body') or {}
    if not isinstance(body, dict):
        raise ValueError('The body must be an object.')
    body_criteria = _strings(body.get('criteria'), 'Body criteria')
    if any(c not in criteria for c in body_criteria):
        raise ValueError('The body covers unknown criteria.')
    files = _strings(body.get('files'), 'Body files')
    for name in files:
        if name.startswith(('blocks/', '/')) or '..' in name.split('/') or name.startswith(('requirements.md', 'prototypes/', '.sdlc/')):
            raise ValueError('The body cannot own blocks, approved documents or controller files: ' + name)
    body = dict(purpose=_text(body.get('purpose'), 'Body purpose'), criteria=body_criteria,
                files=list(dict.fromkeys([BODY_FOLDER, *files])), test=str(body.get('test') or '').strip())
    covered = set(body_criteria).union(*(set(b['criteria']) for b in blocks)) if blocks else set(body_criteria)
    uncovered = [c['id'] for c in acceptance.release_one(spec) if c['id'] not in covered]
    if uncovered:
        raise ValueError('Release-1 criteria are not covered by any block or the body: ' + ', '.join(uncovered))
    return dict(version=1, summary=str(raw.get('summary') or '').strip(), blocks=blocks, body=body, waves=order)


def deferred(plan, spec):
    """Blocks the owner left for later, or whose criteria all moved to a later release."""
    release = {c['id']: c['release'] for c in spec['criteria']}
    left = set(spec.get('deferred_blocks') or [])
    return {b['id'] for b in plan['blocks']
            if b['id'] in left or (b['criteria'] and all(release.get(c) == 'later' for c in b['criteria']))}


def markdown(plan, spec):
    setup = {p['id']: p['description'] for p in spec['prerequisites']}
    later = deferred(plan, spec)
    lines = ['# Block plan', '', plan.get('summary') or '', '',
             'Each block is a reusable package in `blocks/<id>/` with its own interface, tests and README. '
             'Independent blocks are built at the same time. The app body (`app/`) then wires them together.', '',
             '| Block | What it does | Built from | Waits for | Your setup | Release |', '|---|---|---|---|---|---|']
    for b in plan['blocks']:
        source = 'new' if b['source'] == 'new' else 'library ' + b['source'][8:]
        lines.append(f"| **{b['name']}** (`{b['id']}`) | {b['purpose'].replace('|', '/')} | {source} | "
                     f"{', '.join(b['depends_on']) or '-'} | {', '.join(setup.get(p, p) for p in b['prerequisites']) or '-'} | "
                     f"{'later' if b['id'] in later else '1'} |")
    lines += ['', f"**App body** (`app/`): {plan['body']['purpose']}", '', '## Build order', '']
    lines += [f'{i}. ' + ', '.join(wave) + (' (in parallel)' if len(wave) > 1 else '') for i, wave in enumerate(plan['waves'], 1)]
    lines += ['', '## Interfaces', '']
    for b in plan['blocks']:
        lines += [f"### {b['name']}", '', b['interface'], '',
                  f"Covers: {', '.join(b['criteria']) or '-'} · " + (f"Setup: `{b['setup']}` · " if b.get('setup') else '') + f"Test: `{b['test']}`", '']
    if plan['body'].get('test'):
        lines += [f"App body test: `{plan['body']['test']}`", '']
    lines += ['Approving this plan lets Appling run each block\'s setup and test commands above on this Mac to check the blocks itself.',
              'To leave a block for later, choose Request changes and say which blocks.']
    return '\n'.join(lines).strip() + '\n'


def write(root, plan, spec):
    root = Path(root)
    path = safe_path(root, PLAN)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + '\n')
    safe_path(root, DOC).write_text(markdown(plan, spec))


def load(root):
    path = safe_path(Path(root), PLAN)
    return json.loads(path.read_text()) if path.is_file() else None


def block_tasks(plan, spec):
    """Controller tasks for the block builders; deferred blocks are skipped."""
    later = deferred(plan, spec)
    tasks = []
    for b in plan['blocks']:
        if b['id'] in later:
            continue
        tasks.append(dict(id=b['id'], goal=f"Build reusable block {b['name']}", depends_on=[d for d in b['depends_on'] if d not in later],
                          kind='development', role='sw-developer', files=[b['folder']], status='pending', block=b['id'],
                          acceptance=[dict(command=b['test'], expect='Block tests pass', requires_tasks=[])]))
    return tasks


def builder_goal(block, plan, spec):
    """A block builder sees only its block, the interfaces it depends on and the criteria it covers."""
    criteria = {c['id']: c for c in spec['criteria']}
    deps = [b for b in plan['blocks'] if b['id'] in block['depends_on']]
    return (f"Build the reusable block \"{block['name']}\" in {block['folder']} only. Purpose: {block['purpose']}\n"
            f"Interface to provide: {block['interface']}\n"
            f"Acceptance criteria it supports: " + json.dumps([dict(id=c, text=criteria[c]['description'], live=criteria[c]['live'])
                                                              for c in block['criteria'] if c in criteria]) + '\n'
            + (f"It may use these blocks only through their documented interfaces: " +
               json.dumps([dict(id=d['id'], folder=d['folder'], interface=d['interface']) for d in deps]) + '\n' if deps else '')
            + 'Keep it generic and reusable: no project names, no app-specific data or credentials; configuration comes in through '
              'the interface. Deliver source, tests, README.md (purpose, interface, configuration, setup, limits) and block.json '
              '{"name","purpose","interface","runtime","config":[...],"setup":"command","test":"command","prerequisites":[...]}. '
              f"Its approved test command is: {block['test']}" + (f" (setup: {block['setup']})" if block['setup'] else '') + '. '
              'Do not edit anything outside your block folder. Live parts that need owner accounts or devices must still be '
              'implemented behind the interface and tested with local fakes; report them as live_acceptance, not as done.')


def _run(command, root, log, timeout=900):
    """Run an owner-approved command in its own process group; output goes to a file, not a pipe,
    so a background child cannot hang the wait, and the whole group is killed afterwards."""
    import signal
    started = time.time()
    log.parent.mkdir(parents=True, exist_ok=True)
    output = log.with_suffix('.out')
    with open(output, 'w', errors='replace') as fh:
        proc = subprocess.Popen(command, shell=True, cwd=root, stdout=fh, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            code = 124
        finally:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
    text = output.read_text(errors='replace')[-200_000:]
    output.unlink(missing_ok=True)
    note = f'Timed out after {timeout}s\n' if code == 124 else ''
    log.write_text(f'command: {command}\nexit: {code}\nseconds: {time.time()-started:.1f}\n\n{note}{text}')
    return code


def run_block_tests(root, block):
    """The controller runs the owner-approved setup/test commands itself and keeps the output."""
    root = Path(root)
    folder = Path('.sdlc/evidence/blocks') / block['id']
    if block.get('setup'):
        code = _run(block['setup'], root, root / folder / 'setup.log')
        if code:
            return dict(passed=False, exit_code=code, evidence=str(folder / 'setup.log'))
    code = _run(block['test'], root, root / folder / 'test.log')
    return dict(passed=code == 0, exit_code=code, evidence=str(folder / 'test.log'))


# ---------------------------------------------------------------- library

def catalogue(home=None):
    home = Path(home or library_home())
    entries = []
    if not home.is_dir():
        return entries
    for meta in sorted(home.glob('*/*/meta.json')):
        try:
            data = json.loads(meta.read_text())
        except (OSError, ValueError):
            continue
        entries.append({k: data.get(k) for k in ['name', 'version', 'status', 'purpose', 'interface', 'runtime', 'test', 'setup',
                                                  'published', 'project', 'verified_in']})
    return entries


def _digest(folder):
    from .checkpoints import denied
    digest = hashlib.sha256()
    for p in sorted(Path(folder).rglob('*')):
        rel = str(p.relative_to(folder))
        if p.is_file() and not p.is_symlink() and not denied(rel):
            data = p.read_bytes()
            if rel == 'block.json':
                # Where a copy came from is not part of the block's content.
                try:
                    info = json.loads(data); info.pop('origin', None)
                    data = json.dumps(info, sort_keys=True).encode()
                except ValueError:
                    pass
            digest.update(rel.encode()); digest.update(data)
    return digest.hexdigest()


def _copy_clean(src, dst):
    from .checkpoints import denied
    for p in sorted(Path(src).rglob('*')):
        rel = p.relative_to(src)
        if p.is_symlink() or not p.is_file() or denied(str(rel)):
            continue
        target = Path(dst) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)


def library_name(block):
    return block['source'][8:].split('@')[0] if block['source'].startswith('library:') else block['id']


def publish(root, block, project, commit=None, evidence=None, home=None, verified=True):
    """Save a passing block as a new immutable version; reuse in a new project marks it verified."""
    home = Path(home or library_home())
    src = Path(root) / block['folder']
    if not src.is_dir():
        return None
    name = library_name(block)
    folder = home / name
    versions = sorted((int(p.name[1:]) for p in folder.glob('v*') if p.name[1:].isdigit()), reverse=True)
    digest = _digest(src)
    if block['source'].startswith('library:'):
        origin = folder / ('v' + block['source'].split('@')[1].lstrip('v'))
        meta_path = origin / 'meta.json'
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text())
            if meta.get('digest') == digest:
                # Unchanged library block passed in another project: it is now verified.
                if verified and project != meta.get('project') and project not in meta.get('verified_in', []):
                    meta['verified_in'] = [*meta.get('verified_in', []), project]
                    meta['status'] = 'verified'
                    meta_path.write_text(json.dumps(meta, indent=2))
                return meta
    for v in versions:
        meta_path = folder / f'v{v}' / 'meta.json'
        if meta_path.is_file() and json.loads(meta_path.read_text()).get('digest') == digest:
            return json.loads(meta_path.read_text())
    version = (versions[0] + 1) if versions else 1
    while True:
        target = folder / f'v{version}'
        try:
            target.mkdir(parents=True, exist_ok=False)   # claim the version exclusively
            break
        except FileExistsError:
            version += 1
    _copy_clean(src, target / 'source')
    if evidence and (Path(root) / evidence).is_file():
        (target / 'evidence').mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(root) / evidence, target / 'evidence' / Path(evidence).name)
    meta = dict(name=name, version=f'v{version}', status='candidate', purpose=block['purpose'], interface=block['interface'],
                runtime=block['runtime'], test=block['test'], setup=block.get('setup', ''), digest=digest, project=project,
                commit=commit, published=time.time(), verified_in=[],
                provenance='Generated by Appling for the named project; review licences of any third-party dependencies it declares.')
    (target / 'meta.json').write_text(json.dumps(meta, indent=2))
    return meta


def install(root, block, home=None):
    """Copy a pinned library version into the project and record where it came from."""
    home = Path(home or library_home())
    name, version = block['source'][8:].split('@')
    src = home / name / version / 'source'
    if not src.is_dir():
        raise ValueError(f'Library block {name}@{version} is missing.')
    dst = Path(root) / block['folder']
    if dst.exists():
        shutil.rmtree(dst)
    _copy_clean(src, dst)
    info = dst / 'block.json'
    if info.is_file():
        try:
            data = json.loads(info.read_text())
        except ValueError:
            data = None
        if isinstance(data, dict):
            data['origin'] = dict(library=name, version=version)
            info.write_text(json.dumps(data, indent=2))
    return dst
