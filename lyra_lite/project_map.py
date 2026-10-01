"""The project map, read straight from the project's own ledger.

``.sdlc/progress.md`` is the durable record the builder skills keep. Its
"Phase ledger" table is shown as written, each row classified into a plain
state, so the map can never disagree with the project files.
"""

from __future__ import annotations

import re
from pathlib import Path

LEDGER = Path(".sdlc") / "progress.md"
_MAX_BYTES = 512 * 1024

_INCOMPLETE = re.compile(
    r"\b(incomplete|partial|pending|running|in progress|not (yet )?verified|unverified|open)\b"
)
_DONE = re.compile(r"\b(verified|approved|complete|completed|done|integrated|passed)\b")


def row_state(status: str) -> str:
    """done | running | owner | blocked | pending — same rules as the Studio map."""
    text = status.lower()
    incomplete = bool(_INCOMPLETE.search(text))
    if re.search(r"\bblocked\b", text):
        return "owner" if "owner" in text else "blocked"
    if _DONE.search(text) and not incomplete:
        return "done"
    if incomplete and "owner" in text:
        return "owner"
    if incomplete and not text.startswith("pending"):
        return "running"
    return "pending"


def _cells(line: str) -> list[str]:
    parts = line.strip().split("|")[1:-1]
    return [re.sub(r"[`*_]", "", cell).strip() for cell in parts]


def read_map(root: Path) -> dict:
    path = Path(root) / LEDGER
    try:
        stat = path.stat()
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read(_MAX_BYTES)
    except OSError:
        return {"exists": False, "phases": [], "current_phase": None, "updated": None}

    phases: list[dict] = []
    current_phase = updated = None
    in_ledger = in_table = False
    for line in text.splitlines():
        header = re.match(r"^#{1,6}\s+(.*)$", line)
        if header:
            # "## Phase ledger" or a titled one like "# Calculator — phase ledger".
            in_ledger = bool(re.search(r"(^|\W)phase ledger\b", header.group(1).strip(), re.I))
            continue
        if not line.strip():
            in_table = False
        meta = re.match(r"^(Current phase|Updated):\s*(.+)$", line.strip(), re.I)
        if meta:
            if meta.group(1).lower() == "updated":
                updated = meta.group(2).strip()
            else:
                current_phase = meta.group(2).strip()
            continue
        if not line.strip().startswith("|"):
            continue
        cells = _cells(line)
        if cells and cells[0].lower() == "phase":
            in_table = True  # a "| Phase | Status |" table is a ledger anywhere
            continue
        if not (in_ledger or in_table):
            continue
        if len(cells) < 2 or re.fullmatch(r":?-+:?", cells[0]):
            continue
        phases.append({
            "name": cells[0],
            "status": cells[1],
            "state": row_state(cells[1]),
            "note": cells[3] if len(cells) > 3 else "",
        })
    return {
        "exists": True,
        "phases": phases,
        "current_phase": current_phase,
        "updated": updated,
        "mtime": stat.st_mtime,
        "markdown": text,
    }
