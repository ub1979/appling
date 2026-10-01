"""Keep going: nudge an idle project that still has unfinished work.

The decision is a pure function of facts the runner gathers from files
(state, ledger, chat, git), so every rule is testable on its own. It never
nudges while the owner owes an answer, while anything is running, or after
nudges stop producing progress (no new commit and no ledger change).
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULTS = {
    "idle_minutes": 10,
    "daily_cap": 8,
    "max_no_progress": 2,
}

NUDGE = (
    "Keep going: continue with the next unfinished step in .sdlc/progress.md. "
    "Use the task plan and background agents as usual. If only the owner's "
    "decisions or actions remain, say so clearly under \"What I need from you\" "
    "and stop."
)

_OWNER_WORDS = re.compile(
    r"what i need from you|\bapprove\b|\bconfirm\b|let me know|your (call|decision|choice)"
    r"|would you like|do you want|shall i|waiting for you|reply with",
    re.I,
)


def awaits_owner(reply: str) -> bool:
    """True when the last reply hands the turn to the owner."""
    tail = (reply or "").strip()[-500:]
    if not tail:
        return False
    return tail.endswith("?") or bool(_OWNER_WORDS.search(tail))


@dataclass
class Facts:
    now: float
    keep_going: bool
    paused: bool
    busy: bool
    queued: int
    helpers: int
    open_inbox: int
    ledger_running: bool
    last_reply: str
    last_turn_end: float | None
    progress_mark: str
    nudges_today: int
    no_progress: int
    last_mark: str | None
    gave_up: bool


def decide(facts: Facts, settings: dict | None = None) -> tuple[bool, str]:
    """Return (nudge?, reason)."""
    cfg = {**DEFAULTS, **(settings or {})}
    if not facts.keep_going:
        return False, "off"
    if facts.paused:
        return False, "stopped by owner"
    if facts.busy or facts.queued or facts.helpers:
        return False, "working"
    if facts.open_inbox:
        return False, "waiting for owner answer"
    if not facts.ledger_running:
        return False, "no unfinished step in the ledger"
    if awaits_owner(facts.last_reply):
        return False, "last reply asks the owner"
    if facts.last_turn_end is None:
        return False, "no finished turn yet"
    if facts.now - facts.last_turn_end < cfg["idle_minutes"] * 60:
        return False, "recently active"
    if facts.nudges_today >= cfg["daily_cap"]:
        return False, "daily limit reached"
    if facts.gave_up:
        return False, "gave up: no progress"
    return True, "idle with unfinished work"


def progress_mark(root: Path) -> str:
    """Changes whenever the project moves: a new commit or a ledger edit."""
    head = ""
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except Exception:
        pass
    try:
        ledger = str((root / ".sdlc" / "progress.md").stat().st_mtime)
    except OSError:
        ledger = ""
    return f"{head}:{ledger}"


def today() -> str:
    return time.strftime("%Y-%m-%d")
