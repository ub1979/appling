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


def test_usage_splits_lyra_from_agents_and_names_agents(tmp_path: Path):
    from lyra_lite.usage import summarise_usage

    store = ProjectStore(tmp_path).init()
    store.append_event("turn_end", turn="1", status="done",
                       usage={"api_calls": 2, "input": 100, "cache_read": 900, "cache_write": 0, "output": 50})
    store.append_event("helper", event="complete", goal="Act as Ultimate Builder sw-developer for T-1",
                       usage={"api_calls": 5, "input": 200, "cache_read": 800, "cache_write": 0, "output": 70})
    store.append_event("helper", event="complete", goal="Perform independent QA on the app",
                       usage={"api_calls": 1, "input": 10, "cache_read": 0, "cache_write": 0, "output": 5})
    u = summarise_usage(store)
    assert u["lyra"]["prompt"] == 1000 and u["lyra"]["cached_pct"] == 90
    assert u["total"]["api_calls"] == 8 and u["total"]["output"] == 125
    assert [a["id"] for a in u["by_agent"]] == ["sw-developer", "qa-engineer"]
