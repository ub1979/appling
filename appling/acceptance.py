"""Approved acceptance criteria and controller-evaluated results.

The requirements agent proposes criteria and owner prerequisites. Once the owner
approves requirements, `.sdlc/acceptance.json` is part of that approval
revision, so no later model can add, drop or reword a criterion. Results are
computed by the controller from verification output and bound to the source
revision that was examined. A builder's blocker label never grants deferral:
only an approved live criterion with an unsatisfied recorded prerequisite may
be `pending_owner`, and only after its locally testable behaviour passed.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from .store import safe_path

SPEC = '.sdlc/acceptance.json'
RESULTS = '.sdlc/acceptance-results.json'
STATUSES = ('passed', 'failed', 'pending_owner', 'not_run')
PREREQUISITE_KINDS = {'account', 'driver', 'permission', 'device', 'time', 'service', 'other'}
REQUIREMENT_ID = re.compile(r'\b(?:N?FR)-\d+\b')
CRITERION_ID = re.compile(r'AC-[A-Za-z0-9_.-]+')
PREREQUISITE_ID = re.compile(r'P-[A-Za-z0-9_.-]+')


def requirement_ids(text):
    return list(dict.fromkeys(REQUIREMENT_ID.findall(text or '')))


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + ' must be nonempty text.')
    return value.strip()


def normalize(criteria, prerequisites, requirements_text):
    """Validate a proposed criteria set against the requirements it belongs to."""
    expected = requirement_ids(requirements_text)
    if not expected:
        raise ValueError('Requirements need stable FR/NFR IDs before acceptance criteria.')
    if prerequisites is None:
        prerequisites = []
    if not isinstance(prerequisites, list):
        raise ValueError('Prerequisites must be a list.')
    prereqs, seen = [], set()
    for item in prerequisites:
        if not isinstance(item, dict):
            raise ValueError('Each prerequisite must be an object.')
        ident = _text(item.get('id'), 'Prerequisite id')
        if not PREREQUISITE_ID.fullmatch(ident) or ident in seen:
            raise ValueError('Prerequisite IDs must be unique and look like P-name: ' + ident)
        seen.add(ident)
        kind = item.get('kind', 'other')
        if kind not in PREREQUISITE_KINDS:
            raise ValueError('Unknown prerequisite kind for ' + ident + ': ' + str(kind))
        prereqs.append(dict(id=ident, kind=kind, description=_text(item.get('description'), 'Prerequisite description'),
                            needed_at=item.get('needed_at') if item.get('needed_at') in {'build', 'verification'} else 'verification'))
    if not isinstance(criteria, list) or not criteria:
        raise ValueError('Acceptance criteria must be a nonempty list.')
    result, ids = [], set()
    for item in criteria:
        if not isinstance(item, dict):
            raise ValueError('Each acceptance criterion must be an object.')
        ident = _text(item.get('id'), 'Criterion id')
        if not CRITERION_ID.fullmatch(ident) or ident in ids:
            raise ValueError('Criterion IDs must be unique and look like AC-FR-1-1: ' + ident)
        ids.add(ident)
        requirement = _text(item.get('requirement'), 'Criterion requirement')
        if requirement not in expected:
            raise ValueError(f'{ident} refers to unknown requirement {requirement}.')
        release = str(item.get('release', '1'))
        if release not in {'1', 'later'}:
            raise ValueError(f'{ident} release must be "1" or "later".')
        live = item.get('live', False)
        if not isinstance(live, bool):
            raise ValueError(f'{ident} live must be true or false.')
        needs = item.get('prerequisites', [])
        if not isinstance(needs, list) or any(n not in seen for n in needs):
            raise ValueError(f'{ident} refers to unknown prerequisites.')
        if live and not needs:
            raise ValueError(f'{ident} is live acceptance and must name the owner prerequisite it needs.')
        result.append(dict(id=ident, requirement=requirement, description=_text(item.get('description'), 'Criterion description'),
                           release=release, live=live, prerequisites=list(dict.fromkeys(needs))))
    covered = {c['requirement'] for c in result}
    missing = [r for r in expected if r not in covered]
    if missing:
        raise ValueError('Every requirement needs at least one acceptance criterion: ' + ', '.join(missing))
    return dict(version=1, criteria=result, prerequisites=prereqs)


def derived(requirements_text):
    """One local criterion per requirement, for projects without approved criteria."""
    lines = (requirements_text or '').splitlines()
    criteria = []
    for ident in requirement_ids(requirements_text):
        line = next((l.strip(' -*#\t') for l in lines if re.search(r'\b' + re.escape(ident) + r'\b', l)), ident)
        criteria.append(dict(id=f'AC-{ident}-1', requirement=ident, description=line[:500] or ident,
                             release='1', live=False, prerequisites=[]))
    return dict(version=1, criteria=criteria, prerequisites=[], derived=True)


def write(root, spec):
    path = safe_path(Path(root), SPEC)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + '\n')


def load(root):
    """The approved spec, or criteria derived from requirements.md when none exists."""
    root = Path(root)
    path = safe_path(root, SPEC)
    if path.is_file():
        return json.loads(path.read_text())
    requirements = safe_path(root, 'requirements.md')
    return derived(requirements.read_text() if requirements.is_file() else '')


def release_one(spec):
    return [c for c in spec['criteria'] if c['release'] == '1']


def summary_markdown(spec):
    """Human-readable table appended to the requirements review."""
    if spec.get('derived'):
        return ''
    rows = ['## Acceptance criteria (approved with these requirements)', '',
            '| ID | Requirement | Release | Live | Needs | Criterion |', '|---|---|---|---|---|---|']
    for c in spec['criteria']:
        rows.append(f"| {c['id']} | {c['requirement']} | {c['release']} | {'yes' if c['live'] else 'no'} | "
                    f"{', '.join(c['prerequisites']) or '-'} | {c['description'].replace('|', '/')} |")
    if spec['prerequisites']:
        rows += ['', '## What you will need to provide', '', '| ID | Kind | Needed at | Description |', '|---|---|---|---|']
        for p in spec['prerequisites']:
            rows.append(f"| {p['id']} | {p['kind']} | {p['needed_at']} | {p['description'].replace('|', '/')} |")
    return '\n'.join(rows)


def readiness(state):
    """Owner-reported setup, a signal that can change without project files changing."""
    done = state.get('prerequisites_done') or {}
    return {k: bool(v) for k, v in sorted(done.items()) if v}


def unsatisfied(spec, criterion, state):
    done = readiness(state)
    return [p for p in criterion['prerequisites'] if p not in done]


def deferrable(spec, criterion, state):
    """Only the controller decides deferral: live, recorded prerequisite, not yet satisfied."""
    return bool(criterion['live'] and criterion['prerequisites'] and unsatisfied(spec, criterion, state))


def has_deferrable(spec, state):
    return any(deferrable(spec, c, state) for c in release_one(spec))


def _evidence_ok(root, path, prefix=None):
    """Nonempty evidence inside the project, and inside this run's folder when given."""
    if not isinstance(path, str) or not path.strip():
        return False
    try:
        p = safe_path(Path(root), path)
        if prefix and not p.is_relative_to(safe_path(Path(root), prefix)):
            return False   # old evidence elsewhere in the project proves nothing about this run
    except ValueError:
        return False
    return p.is_file() and p.stat().st_size > 0


def _zero(entry):
    # An omitted exit code is not a pass.
    return type(entry.get('exit_code')) is int and entry['exit_code'] == 0


def evaluate(root, spec, state, result, source_revision, role='qa-engineer', evidence_prefix=None):
    """Turn independent verification output into per-criterion results.

    The verifier may report `criteria` entries; otherwise passing `checks` with
    requirement IDs cover the local criteria of those requirements (legacy QA).
    Live criteria always need a criterion-level report. Evidence must come from
    this verification run's folder when `evidence_prefix` is supplied.
    """
    now = time.time()
    reported = {}
    for entry in result.get('criteria') or []:
        if isinstance(entry, dict) and isinstance(entry.get('id'), str):
            reported[entry['id']] = entry
    covered = set()
    for check in result.get('checks') or []:
        if isinstance(check, dict) and _zero(check) and check.get('command') and _evidence_ok(root, check.get('evidence'), evidence_prefix):
            covered.update(r for r in check.get('requirements', []) if isinstance(r, str))
    results = {}
    for criterion in release_one(spec):
        entry = reported.get(criterion['id'])
        record = dict(status='not_run', source_revision=source_revision, checked_at=now, role=role,
                      requirement=criterion['requirement'], evidence=None, next_action=None, owner=None, detail=None)
        if entry is None:
            if criterion['requirement'] in covered and not criterion['live']:
                record.update(status='passed', detail='Covered by a passing requirement check.')
            elif criterion['live']:
                record.update(next_action='Live criteria need a criterion-level verification report.', owner='builder')
            else:
                record.update(next_action='Verification did not report this criterion.', owner='builder')
            results[criterion['id']] = record
            continue
        claimed = entry.get('status')
        evidence = entry.get('evidence')
        good_local = _zero(entry) and _evidence_ok(root, evidence, evidence_prefix)
        record.update(evidence=evidence if isinstance(evidence, str) else None,
                      detail=str(entry.get('detail') or '')[:1000] or None)
        if claimed == 'passed' and good_local and criterion['live'] and unsatisfied(spec, criterion, state):
            # A live pass needs the recorded setup; without it this is at most local evidence.
            if entry.get('implemented') is False:
                record.update(status='failed', owner='builder', next_action='Implement the code path.')
            else:
                waiting = unsatisfied(spec, criterion, state)
                record.update(status='pending_owner', owner='you', prerequisites=waiting,
                              next_action='Live pass claimed before setup was recorded; provide: ' + ', '.join(waiting))
        elif claimed == 'passed':
            if good_local:
                record.update(status='passed')
            else:
                record.update(status='not_run', next_action='Passing claim lacks a zero-exit check with nonempty evidence.', owner='builder')
        elif claimed == 'pending_owner':
            if entry.get('implemented') is not True:
                record.update(status='failed', next_action='Implement the code path; setup cannot excuse missing implementation.', owner='builder')
            elif not deferrable(spec, criterion, state):
                record.update(status='not_run', owner='builder',
                              next_action='Not an approved live criterion with an unsatisfied prerequisite; verify it now.')
            elif not good_local:
                record.update(status='not_run', owner='builder',
                              next_action='Locally testable behaviour needs a zero-exit check with nonempty evidence before live acceptance can wait.')
            else:
                waiting = unsatisfied(spec, criterion, state)
                record.update(status='pending_owner', owner='you',
                              next_action=str(entry.get('next_action') or ('Provide: ' + ', '.join(waiting)))[:500],
                              prerequisites=waiting)
        elif claimed == 'failed':
            record.update(status='failed', owner='builder',
                          next_action=str(entry.get('next_action') or 'Repair the failing behaviour.')[:500])
        else:
            record.update(next_action='Verification did not run this criterion.', owner='builder')
        results[criterion['id']] = record
    return results


def save_results(root, results):
    path = safe_path(Path(root), RESULTS)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + '\n')


def load_results(root):
    path = safe_path(Path(root), RESULTS)
    return json.loads(path.read_text()) if path.is_file() else {}


def current(root, spec, results, source_revision):
    """Results examined against other bytes no longer count; show them as not run."""
    out = {}
    for criterion in release_one(spec):
        record = dict(results.get(criterion['id']) or dict(status='not_run', requirement=criterion['requirement']))
        if record.get('source_revision') != source_revision and record.get('status') != 'not_run':
            record.update(status='not_run', stale=True, next_action='Source changed since this result; verify again.', owner='builder')
        out[criterion['id']] = record
    return out


def outcome(results):
    statuses = {r['status'] for r in results.values()}
    if not results:
        return 'not_run'
    if 'failed' in statuses:
        return 'failed'
    if 'not_run' in statuses:
        return 'not_run'
    if 'pending_owner' in statuses:
        return 'pending_owner'
    return 'passed'


def evidence_digest(root, folder):
    """Hash evidence contents so a resume can tell new evidence from a repeat."""
    digest = hashlib.sha256()
    base = safe_path(Path(root), folder)
    if base.is_dir():
        for p in sorted(base.rglob('*')):
            if p.is_file() and not p.is_symlink():
                digest.update(str(p.relative_to(base)).encode())
                digest.update(p.read_bytes())
    return digest.hexdigest()


def spec_digest(root):
    path = safe_path(Path(root), SPEC)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
