"""The project map, read straight from the project's own ledger.

``.sdlc/progress.md`` is the durable record the builder skills keep. Its
Phase/status tables provide the current rows; superseded records remain in
``history`` and in the unmodified Markdown. Delivery closes only earlier rows
in the same table and revision, never unrelated or subsequently added work.
"""

from __future__ import annotations

import re
from pathlib import Path

LEDGER = Path(".sdlc") / "progress.md"
_MAX_BYTES = 512 * 1024

_FAIL = r"fail(?:s|ed|ing|ure|ures)?"
_INCOMPLETE = re.compile(
    r"\b(incomplete|partial|pending|running|reopened|in progress"
    r"|not\s+(?:(?:yet|fully|completely|entirely)\s+)*(verified|confirmed|fixed|pass|passed)"
    rf"|unverified|open|{_FAIL})\b"
)
# Ignore only explicitly absent problems, not the rest of the status.
# For example, "0 open HIGH; 2 open MEDIUM" still contains unfinished work.
_ABSENT_WORK = re.compile(
    r"(?<![\w.+-])(?:0|zero|no|nothing)(?:\s*/\s*\d+)?\s+"
    r"(?:(?:open|pending|tests?|checks?)\s+)?"
    rf"(?:open|pending|awaiting|running|incomplete|partial|unverified|blocked|{_FAIL})\b"
    rf"|\b(?:not|no\s+longer)\s+(?:open|pending|awaiting|running|blocked|{_FAIL})\b"
    rf"|\b(?:open|pending|{_FAIL})(?:\s+(?:tests|checks))?\s*[:=]\s*0(?![\w.])"
)
# A historical problem is not necessarily resolved. Require an explicit fix
# in the same clause, and keep the problem if that clause still qualifies it.
_RESOLVED_PAST = re.compile(
    rf"\bpreviously\s+(?:open|pending|running|blocked|{_FAIL})\b"
    r"(?=[^.;\n]*\b(?:fixed|resolved|closed)\b)"
    r"(?![^.;\n]*\b(?:not|unresolved|broken|remain(?:s|ing)?)\b)"
)
_OWNER_WAIT = re.compile(r"\bawaiting\b[^.;\n]*\bowner\b|\bowner\b[^.;\n]*\bawaiting\b")
_DONE = re.compile(r"\b(verified|approved|confirmed|fixed|complete|completed|done|integrated|pass|passed)\b")
# Closed dispositions finish a row too. Require a leading status label so
# negations ("not resolved") and incidental mentions do not close open work.
_CLOSED = re.compile(r"^(resolved|superseded|descoped|delivered|handed off)\b")


def _status_text(status: str) -> str:
    text = _ABSENT_WORK.sub("", status.strip().lower())
    return _RESOLVED_PAST.sub("", text).strip()


def row_state(status: str) -> str:
    """done (including closed work) | running | owner | blocked | pending."""
    text = _status_text(status)
    incomplete = bool(_INCOMPLETE.search(text))
    if re.search(r"\bblocked\b", text):
        return "owner" if "owner" in text else "blocked"
    if _OWNER_WAIT.search(text):
        return "owner"
    # "partially fixed/complete" is not done, but it is not running either.
    partly = bool(re.search(r"\bpartially\b", text))
    if (_DONE.search(text) or _CLOSED.match(text)) and not incomplete and not partly:
        return "done"
    if incomplete and "owner" in text:
        return "owner"
    if incomplete and not text.startswith("pending"):
        return "running"
    return "pending"


def _cells(line: str) -> list[str]:
    parts = line.strip().split("|")[1:-1]
    return [re.sub(r"[`*_]", "", cell).strip() for cell in parts]


def _revision(label: str) -> tuple[str | None, str]:
    """Explicit revision prefixes identify scope, not arbitrary phase words."""
    label = re.sub(r"\s+", " ", label.strip().lower())
    match = re.match(
        r"^(?:v|rev(?:ision)?\.?\s*|version\s+)(\d+(?:\.\d+)*)(?:\b|$)[\s:—–-]*", label)
    return (match.group(1), label[match.end():]) if match else (None, label)


def _is_delivery(row: dict) -> bool:
    if row["state"] != "done":
        return False
    _, name = _revision(row["name"])
    status = _status_text(row["status"])
    # Removing/replacing the delivery task is not evidence of delivery.
    if re.match(r"^(resolved|superseded|descoped)\b", status):
        return False
    # A component being handed to another agent is not a project handoff.
    if re.search(r"\b(not|pending|partial|awaiting)\b|\bhanded off to\b", status):
        return False
    delivery_labels = {"delivery", "final delivery", "handoff", "final handoff",
                       "owner approval + delivery", "owner approval and delivery"}
    if name in delivery_labels:
        return True
    # Baseline/version summary rows must explicitly say delivered or handed
    # off. Ordinary tasks such as "Documentation | delivered" do not
    # certify completion of the other phases.
    return (name in {"baseline", "project", "app", "application", "release", "delta", ""}
            and bool(re.search(r"\b(delivered|handed off)\b", status)))


def _current_rows(entries: list[tuple[dict, int, str | None]]) -> tuple[list, list, bool]:
    active: set[int] = set()
    latest: dict[tuple, int] = {}
    for i, (row, table, scope) in enumerate(entries):
        key = (table, scope, row["name"].casefold())
        previous = latest.get(key)
        if previous is not None:
            active.discard(previous)
        latest[key] = i
        if _is_delivery(row):
            for prior in list(active):
                old, old_table, old_scope = entries[prior]
                if ((old_table, old_scope) == (table, scope)
                        and old["state"] != "done"
                        and not re.search(r"\breopened\b", old["status"], re.I)):
                    active.remove(prior)
        active.add(i)
    current = [row for i, (row, _, _) in enumerate(entries) if i in active]
    history = [row for i, (row, _, _) in enumerate(entries) if i not in active]
    delivered = any(_is_delivery(row) for row in current) and all(row["state"] == "done" for row in current)
    return current, history, delivered


def read_map(root: Path) -> dict:
    path = Path(root) / LEDGER
    try:
        stat = path.stat()
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read(_MAX_BYTES)
    except OSError:
        return {"exists": False, "phases": [], "current_phase": None, "updated": None}

    entries: list[tuple[dict, int, str | None]] = []
    current_phase = updated = None
    columns: dict[str, int] = {}
    headings: list[tuple[int, str | None]] = []
    table = 0
    for line in text.splitlines():
        header = re.match(r"^(#{1,6})\s+(.*)$", line)
        if header:
            columns = {}
            level = len(header.group(1))
            while headings and headings[-1][0] >= level:
                headings.pop()
            scope = _revision(header.group(2))[0]
            headings.append((level, scope or (headings[-1][1] if headings else None)))
            continue
        meta = re.match(r"^(Current phase|Updated):\s*(.+)$", line.strip(), re.I)
        if meta:
            if meta.group(1).lower() == "updated":
                updated = meta.group(2).strip()
            else:
                current_phase = meta.group(2).strip()
            continue
        if not line.strip().startswith("|"):
            columns = {}
            continue
        cells = _cells(line)
        names = {cell.lower(): i for i, cell in enumerate(cells)}
        if "phase" in names and "status" in names:
            columns = names
            table += 1
            continue
        if not columns or not cells or all(re.fullmatch(r":?-+:?", c) for c in cells):
            continue
        if len(cells) <= max(columns["phase"], columns["status"]):
            continue
        notes = [cells[i] for label, i in columns.items()
                 if re.search(r"\b(evidence|notes?)\b", label) and i < len(cells) and cells[i]]
        status = cells[columns["status"]]
        row = {
            "name": cells[columns["phase"]],
            "status": status,
            "state": row_state(status),
            "note": " — ".join(notes),
        }
        scope = _revision(row["name"])[0] or (headings[-1][1] if headings else None)
        entries.append((row, table, scope))
    phases, history, delivered = _current_rows(entries)
    return {
        "exists": True,
        "phases": phases,
        "history": history,
        "delivery_complete": delivered,
        "current_phase": "Delivered" if delivered else current_phase,
        "updated": updated,
        "mtime": stat.st_mtime,
        "markdown": text,
    }
