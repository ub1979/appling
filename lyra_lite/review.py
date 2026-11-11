"""Workspace evidence for update cycles and owner review checkpoints."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

from lyra_lite.preview import PREVIEW_TYPES, _built, prototype_root
from lyra_lite.project_map import read_map

PROTOTYPE_CHOICES = ("Approve prototype", "Request changes")
REQUIREMENTS_CHOICES = ("Approve requirements", "Request changes")
_STATUS = re.compile(r"(?im)^\s*\*{0,2}status\*{0,2}:\*{0,2}[^\n]*\n?")


def visual_project(root: Path, state: dict) -> bool:
    return state.get("project_kind") in {"app", "website", "slides", "video"} or (
        prototype_root(root) is not None or (root / "index.html").is_file() or _built(root) is not None
    )


def requirements_revision(root: Path) -> str | None:
    try:
        text = (root / "requirements.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    draft = _STATUS.sub("", text, count=1).strip()
    return hashlib.sha256(draft.encode()).hexdigest() if draft else None


def prototype_revision(root: Path) -> str | None:
    base = prototype_root(root)
    if base is None:
        return None
    digest = hashlib.sha256()
    for path in sorted(base.rglob("*")):
        if path.suffix.lower() not in PREVIEW_TYPES or path.is_symlink():
            continue
        try:
            if path.is_file():
                stat = path.stat()
                digest.update(repr((path.relative_to(base).as_posix(), stat.st_size, stat.st_mtime_ns)).encode())
        except OSError:
            return None
    return digest.hexdigest()


def built_project(root: Path, ledger: dict | None = None) -> bool:
    """Recognise delivered Appling projects and common imported app layouts."""
    ledger = ledger if ledger is not None else read_map(root)
    if ledger.get("delivery_complete") or any(
        row["state"] == "done" and re.search(r"\b(build|implementation|development)\b", row["name"], re.I)
        for row in ledger["phases"]
    ):
        return True
    if _built(root) or (root / "index.html").is_file():
        return True
    manifests = ("package.json", "pyproject.toml", "Cargo.toml", "go.mod", "pubspec.yaml", "Package.swift")
    entrypoints = ("src", "app", "pages", "lib", "main.py", "app.py", "main.go", "server.js",
                   "index.js", "App.js", "App.tsx", "Sources")
    return any((root / name).is_file() for name in manifests) and any(
        (root / name).exists() for name in entrypoints
    )


def active_update(root: Path, state: dict, ledger: dict | None = None) -> dict | None:
    update = state.get("update")
    if not update:
        return None
    ledger = ledger if ledger is not None else read_map(root)
    if ledger.get("delivery_complete") and ledger.get("delivery_revision") == str(update["revision"]):
        return None
    return update


def next_revision(ledger: dict, state: dict) -> int:
    versions = [int(v) for v in re.findall(
        r"(?im)^\s*(?:#{1,6}|\|)\s*(?:revision\s+|version\s+|v)(\d+)",
        ledger.get("markdown") or "",
    )]
    return max([1, (state.get("update") or {}).get("revision", 1), *versions]) + 1


def create_update_branch(root: Path, branch: str) -> None:
    if not branch or branch.startswith("-") or branch == "HEAD" or len(branch) > 180:
        raise RuntimeError("Enter a valid new Git branch name.")
    try:
        valid = subprocess.run(["git", "check-ref-format", f"refs/heads/{branch}"],
                               cwd=root, capture_output=True, check=False, timeout=10)
        if valid.returncode:
            raise RuntimeError("Enter a valid new Git branch name, such as appling/update-2.")
        result = subprocess.run(["git", "switch", "-c", branch], cwd=root,
                                capture_output=True, text=True, check=False, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Could not create the Git branch: {exc}") from exc
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Could not create the Git branch.")


def change_report(root: Path, update: dict, requirements: str) -> Path:
    return root / ".sdlc" / "changes" / f"v{update['revision']}-{requirements[:12]}.md"


def change_review_ready(path: Path) -> bool:
    try:
        with path.open(encoding="utf-8") as file:
            return bool(re.fullmatch(r"(?:\*\*)?Status(?:\*\*)?:(?:\*\*)?\s*Ready",
                                     file.readline().strip(), re.I))
    except (OSError, UnicodeError):
        return False
