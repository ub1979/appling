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
                 'later': 'Left for later', 'merged': 'Merged', 'failed': 'Tests failed',
                 'serial': 'Being built step by step'}


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


EXPORT_KINDS = {'function', 'class', 'component', 'route', 'event', 'command', 'constant', 'type'}


def _contract(value, ident):
    """A block's checkable interface: its entry file and every name other code may use.
    Returns None when the plan gives none; raises ValueError when it is malformed."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f'{ident} contract must be an object.')
    entry = _text(value.get('entry'), f'{ident} contract entry').removeprefix(f'blocks/{ident}/')
    if entry.startswith('/') or '..' in entry.split('/') or entry.endswith('/'):
        raise ValueError(f'{ident} contract entry must be a file inside blocks/{ident}/.')
    exports, seen = [], set()
    for item in value.get('exports') if isinstance(value.get('exports'), list) else []:
        if not isinstance(item, dict):
            raise ValueError(f'{ident} contract exports must be objects.')
        name = _text(item.get('name'), f'{ident} contract export name')
        if len(name) > 120 or any(c.isspace() for c in name) or name in seen:
            raise ValueError(f'{ident} contract export names must be unique and contain no spaces: {name[:60]}')
        seen.add(name)
        kind = str(item.get('kind') or 'function').strip().lower()
        exports.append(dict(name=name, kind=kind if kind in EXPORT_KINDS else 'function',
                            input=str(item.get('input') or '').strip(), output=str(item.get('output') or '').strip(),
                            errors=str(item.get('errors') or '').strip()))
    if not exports:
        raise ValueError(f'{ident} contract must list at least one export.')
    return dict(entry=entry, exports=exports, config=_strings(value.get('config'), f'{ident} contract config'))


def _uses(value, label):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(label + ' must map a block id to the contract names used from it.')
    return {str(k): _strings(v, label) for k, v in value.items()}


def _check_uses(user, uses, allowed, offered, strict):
    """Keep only uses that the named block's contract really offers. In strict mode a mismatch is an error,
    so the planner fixes it before anything is built."""
    kept = {}
    for dep, names in uses.items():
        if dep not in allowed:
            if strict:
                raise ValueError(f'{user} lists uses of {dep}, which it does not depend on. Add {dep} to depends_on or remove the use.')
            continue
        unknown = [n for n in names if dep in offered and n not in offered[dep]]
        if unknown and strict:
            raise ValueError(f"{user} uses {', '.join(unknown)} from {dep}, but {dep}'s contract does not offer that. "
                             f"Add it to {dep}'s contract exports or change what {user} uses.")
        names = [n for n in names if n not in unknown]
        if names:
            kept[dep] = names
    return kept


def validate(raw, spec, catalogue=(), strict_contracts=False):
    """Check a proposed block plan; return the normalized plan or raise ValueError.
    Contracts are optional (older plans have none). With strict_contracts, a malformed contract, a new block
    without one in a plan that uses contracts, or a use the other block does not offer is an error."""
    if not isinstance(raw, dict) or not isinstance(raw.get('blocks'), list):
        raise ValueError('The block plan needs a list of blocks.')
    criteria = {c['id']: c for c in spec['criteria']}
    prerequisites = {p['id'] for p in spec['prerequisites']}
    available = {f"{b['name']}@{b['version']}" for b in catalogue}
    blocks, ids, wanted_uses = [], set(), {}
    library_contracts = {f"{b['name']}@{b['version']}": b.get('contract') for b in catalogue}
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
        try:
            contract = _contract(item.get('contract') or (library_contracts.get(source[8:]) if source != 'new' else None), ident)
            wanted_uses[ident] = _uses(item.get('uses'), f'{ident} uses')
        except ValueError:
            if strict_contracts:
                raise
            contract = None; wanted_uses[ident] = {}
        if contract:
            blocks[-1]['contract'] = contract
    if strict_contracts and any(b.get('contract') for b in blocks):
        bare = [b['id'] for b in blocks if b['source'] == 'new' and not b.get('contract')]
        if bare:
            raise ValueError('These new blocks have no contract: ' + ', '.join(bare) + '. Give every new block a contract '
                             '(entry file and exports) so the other blocks and the app can be built against it.')
    offered = {b['id']: {e['name'] for e in b['contract']['exports']} for b in blocks if b.get('contract')}
    needs = {f"{b['name']}@{b['version']}": b.get('depends_on') or [] for b in catalogue}
    for block in blocks:
        if block['source'].startswith('library:'):
            # A library block was built next to these blocks and finds them by folder name.
            lacking = [d for d in needs.get(block['source'][8:], []) if d not in ids or d not in block['depends_on']]
            if lacking:
                raise ValueError(f"{block['id']} reuses {block['source'][8:]}, which needs these blocks too (same ids, listed in its "
                                 'depends_on): ' + ', '.join(lacking) + '. Add them (from the library if available) or build this block new.')
    for block in blocks:
        missing = [d for d in block['depends_on'] if d not in ids]
        if missing or block['id'] in block['depends_on']:
            raise ValueError(f"{block['id']} depends on unknown blocks: " + ', '.join(missing or [block['id']]))
        uses = _check_uses(block['id'], wanted_uses[block['id']], set(block['depends_on']), offered, strict_contracts)
        if uses:
            block['uses'] = uses
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
    try:
        body_uses = _check_uses('The body', _uses(body.get('uses'), 'Body uses'), ids, offered, strict_contracts)
    except ValueError:
        if strict_contracts:
            raise
        body_uses = {}
    body = dict(purpose=_text(body.get('purpose'), 'Body purpose'), criteria=body_criteria,
                files=list(dict.fromkeys([BODY_FOLDER, *files])), test=str(body.get('test') or '').strip())
    if body_uses:
        body['uses'] = body_uses
    covered = set(body_criteria).union(*(set(b['criteria']) for b in blocks)) if blocks else set(body_criteria)
    uncovered = [c['id'] for c in acceptance.release_one(spec) if c['id'] not in covered]
    if uncovered:
        raise ValueError('Release-1 criteria are not covered by any block or the body: ' + ', '.join(uncovered))
    return dict(version=2 if offered else 1, summary=str(raw.get('summary') or '').strip(), blocks=blocks, body=body, waves=order)


def deferred(plan, spec):
    """Blocks the owner left for later, or whose criteria all moved to a later release."""
    release = {c['id']: c['release'] for c in spec['criteria']}
    left = set(spec.get('deferred_blocks') or [])
    return {b['id'] for b in plan['blocks']
            if b['id'] in left or (b['criteria'] and all(release.get(c) == 'later' for c in b['criteria']))}


def adopt_criteria(plan, spec):
    """Fit an approved plan to updated criteria without replanning.

    A new release-1 check goes to every kept block (and the body) that already owns a check for the same
    requirement; with no such owner it goes to the body. Checks that no longer exist are dropped.
    Returns (plan, {criterion_id: [owner ids, 'body' for the body]})."""
    plan = json.loads(json.dumps(plan))
    criteria = {c['id']: c for c in spec['criteria']}
    later = deferred(plan, spec)
    for owner in [*plan['blocks'], plan['body']]:
        owner['criteria'] = [c for c in owner['criteria'] if c in criteria]
    owned = set(plan['body']['criteria']).union(*(set(b['criteria']) for b in plan['blocks']))
    added = {}
    for c in acceptance.release_one(spec):
        if c['id'] in owned:
            continue
        owners = [b for b in plan['blocks'] if b['id'] not in later
                  and any(criteria[o]['requirement'] == c['requirement'] for o in b['criteria'])]
        body = plan['body']
        if not owners or any(criteria[o]['requirement'] == c['requirement'] for o in body['criteria']):
            owners.append(body)
        for owner in owners:
            owner['criteria'].append(c['id'])
        added[c['id']] = [o.get('id', 'body') for o in owners]
    return plan, added


def body_only(plan, spec):
    """Release-1 checks only the body covers. The body is built by one agent after the blocks, so this work is not parallel."""
    owned = set().union(*(set(b['criteria']) for b in plan['blocks'])) if plan['blocks'] else set()
    return [c['id'] for c in acceptance.release_one(spec) if c['id'] in plan['body']['criteria'] and c['id'] not in owned]


SMALL_APP_FEATURES = 6
SMALL_APP_NEW_BLOCKS = 2


def small_app(spec):
    """A small first release (few features): splitting it into many new blocks costs more than it saves."""
    features = {c['requirement'] for c in acceptance.release_one(spec) if str(c.get('requirement', '')).startswith('FR-')}
    return len(features) <= SMALL_APP_FEATURES


def too_many_new_blocks(plan, spec):
    new = [b['id'] for b in plan['blocks'] if b['source'] == 'new' and b['id'] not in deferred(plan, spec)]
    return new if small_app(spec) and len(new) > SMALL_APP_NEW_BLOCKS else []


def body_heavy(plan, spec):
    """True when the body alone owns more than a small share of release 1 (tiny apps may be body-only)."""
    total = len(acceptance.release_one(spec))
    return total > 6 and len(body_only(plan, spec)) > max(3, total // 7)


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
    lines += ['', f"**App body** (`app/`): {plan['body']['purpose']}", '']
    alone = body_only(plan, spec); total = len(acceptance.release_one(spec))
    if body_heavy(plan, spec):
        lines += [f"**Warning: the app body alone covers {len(alone)} of {total} release-1 checks** ({', '.join(alone)}). "
                  'The body is built by one agent after all blocks finish, so this work is not parallel and the merge step '
                  'will be long. Request changes to move feature areas into blocks.', '']
    elif plan['blocks']:
        lines += [f"The app body only connects the blocks; it alone covers {len(alone)} of {total} release-1 checks.", '']
    lines += ['## Build order', '']
    lines += [f'{i}. ' + ', '.join(wave) + (' (in parallel)' if len(wave) > 1 else '') for i, wave in enumerate(plan['waves'], 1)]
    lines += ['', '## Interfaces', '']
    for b in plan['blocks']:
        lines += [f"### {b['name']}", '', b['interface'], '']
        if b.get('contract'):
            cell = lambda text: (text or '-').replace('|', '/').replace('\n', ' ')
            lines += [f"Agreed contract. Entry file: `{b['folder']}{b['contract']['entry']}`"
                      + (f" · Settings: {', '.join(b['contract']['config'])}" if b['contract'].get('config') else ''), '',
                      '| Name | Kind | Takes | Gives back | Errors |', '|---|---|---|---|---|']
            lines += [f"| `{cell(e['name'])}` | {e['kind']} | {cell(e['input'])} | {cell(e['output'])} | {cell(e['errors'])} |"
                      for e in b['contract']['exports']]
            lines += ['']
        if b.get('uses'):
            lines += ['Uses: ' + '; '.join(f"{dep}: {', '.join(names)}" for dep, names in b['uses'].items()), '']
        lines += [f"Covers: {', '.join(b['criteria']) or '-'} · " + (f"Setup: `{b['setup']}` · " if b.get('setup') else '') + f"Test: `{b['test']}`", '']
    if plan['body'].get('uses'):
        lines += ['App body uses: ' + '; '.join(f"{dep}: {', '.join(names)}" for dep, names in plan['body']['uses'].items()), '']
    if any(b.get('contract') for b in plan['blocks']):
        lines += ['Contracts are agreed before building. Appling checks that each block provides every name in its contract, '
                  'in its code and in its tests, before the block counts as built.', '']
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


CONTRACT_RULES = ('Agreed contract (fixed before building; other blocks and the app are built against it, so provide exactly this): '
                  '{contract}\n'
                  'Everything in the contract is reachable from the entry file {entry} under exactly these names, with these inputs, '
                  'outputs and errors. Every block has the same shape: settings come in through the entry or the config names listed, '
                  'never from project-specific files; errors are raised or returned as the contract says; another block is used only '
                  'through its own entry file and only when listed below. Your tests call every contract name. Appling checks that '
                  'each name exists in your source and in your tests before the block counts as built. If the contract cannot be met '
                  'as written, report an integration blocker saying exactly what must change; never rename or drop a name silently.\n')


def conformance(root, block):
    """Compare a built block with its agreed contract. Returns (missing, soft): names absent from the block's
    source (a broken promise to its users), and softer gaps (a name no test mentions, a differently named entry file).
    Deliberately literal and conservative: a name that appears nowhere cannot be provided."""
    contract = block.get('contract')
    if not contract:
        return [], []
    folder = Path(root) / block['folder']
    skip = {'node_modules', '.venv', 'venv', 'dist', 'build', 'out', 'coverage', '__pycache__', '.git', '.pytest_cache',
            'target', '.build', '.next', 'models'}
    source, tests = [], []
    for path in sorted(folder.rglob('*')) if folder.is_dir() else []:
        rel = path.relative_to(folder)
        if any(part in skip for part in rel.parts) or not path.is_file() or path.is_symlink() or rel.name in {'README.md', 'block.json'}:
            continue
        try:
            if path.stat().st_size > 1_000_000:
                continue
            text = path.read_text(errors='ignore')
        except OSError:
            continue
        is_test = any(re.search(r'(^|[._-])(tests?|specs?|__tests__)([._-]|$)', part.lower()) for part in rel.parts)
        (tests if is_test else source).append(text)
    # The plan names the entry file before any code exists, so a different file name is something to correct once,
    # not a reason to stop: the names themselves are the promise other blocks rely on.
    missing = []
    untested = [] if (folder / contract['entry']).is_file() else [
        f"The entry file {block['folder']}{contract['entry']} does not exist. Provide it (it may simply re-export from where the code lives)."]
    for export in contract['exports']:
        if not any(export['name'] in text for text in source):
            missing.append(f"{export['name']} ({export['kind']}) is in the contract but nowhere in the block's source.")
        elif tests and export['kind'] not in {'type', 'constant'} and not any(export['name'] in text for text in tests):
            untested.append(f"{export['name']} ({export['kind']}) is not used by any test in the block.")
    return missing, untested


def builder_goal(block, plan, spec):
    """A block builder sees only its block, the interfaces it depends on and the criteria it covers."""
    criteria = {c['id']: c for c in spec['criteria']}
    deps = [b for b in plan['blocks'] if b['id'] in block['depends_on']]
    return (f"Build the reusable block \"{block['name']}\" in {block['folder']} only. Purpose: {block['purpose']}\n"
            f"Interface to provide: {block['interface']}\n"
            + (CONTRACT_RULES.format(contract=json.dumps(block['contract']), entry=block['folder'] + block['contract']['entry'])
               if block.get('contract') else '') +
            f"Acceptance criteria it supports: " + json.dumps([dict(id=c, text=criteria[c]['description'], live=criteria[c]['live'])
                                                              for c in block['criteria'] if c in criteria and criteria[c]['release'] == '1']) + '\n'
            + ('Out of scope for now (later release, do not build): ' + json.dumps([criteria[c]['description'][:160] for c in block['criteria']
                                                                                    if c in criteria and criteria[c]['release'] == 'later']) + '\n'
               if any(c in criteria and criteria[c]['release'] == 'later' for c in block['criteria']) else '')
            + (f"It may use these blocks only through their documented interfaces: " +
               json.dumps([dict(id=d['id'], folder=d['folder'], interface=d['interface'],
                                **({'contract': d['contract'], 'you_use': (block.get('uses') or {}).get(d['id'], [])}
                                   if d.get('contract') else {})) for d in deps]) + '\n' if deps else '')
            + 'Keep it generic and reusable: no project names, no app-specific data or credentials; configuration comes in through '
              'the interface. Deliver source, tests, README.md (purpose, interface, configuration, setup, limits) and block.json '
              '{"name","purpose","interface","runtime","config":[...],"setup":"command","test":"command","prerequisites":[...]}. '
              f"Its approved test command is: {block['test']}" + (f" (setup: {block['setup']})" if block['setup'] else '') + '. '
              'Do not edit anything outside your block folder. Live parts that need owner accounts or devices must still be '
              'implemented behind the interface and tested with local fakes; report them as live_acceptance, not as done. '
              'If a block you depend on lacks something you need, report an integration blocker with "block":"<its id>" and exactly what it '
              'must add. Report things the app itself must provide (wiring, host services) as integration blockers without "block".')


def _run(command, root, log, timeout=900):
    """Run an owner-approved command in its own process group; output goes to a file, not a pipe,
    so a background child cannot hang the wait, and the whole group is killed afterwards."""
    import signal
    started = time.time()
    log.parent.mkdir(parents=True, exist_ok=True)
    output = log.with_suffix('.out')
    with open(output, 'w', errors='replace') as fh:
        proc = subprocess.Popen(command, shell=True, cwd=root, stdout=fh, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=True,
                                env={**os.environ, 'APPLING_HEADLESS': '1'})   # controller checks never open windows
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
                                                  'published', 'project', 'verified_in', 'depends_on', 'contract']})
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


CODE_SUFFIXES = {'.js', '.mjs', '.cjs', '.ts', '.mts', '.cts', '.tsx', '.jsx', '.py'}


def undeclared_imports(root, block, plan_):
    """Other blocks this block's code reaches by path without listing them in depends_on.
    Such a block works only next to its old neighbours, so it is not saved to the library."""
    others = {b['id'] for b in plan_['blocks']} - {block['id']} - set(block.get('depends_on') or [])
    folder = Path(root) / block['folder']
    found = set()
    if not others or not folder.is_dir():
        return []
    patterns = {o: re.compile(r'(?:\.\./)+' + re.escape(o) + r'/|blocks/' + re.escape(o) + r'/') for o in others}
    for path in folder.rglob('*'):
        if path.suffix not in CODE_SUFFIXES or 'node_modules' in path.parts or not path.is_file():
            continue
        text = path.read_text(errors='replace')
        found |= {o for o, pattern in patterns.items() if pattern.search(text)}
    return sorted(found)


def library_name(block):
    return block['source'][8:].split('@')[0] if block['source'].startswith('library:') else block['id']


def publish(root, block, project, commit=None, evidence=None, home=None, verified=True, depends_on=None):
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
                depends_on=list(depends_on if depends_on is not None else block.get('depends_on') or []),
                commit=commit, published=time.time(), verified_in=[], **({'contract': block['contract']} if block.get('contract') else {}),
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
