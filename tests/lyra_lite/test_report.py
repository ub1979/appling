from pathlib import Path

from lyra_lite.report import summarise
from lyra_lite.store import ProjectStore


def test_summary_counts_turns_by_who_started_them(tmp_path: Path):
    store = ProjectStore(tmp_path).init()
    for i, kind in enumerate(["user", "watchdog", "helper_done"]):
        store.append_event("turn_start", turn=str(i), kind=kind, text="x")
        store.append_event("turn_end", turn=str(i), status="error" if kind == "watchdog" else "done",
                           usage={"api_calls": 3, "cost_usd": 0.5})
    store.append_event("helper", event="start", subagent_id="a")
    store.append_event("inbox", item={"id": "approval-1"})
    row = summarise(tmp_path)
    assert (row["owner_messages"], row["watchdog_nudges"], row["helper_reports"]) == (1, 1, 1)
    assert (row["agents_started"], row["approvals_asked"], row["errors"]) == (1, 1, 1)
    assert row["model_calls"] == 9 and row["cost_usd"] == 1.5
