"""Summarise a project's run from its files, for comparing engines fairly.

    .venv/bin/python -m lyra_lite.report "~/Lyra Projects/pocket-tasks-hermes" [...more]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from lyra_lite.store import ProjectStore


def summarise(root: Path) -> dict:
    store = ProjectStore(root)
    events, _ = store.read_events(0)
    starts = [e for e in events if e["type"] == "turn_start"]
    ends = [e for e in events if e["type"] == "turn_end"]
    kinds: dict[str, int] = {}
    for e in starts:
        kinds[e.get("kind", "user")] = kinds.get(e.get("kind", "user"), 0) + 1
    busy = 0.0
    by_turn = {e.get("turn"): e["ts"] for e in starts}
    for e in ends:
        if e.get("turn") in by_turn:
            busy += e["ts"] - by_turn[e["turn"]]
    cost = sum(float((e.get("usage") or {}).get("cost_usd") or 0) for e in ends)
    calls = sum(int((e.get("usage") or {}).get("api_calls") or 0) for e in ends)
    try:
        commits = int(subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=root,
                                     capture_output=True, text=True).stdout.strip() or 0)
    except Exception:
        commits = 0
    return {
        "project": root.name,
        "engine": store.state().get("engine") or "hermes",
        "wall_hours": round((events[-1]["ts"] - events[0]["ts"]) / 3600, 2) if events else 0,
        "working_hours": round(busy / 3600, 2),
        "owner_messages": kinds.get("user", 0),
        "watchdog_nudges": kinds.get("watchdog", 0),
        "helper_reports": kinds.get("helper_done", 0),
        "agents_started": sum(1 for e in events if e["type"] == "helper" and e.get("event") in {"start", "spawn_requested"}),
        "approvals_asked": sum(1 for e in events if e["type"] == "inbox"),
        "errors": sum(1 for e in ends if e.get("status") in {"error", "crashed"}),
        "lost_on_restart": sum(1 for e in ends if e.get("status") == "lost_on_restart"),
        "watchdog_gave_up": sum(1 for e in events if e["type"] == "watchdog" and e.get("action") == "gave_up"),
        "model_calls": calls,
        "cost_usd": round(cost, 2),
        "commits": commits,
    }


def main(argv: list[str]) -> None:
    rows = [summarise(Path(a).expanduser().resolve()) for a in argv]
    if not rows:
        print(__doc__)
        return
    keys = list(rows[0])
    width = max(len(k) for k in keys)
    for key in keys:
        print(f"{key:<{width}}  " + "  ".join(f"{str(r[key]):>22}" for r in rows))


if __name__ == "__main__":
    main(sys.argv[1:])
