"""Workspace evidence for update cycles and owner review checkpoints."""

from __future__ import annotations

import hashlib
import re
import subprocess
import time
from pathlib import Path

from lyra_lite.preview import PREVIEW_TYPES, _built, prototype_root
from lyra_lite.project_map import read_map

PROTOTYPE_CHOICES = ("Approve prototype", "Request changes")
REQUIREMENTS_CHOICES = ("Approve requirements", "Request changes")
PLAN_CHOICES = ("Approve implementation plan", "Request changes")
_STATUS = re.compile(r"(?im)^\s*\*{0,2}status\*{0,2}:\*{0,2}[^\n]*\n?")


def requests_plan_approval(question: str, choices) -> bool:
    return any(re.search(r"\bapprove\s+(?:the\s+)?(?:implementation\s+|task\s+)?plan\b", str(c), re.I)
               for c in choices or []) or bool(re.search(
                   r"\b(?:do you|can you|would you|please)\s+(?:like to\s+)?approve\b[^?\n]{0,120}\bplan\b",
                   str(question), re.I))


def implementation_plan(root: Path) -> dict | None:
    for name in (".sdlc/task-graph.md", ".sdlc/implementation-plan.md", "implementation-plan.md", "plan.md"):
        try:
            text = (root / name).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        content = requirements_content(text)
        if content:
            return {"path": name, "text": text, "revision": hashlib.sha256(content.encode()).hexdigest()}
    return None


def visual_project(root: Path, state: dict) -> bool:
    return state.get("project_kind") in {"app", "website", "slides", "video"} or (
        prototype_root(root) is not None or (root / "index.html").is_file() or _built(root) is not None
    )


def requirements_content(text: str) -> str:
    """Approval bookkeeping is metadata; product and verification sections are not."""
    text = _STATUS.sub("", text, count=1)
    lines = []
    skip_level = None
    fence = None
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            fence = None if fence == marker else marker if fence is None else fence
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line) if fence is None else None
        if heading:
            level = len(heading[1])
            if skip_level is not None and level <= skip_level:
                skip_level = None
            if heading[2].strip().casefold() == "approval gates and current state":
                skip_level = level
                continue
        if skip_level is None:
            lines.append(line)
    return "\n".join(lines).strip()


def requirements_revision(root: Path) -> str | None:
    try:
        text = (root / "requirements.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    draft = requirements_content(text)
    return hashlib.sha256(draft.encode()).hexdigest() if draft else None


def plan_execution_started(state: dict) -> bool:
    execution = state.get("plan_execution") or {}
    return bool(state.get("plan_approved") and not state.get("requirements_review")
                and execution.get("plan") == state["plan_approved"]
                and execution.get("requirements") == state.get("requirements_approved")
                == state.get("plan_requirements"))


def record_plan_execution(store, goal: str) -> None:
    """Latch the approved baseline when real development starts, not on edits."""
    from lyra_lite.agents import agent_for_goal

    if agent_for_goal(goal) != "sw-developer":
        return
    with store._lock:
        state = store.state()
        if (not state.get("plan_approved") or state.get("requirements_review")
                or not state.get("plan_requirements")
                or state["plan_requirements"] != state.get("requirements_approved")
                or state["plan_requirements"] != requirements_revision(store.root)
                or plan_execution_started(state)):
            return
        plan = implementation_plan(store.root)
        if not plan or plan["revision"] != state["plan_approved"]:
            return
        store.update_state(plan_execution={"plan": state["plan_approved"],
                                           "requirements": state["plan_requirements"]})


def reconcile_plan_execution(store) -> None:
    """Recover legacy execution only from an answered approval followed by a start."""
    state = store.state()
    if plan_execution_started(state) or not state.get("plan_approved"):
        return
    approved = [i for i in store.inbox() if i.get("kind") == "plan" and i.get("status") == "answered"
                and i.get("answer") == PLAN_CHOICES[0] and i.get("revision") == state["plan_approved"]
                and i.get("requirements") == state.get("plan_requirements")
                and i.get("chat_id") == state.get("chat_id")]
    if (not approved or state.get("requirements_review") or not state.get("plan_requirements")
            or state["plan_requirements"] != state.get("requirements_approved")
            or state["plan_requirements"] != requirements_revision(store.root)):
        return
    after = max(i.get("closed", i.get("created", 0)) for i in approved)
    events, _ = store.read_events(0)
    from lyra_lite.agents import agent_for_goal

    for event in events:
        if (event.get("ts", 0) >= after and event.get("type") == "helper" and event.get("event") == "start"
                and agent_for_goal(str(event.get("goal") or "")) == "sw-developer"):
            # The old plan no longer needs to match today's engineering
            # notes: the persisted approval/start pair proves the baseline.
            store.update_state(plan_execution={"plan": state["plan_approved"],
                                               "requirements": state["plan_requirements"]})
            return


def reconcile_requirements_approval(store) -> bool:
    """Migrate a proven legacy approval without accepting any product changes."""
    state = store.state()
    approved = state.get("requirements_approved")
    current = requirements_revision(store.root)
    if not approved or not current or approved == current:
        return False
    if state.get("requirements_revision_format") == 2:
        return False
    try:
        text = (store.root / "requirements.md").read_text(encoding="utf-8")
        candidates = [text]
        history = subprocess.run(["git", "log", "-40", "--format=%H", "--", "requirements.md"],
                                 cwd=store.root, capture_output=True, text=True, timeout=3)
        deadline = time.monotonic() + 3
        for commit in history.stdout.splitlines():
            if time.monotonic() >= deadline:
                break
            result = subprocess.run(["git", "show", f"{commit}:requirements.md"], cwd=store.root,
                                    capture_output=True, text=True, timeout=1)
            if result.returncode == 0:
                candidates.append(result.stdout)
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        return False
    for candidate in candidates:
        legacy = hashlib.sha256(_STATUS.sub("", candidate, count=1).strip().encode()).hexdigest()
        if legacy == approved and requirements_content(candidate) == requirements_content(text):
            store.update_state(requirements_approved=current, requirements_revision_format=2)
            store.append_event("approval_reconciled", kind="requirements")
            return True
    return False


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
