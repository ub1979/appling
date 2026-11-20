"""Private Git snapshots and isolated task worktrees; never commit the user's index."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path, PurePosixPath

from .store import safe_path


EXCLUDED_DIRS = {'.git', '.appling', 'node_modules', '.venv', '__pycache__', 'dist', 'build', 'out'}


def eligible(name):
    return not any(p in EXCLUDED_DIRS or p.startswith('.env') for p in Path(name).parts)


def git(root, *args, env=None, binary=False, input=None):
    result = subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', *args], cwd=root,
                            env=env, input=input, capture_output=True, text=not binary)
    if result.returncode:
        message = result.stderr.decode(errors='replace') if binary else result.stderr
        raise RuntimeError('Git workspace operation failed: ' + message[-1500:])
    return result.stdout if binary else result.stdout.strip()


def ownership(files):
    if not isinstance(files, list) or any(not isinstance(p, str) for p in files):
        raise ValueError('Task files must be a list of relative files or folders ending in /.')
    result = []
    for value in files:
        path = PurePosixPath(value)
        if (not value or value.startswith('/') or '\\' in value or
                any(p in {'.', '..', '.git', '.appling'} for p in value.rstrip('/').split('/')) or
                any(c in value for c in '*?[]:') or str(path) == '.'):
            raise ValueError('Task ownership needs plain project-relative files or folders.')
        result.append(value)
    return list(dict.fromkeys(result))


def owns(scopes, name):
    return any(name == scope.rstrip('/') or scope.endswith('/') and name.startswith(scope) for scope in scopes)


def independent(left, right):
    """Unknown ownership is serial; overlapping directories/files are serial."""
    a, b = left.get('files', []), right.get('files', [])
    return bool(a and b) and not any(owns([x], y.rstrip('/')) or owns([y], x.rstrip('/')) for x in a for y in b)


def snapshot(root, parent=None, include=()):
    """Capture eligible working files with a disposable index, including untracked work."""
    root = Path(root).resolve()
    if not (root / '.git').exists():
        git(root, 'init', '-b', 'main')
    with tempfile.TemporaryDirectory(prefix='appling-index-') as folder:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(folder) / 'index'),
                   GIT_AUTHOR_NAME='Appling Worker', GIT_AUTHOR_EMAIL='worker@appling.local',
                   GIT_COMMITTER_NAME='Appling Worker', GIT_COMMITTER_EMAIL='worker@appling.local')
        # Enumerate from the real index, respecting ignores only for untracked
        # files. Negative pathspecs passed to `add .` can themselves trigger Git's
        # ignored-path error. Stage only eligible literal names into our index.
        names={os.fsdecode(p) for p in git(root,'ls-files','--cached','--others',
            '--exclude-standard','-z',binary=True).split(b'\0') if p}
        for name in ['requirements.md', 'plan.md', 'prototypes', *include]:
            path = safe_path(root, name)
            if path.is_dir():
                for base,dirs,files in os.walk(path):
                    dirs[:]=[d for d in dirs if eligible(str((Path(base)/d).relative_to(root)))]
                    names.update(str((Path(base)/f).relative_to(root)) for f in files)
            elif path.exists() or path.is_symlink():names.add(str(path.relative_to(root)))
        selected=[os.fsencode(name) for name in sorted(names) if eligible(name)
                  and ((root/name).exists() or (root/name).is_symlink())]
        if selected:
            git(root,'--literal-pathspecs','add','--force','--pathspec-from-file=-','--pathspec-file-nul',
                env=env,binary=True,input=b'\0'.join(selected)+b'\0')
        tree = git(root, 'write-tree', env=env)
        return git(root, 'commit-tree', tree, *(['-p', parent] if parent else []),
                   '-m', 'Appling private task snapshot', env=env)


def create(root, directory, base):
    directory = Path(directory)
    directory.parent.mkdir(parents=True, exist_ok=True)
    git(root, 'worktree', 'add', '--detach', str(directory), base)


def changes(workspace, base, commit):
    raw = git(workspace, 'diff', '--no-renames', '--name-only', '-z', base, commit, binary=True)
    return [p.decode('utf-8') for p in raw.split(b'\0') if p]


def added(workspace, base, commit):
    raw = git(workspace, 'diff', '--no-renames', '--name-only', '--diff-filter=A', '-z', base, commit, binary=True)
    return [p.decode('utf-8') for p in raw.split(b'\0') if p]


def matches(root, commit, name):
    """Compare working bytes and executable bit with a Git tree entry."""
    path=Path(root)/name
    entry=git(root,'ls-tree',commit,'--',name)
    if not entry:return not path.exists() and not path.is_symlink()
    mode=entry.split()[0]
    return (mode in {'100644','100755'} and not path.is_symlink() and path.is_file()
            and path.read_bytes()==git(root,'show',commit+':'+name,binary=True)
            and bool(path.stat().st_mode & 0o111)==(mode=='100755'))


def patch(workspace, base, commit):
    return git(workspace, 'diff', '--no-renames', '--binary', base, commit, binary=True)


def integrate(root, workspace, base, commit, scopes, evidence, allow_applied=False):
    """Reject surprises and changed owner files before applying the entire patch."""
    root, workspace = Path(root), Path(workspace)
    names = changes(workspace, base, commit)
    for name in names:
        # safe_path rejects traversal, Git metadata and symlink escapes.
        if (root/name).is_symlink() or (workspace/name).is_symlink():
            raise ValueError('Worker symlinks require an explicit integration review: ' + name)
        current, proposed = safe_path(root, name), safe_path(workspace, name)
        if not owns([*scopes, evidence], name):
            raise ValueError('Worker changed a file outside its assigned ownership: ' + name)
        if name in {'requirements.md', 'plan.md'} or name.startswith('prototypes/') or any(part.startswith('.env') for part in Path(name).parts):
            raise ValueError('Worker changed a protected project file: ' + name)
    if allow_applied and all(matches(root,commit,name) for name in names):
        return names  # Coordinator crashed after apply but before the durable task update.
    for name in names:
        if not matches(root,base,name):
            raise ValueError('Project file changed since this worker started; its work is retained: ' + name)
    diff=patch(workspace,base,commit)
    if diff:
        git(root, 'apply', '--check', '--binary', '-', binary=True, input=diff)
        git(root, 'apply', '--binary', '-', binary=True, input=diff)
    return names


def remove(root, workspace):
    # Called only for successfully integrated work. Failures remain recoverable.
    git(root, 'worktree', 'remove', '--force', str(workspace))
