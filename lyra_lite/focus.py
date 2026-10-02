"""The focus note: where the project stands, attached to Appling's messages.

Long chats get summarised and details fade. The project's own files do not:
this note is rebuilt from them (the progress ledger and the Project Brain's
next-actions and open-questions sections) and attached to the message Appling
receives, so she always sees the current state — however old the chat is.
It costs no model call and is only re-sent when the state changes (or every
few turns as a reminder).
"""

from __future__ import annotations

import re
from pathlib import Path

from lyra_lite.project_map import read_map

MAX_CHARS = 1500
BRAIN = Path(".sdlc") / "project-brain.md"
_SECTION_WORDS = ("next", "open", "risk", "question", "current")


def _brain_sections(root: Path) -> list[str]:
    try:
        text = (root / BRAIN).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out, take, taken = [], False, 0
    for line in text.splitlines():
        heading = re.match(r"^#{1,4}\s+(.*)$", line)
        if heading:
            take = any(w in heading.group(1).lower() for w in _SECTION_WORDS)
            taken = 0
            if take:
                out.append(f"{heading.group(1).strip()}:")
            continue
        if take and line.strip() and taken < 6:
            out.append("  " + line.strip()[:200])
            taken += 1
    return out


def focus_note(root: Path, open_inbox: int = 0) -> str:
    root = Path(root)
    lines: list[str] = []
    ledger = read_map(root)
    if ledger.get("current_phase"):
        lines.append(f"Current step: {ledger['current_phase']}")
    unfinished = [p for p in ledger.get("phases", []) if p["state"] != "done"]
    done = [p["name"] for p in ledger.get("phases", []) if p["state"] == "done"]
    if done:
        lines.append("Done: " + ", ".join(done[:10]))
    for p in unfinished[:6]:
        lines.append(f"Not done: {p['name']} — {p['status'][:120]}")
    lines.extend(_brain_sections(root))
    if open_inbox:
        lines.append(f"Waiting on the owner: {open_inbox} open question(s)/approval(s) in the inbox.")
    if not lines:
        return ""
    body = "\n".join(lines)
    if len(body) > MAX_CHARS:
        body = body[: MAX_CHARS - 1] + "…"
    return ("[Project focus — current state from the project files; trust it over older chat. "
            "Use project_recall for details.]\n" + body)
