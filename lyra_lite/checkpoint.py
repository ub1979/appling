"""Automatic checkpoint commits for builder projects.

A specialist that stops (finished, cut off at its step limit, or failed) used
to leave its edits uncommitted unless the coordinator remembered to commit.
Several helpers in a row could pile up dozens of unrecorded files, and a lost
chat or a crash meant nobody knew what state they were in. After every
specialist finishes, this records whatever it left in the project's own Git
history as a clearly labelled checkpoint, so no work is ever lost. The
coordinator still makes its own verified commits; checkpoints are the net.

Guard rails:
- only builder projects (a ``.sdlc/`` folder) that are the top of their own
  Git repository — never a parent repository such as Lyra's own checkout;
- files that look like secrets are never staged;
- Git errors are logged and swallowed: a checkpoint must never break a turn.
"""

from __future__ import annotations

import fnmatch
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_GIT_TIMEOUT_SECONDS = 30
_MAX_MESSAGE_GOAL_CHARS = 72

# Never staged by a checkpoint, even when .gitignore misses them.
_SECRET_PATTERNS = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "id_ed25519*",
    "*credentials*.json",
    "*secret*",
    "*.keychain*",
)
_SECRET_ALLOWED = (".env.example", ".env.sample", ".env.template")


def _git(project: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(project), *args],
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_SECONDS,
        check=False,
    )


def _looks_secret(path: str) -> bool:
    name = Path(path).name
    if name in _SECRET_ALLOWED:
        return False
    return any(fnmatch.fnmatch(name, pattern) for pattern in _SECRET_PATTERNS)


def _owns_its_repository(project: Path) -> bool:
    top = _git(project, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        return False
    try:
        return Path(top.stdout.strip()).resolve() == project.resolve()
    except OSError:
        return False


def _changed_paths(project: Path) -> list[str]:
    status = _git(project, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if status.returncode != 0:
        return []
    paths: list[str] = []
    entries = status.stdout.split("\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        paths.append(path)
        if "R" in code or "C" in code:
            index += 1  # skip the rename/copy source path
    return paths


def _message(role: Optional[str], status: Optional[str],
             exit_reason: Optional[str], goal: Optional[str]) -> str:
    who = (role or "specialist").strip() or "specialist"
    how = "cut off at its step limit" if exit_reason == "max_iterations" else (
        status or "finished"
    )
    subject = f"checkpoint: {who} {how} (auto-saved by Lyra)"
    goal_line = " ".join((goal or "").split())
    if len(goal_line) > _MAX_MESSAGE_GOAL_CHARS:
        goal_line = goal_line[: _MAX_MESSAGE_GOAL_CHARS - 1] + "…"
    body = (
        "Recorded automatically after a helper stopped so its work is not lost.\n"
        "It may be unverified; a later commit from Lyra should confirm it."
    )
    if goal_line:
        body = f"Task: {goal_line}\n\n{body}"
    return f"{subject}\n\n{body}"


def checkpoint_project(
    workspace: Optional[str],
    *,
    role: Optional[str] = None,
    status: Optional[str] = None,
    exit_reason: Optional[str] = None,
    goal: Optional[str] = None,
) -> Optional[str]:
    """Commit a builder project's pending changes. Returns the commit id, or None."""
    if not workspace:
        return None
    try:
        project = Path(workspace).expanduser().resolve(strict=True)
    except OSError:
        return None
    if not (project / ".sdlc").is_dir() or not _owns_its_repository(project):
        return None

    try:
        paths = [path for path in _changed_paths(project) if not _looks_secret(path)]
        if not paths:
            return None
        added = _git(project, "add", "--all", "--", *paths)
        if added.returncode != 0:
            logger.warning("Checkpoint staging failed in %s: %s", project, added.stderr.strip())
            return None
        staged = _git(project, "diff", "--cached", "--quiet")
        if staged.returncode == 0:
            return None
        commit = _git(
            project, "commit", "--no-verify", "-q",
            "-m", _message(role, status, exit_reason, goal),
        )
        if commit.returncode != 0:
            logger.warning("Checkpoint commit failed in %s: %s", project, commit.stderr.strip())
            return None
        head = _git(project, "rev-parse", "--short", "HEAD")
        commit_id = head.stdout.strip() or None
        logger.info("Checkpoint %s recorded %d path(s) in %s", commit_id, len(paths), project)
        return commit_id
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Checkpoint skipped in %s: %s", project, exc)
        return None


def on_subagent_stop(**kwargs) -> None:
    """``subagent_stop`` hook: checkpoint the project the helper worked in."""
    checkpoint_project(
        kwargs.get("workspace"),
        role=kwargs.get("child_role"),
        status=kwargs.get("child_status"),
        exit_reason=kwargs.get("child_exit_reason"),
        goal=kwargs.get("child_goal"),
    )
