"""Milestone checkpoints on the project branch that leave the owner's Git state alone.

Unlike `workspaces.snapshot` (private, unreferenced commits for worker
isolation), a checkpoint becomes a real commit on the current branch:

* staged in a temporary index, so the owner's index is never rewritten wholesale;
* ignored files are skipped, and a denylist keeps secrets, databases, virtual
  environments, build output, model weights, large binaries and run evidence
  (`.sdlc/evidence/`) out even when ignore rules miss them;
* the branch moves only by compare-and-swap from the HEAD the snapshot was based
  on, otherwise the commit is kept under refs/appling/checkpoints/<label>;
* afterwards, paths the owner had not staged are synced in their real index so
  `git status` does not show the checkpoint as staged reversals. Paths the
  owner had staged keep their staged contents.
"""
from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import tempfile
from pathlib import Path, PurePosixPath

MAX_BYTES = 20 * 1024 * 1024
DENY_DIRS = {'.git', '.appling', 'node_modules', '.venv', 'venv', '__pycache__', 'dist', 'build', 'out',
             '.local-data', 'coverage', 'test-results', 'playwright-report', '.next', '.turbo', '.cache'}
DENY_FILES = ['.env', '.env.*', '*.pem', '*.key', '*.p12', '*.pfx', 'id_rsa*', 'id_ed25519*', 'credentials*.json',
              'token*.json', '*.sqlite', '*.sqlite3', '*.sqlite-*', '*.db', '*.safetensors', '*.gguf', '*.onnx',
              '*.pt', '*.pth', '*.ckpt', '*.bin', '*.wav', '*.mp4', '*.mov']
ALLOW_FILES = ['.env.example', '.env.sample', '.env.template']


DENY_PREFIXES = ('.sdlc/evidence/',)   # run logs/screenshots may hold account data; results bind to source, not evidence


def denied(name, root=None):
    if name.startswith(DENY_PREFIXES):
        return True
    parts = PurePosixPath(name).parts
    if any(p in DENY_DIRS for p in parts[:-1]):
        return True
    base = parts[-1] if parts else name
    if any(fnmatch.fnmatch(base, pattern) for pattern in ALLOW_FILES):
        return False
    if any(fnmatch.fnmatch(base, pattern) for pattern in DENY_FILES):
        return True
    if root is not None:
        path = Path(root) / name
        try:
            if path.is_symlink():
                # A link into private storage (e.g. a shared model folder) is not source.
                target = os.path.realpath(path)
                if not Path(target).is_relative_to(Path(root).resolve()):
                    return True
            elif path.is_file() and path.stat().st_size > MAX_BYTES:
                return True
        except OSError:
            return True
    return False


def _git(root, *args, env=None, input=None, check=True):
    result = subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '--literal-pathspecs', *args], cwd=root,
                            env=env, input=input, capture_output=True)
    if check and result.returncode:
        raise RuntimeError('Checkpoint failed: ' + result.stderr.decode(errors='replace')[-800:])
    return result


def _out(root, *args, env=None, check=True):
    return _git(root, *args, env=env, check=check).stdout.decode(errors='replace').strip()


def _names(raw):
    return [os.fsdecode(n) for n in raw.split(b'\0') if n]


def label_for(text):
    return re.sub(r'[^A-Za-z0-9_.-]+', '-', text).strip('-.')[:60] or 'project'


def checkpoint(root, message, label='project'):
    """Commit current eligible work; return details, or None when not a Git repository."""
    root = Path(root).resolve()
    if not (root / '.git').exists():
        return None
    head = _out(root, 'rev-parse', '-q', '--verify', 'HEAD', check=False) or None
    branch = _out(root, 'symbolic-ref', '-q', 'HEAD', check=False) or None
    identity = {}
    if not _out(root, 'config', 'user.email', check=False):
        identity = dict(GIT_AUTHOR_NAME='Appling', GIT_AUTHOR_EMAIL='checkpoint@appling.local',
                        GIT_COMMITTER_NAME='Appling', GIT_COMMITTER_EMAIL='checkpoint@appling.local')
    with tempfile.TemporaryDirectory(prefix='appling-checkpoint-') as folder:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(folder) / 'index'), **identity)
        if head:
            _git(root, 'read-tree', head, env=env)
        else:
            _git(root, 'read-tree', '--empty', env=env)
        # Tracked files (from HEAD) plus untracked files that ignore rules allow.
        names = _names(_git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard', env=env).stdout)
        add, remove, skipped = [], [], []
        for name in names:
            path = root / name
            exists = path.exists() or path.is_symlink()
            if not exists:
                remove.append(name)
            elif denied(name, root):
                skipped.append(name)
            else:
                add.append(name)
        if add:
            _git(root, 'add', '--force', '--pathspec-from-file=-', '--pathspec-file-nul', env=env,
                 input=b'\0'.join(os.fsencode(n) for n in add) + b'\0')
        if remove:
            _git(root, 'rm', '--cached', '-q', '--ignore-unmatch', '--pathspec-from-file=-', '--pathspec-file-nul', env=env,
                 input=b'\0'.join(os.fsencode(n) for n in remove) + b'\0')
        tree = _out(root, 'write-tree', env=env)
    if head and tree == _out(root, 'rev-parse', head + '^{tree}'):
        return dict(commit=head, changed=False, ref=branch, skipped=skipped)
    commit = _out(root, 'commit-tree', tree, *(['-p', head] if head else []), '-m', message, env=dict(os.environ, **identity))
    changed_paths = _names(_git(root, 'diff', '--name-only', '-z', '--no-renames', head or _empty_tree(root), commit).stdout)
    if branch:
        staged = set(_names(_git(root, 'diff', '--cached', '--name-only', '-z', '--no-renames', *( [head] if head else []),
                                 check=False).stdout)) if head else set()
        moved = _git(root, 'update-ref', '-m', 'appling checkpoint', branch, commit, head or '0' * 40, check=False)
        if moved.returncode == 0:
            sync = [p for p in changed_paths if p not in staged]
            if sync:
                # Point unstaged index entries at the checkpoint; leave owner-staged ones.
                _git(root, 'reset', '-q', commit, '--pathspec-from-file=-', '--pathspec-file-nul',
                     input=b'\0'.join(os.fsencode(n) for n in sync) + b'\0', check=False)
            return dict(commit=commit, changed=True, ref=branch, branch_updated=True, paths=len(changed_paths), skipped=skipped)
    ref = 'refs/appling/checkpoints/' + label_for(label)
    _git(root, 'update-ref', '-m', 'appling checkpoint', ref, commit)
    return dict(commit=commit, changed=True, ref=ref, branch_updated=False, paths=len(changed_paths), skipped=skipped,
                note='The branch is detached or moved during the checkpoint; the commit is kept under ' + ref + '.')


def _empty_tree(root):
    return _git(root, 'hash-object', '-t', 'tree', '--stdin', input=b'').stdout.decode().strip()
