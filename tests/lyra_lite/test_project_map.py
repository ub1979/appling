from pathlib import Path

import pytest

from lyra_lite.project_map import read_map, row_state
from tests.lyra_lite.progress_cases import CLAUDE_DELIVERED, HERMES_DELIVERED, NEW_FEATURE

LEDGER = """# SDLC Progress

Project: Demo
Current phase: Development
Updated: 2026-10-01

## Phase ledger
| Phase | Status | Artifact | Evidence |
|---|---|---|---|
| Requirements and prototype | **verified / approved** | `requirements.md` | owner approved |
| Remaining development | running | T-001–T-051 | wave 3 |
| Independent security / QA | partial | T-041 | scanner passed |
| Owner-bound import | offline verified; owner acceptance pending | CR-053 | needs owner |
| Ads connection | blocked | RES-002 | scope |
| Documentation | pending | T-045 | |

## Planned wave/task ledger
| Wave | Pending task rows | Outcome |
|---|---|---|
| 1 | T-001 verified | done |
"""


def test_rows_are_read_in_order_with_plain_states(tmp_path: Path):
    (tmp_path / ".sdlc").mkdir()
    (tmp_path / ".sdlc" / "progress.md").write_text(LEDGER)
    data = read_map(tmp_path)
    assert data["current_phase"] == "Development"
    assert [(p["name"], p["state"]) for p in data["phases"]] == [
        ("Requirements and prototype", "done"),
        ("Remaining development", "running"),
        ("Independent security / QA", "running"),
        ("Owner-bound import", "owner"),
        ("Ads connection", "blocked"),
        ("Documentation", "pending"),
    ]
    assert data["phases"][0]["status"] == "verified / approved"


def test_unfinished_qualifier_wins_over_done_words():
    assert row_state("verified locally, incomplete product") == "running"
    assert row_state("integrated, product capability partial") == "running"
    assert row_state("not yet PASS") == "running"
    assert row_state("not passed") == "running"
    assert row_state("PASS; owner acceptance pending") == "owner"
    assert row_state("complete") == "done"


@pytest.mark.parametrize("status", [
    "PASS — 0 open HIGH/CRITICAL",
    "APPROVED, no open defects",
    "verified, nothing pending",
    "PASS — zero failures",
    "PASS — 0 open failures",
    "PASS — failures: 0",
    "PASS — no tests failing",
    "completed — no failed tests",
    "PASS — tests not failing",
    "resolved — no pending work",
    "superseded — no open work",
    "descoped — nothing pending",
    "fixed, no longer failing",
    "PASS (previously failing test fixed)",
    "PASS — fail: 0",
    "PASS — 0/5 failing",
    "CONFIRMED at 039b438",
])
def test_explicit_absence_of_remaining_work_does_not_reopen_passed_rows(status):
    assert row_state(status) == "done"


@pytest.mark.parametrize("status, expected", [
    ("done, FAIL", "running"),
    ("completed — but tests failing", "running"),
    ("PASS locally; integration tests failed", "running"),
    ("FAIL", "running"),
    ("PASS — 2 open HIGH", "running"),
    ("PASS — 10 open defects", "running"),
    ("PASS — failures: 10", "running"),
    ("PASS — 0 open HIGH; 2 open MEDIUM", "running"),
    ("PASS — no open defects; implementation partial", "running"),
    ("PASS — no failures; export pending", "running"),
    ("verified, nothing pending in QA; owner acceptance pending", "owner"),
    ("completed — no failed tests; blocked on owner approval", "owner"),
    ("done, FAIL; owner acceptance pending", "owner"),
    ("PASS locally; blocked on integration", "blocked"),
    ("PASS — Safari test fails", "running"),
    ("PASS — 2/5 failing", "running"),
    ("partially fixed", "pending"),
    ("partially complete", "pending"),
    ("not confirmed", "running"),
    ("not yet fixed", "running"),
])
def test_actual_failures_and_remaining_work_still_override_pass(status, expected):
    assert row_state(status) == expected


@pytest.mark.parametrize("status", [
    "resolved",
    "RESOLVED — outcome B, locked private. Decided by the owner's real run.",
    "superseded",
    "superseded — see the Development row below",
    "descoped",
    "DESCOPED BY OWNER 2026-10-13",
    "  Resolved  ",
    "delivered 2026-10-23",
    "handed off 2026-10-23",
])
def test_closed_work_is_done(status):
    assert row_state(status) == "done"


@pytest.mark.parametrize("status, expected", [
    ("not resolved", "pending"),
    ("not yet superseded", "pending"),
    ("not descoped", "pending"),
    ("unresolved", "pending"),
    ("partially resolved", "pending"),
    ("awaiting confirmation that work is descoped", "pending"),
    ("resolved locally; owner acceptance pending", "owner"),
    ("superseded; migration in progress", "running"),
    ("descoped in part; remaining work blocked", "blocked"),
    ("resolved locally; blocked on owner approval", "owner"),
    ("not delivered", "pending"),
    ("not yet handed off", "pending"),
    ("delivered locally; owner acceptance pending", "owner"),
])
def test_closure_words_do_not_hide_unfinished_work(status, expected):
    assert row_state(status) == expected


def test_missing_ledger_is_an_empty_map(tmp_path: Path):
    assert read_map(tmp_path) == {"exists": False, "phases": [], "current_phase": None, "updated": None}


def test_titled_ledger_heading_and_bare_phase_table_are_read(tmp_path: Path):
    (tmp_path / ".sdlc").mkdir()
    body = "| Phase | Status | Evidence |\n|---|---|---|\n| Task planning | verified | x |\n| QA | blocked | phone check |\n"
    for heading in ("# Scientific calculator — phase ledger\n\n", "# Progress\n\n"):
        (tmp_path / ".sdlc" / "progress.md").write_text(heading + body + "\n## Planned wave/task ledger\n| Wave | Rows |\n|---|---|\n| 1 | T-001 verified |\n")
        rows = [(p["name"], p["state"]) for p in read_map(tmp_path)["phases"]]
        assert rows == [("Task planning", "done"), ("QA", "blocked")], heading


@pytest.mark.parametrize("table", [
    "| Date | Phase | Status | Notes |\n|---|---|---|---|\n"
    "| 2026-10-23 | Build | verified | built it |\n"
    "| 2026-10-23 | QA | ✅ PASS | tested it |\n",
    "| # | Phase | Agent | Status | Evidence / notes |\n|---|---|---|---|---|\n"
    "| 1 | Build | Developer | verified | built it |\n"
    "| 2 | QA | QA | round 2 PASS | tested it |\n",
])
def test_observed_engine_ledgers_use_named_columns(tmp_path, table):
    (tmp_path / ".sdlc").mkdir()
    (tmp_path / ".sdlc/progress.md").write_text("# Progress ledger\n\n" + table)
    phases = read_map(tmp_path)["phases"]
    assert [(p["name"], p["state"], p["note"]) for p in phases] == [
        ("Build", "done", "built it"), ("QA", "done", "tested it"),
    ]


def test_only_phase_status_tables_count_and_evidence_cannot_complete_a_row(tmp_path):
    (tmp_path / ".sdlc").mkdir()
    (tmp_path / ".sdlc/progress.md").write_text("""## Phase ledger
| Status | Evidence | Phase |
|---|---|---|
| running | Development complete; QA passed | Development |
| resolved | old issue | Defect |
| superseded | replaced | Old plan |
| descoped | owner removed | Export |
## Other table
| Name | Status |
|---|---|
| unrelated | running |
""")
    rows = read_map(tmp_path)["phases"]
    assert [(p["name"], p["state"]) for p in rows] == [
        ("Development", "running"), ("Defect", "done"), ("Old plan", "done"), ("Export", "done"),
    ]


def _map(tmp_path, text):
    (tmp_path / ".sdlc").mkdir(exist_ok=True)
    (tmp_path / ".sdlc/progress.md").write_text(text)
    return read_map(tmp_path)


@pytest.mark.parametrize("text", [CLAUDE_DELIVERED, HERMES_DELIVERED])
def test_delivered_scope_keeps_old_rows_as_history_not_unfinished_work(tmp_path, text):
    result = _map(tmp_path, text)
    assert result["delivery_complete"]
    assert all(row["state"] == "done" for row in result["phases"])
    assert any("PASS" in row["status"] for row in result["phases"])
    assert any(row["status"] == "running" for row in result["history"])
    assert result["markdown"] == text
    assert (tmp_path / ".sdlc/progress.md").read_text() == text


@pytest.mark.parametrize("text", [CLAUDE_DELIVERED, HERMES_DELIVERED])
def test_new_scope_after_delivery_remains_active(tmp_path, text):
    result = _map(tmp_path, text + NEW_FEATURE)
    assert not result["delivery_complete"]
    assert [(p["name"], p["state"]) for p in result["phases"] if p["state"] != "done"] == [
        ("Export development", "running"), ("Export QA", "pending"),
    ]


def test_same_phase_latest_status_wins_but_other_work_is_preserved(tmp_path):
    result = _map(tmp_path, """| Phase | Status |
|---|---|
| Development | running |
| QA | running |
| QA | PASS |
| Security QA | running |
""")
    assert [(p["name"], p["state"]) for p in result["phases"]] == [
        ("Development", "running"), ("QA", "done"), ("Security QA", "running"),
    ]


@pytest.mark.parametrize("summary", [
    "| Documentation | delivered |",  # a task handoff is not project delivery
    "| Delivery | not delivered |",
    "| Delivery | partial; owner approval pending |",
    "| Delivery | blocked |",
    "| Handoff | handed off to QA |",  # work still needs verification
    "| Delivery | superseded |",
    "| Delivery | descoped |",
    "| Delivery | resolved |",
])
def test_ordinary_or_incomplete_handoff_does_not_close_other_work(tmp_path, summary):
    result = _map(tmp_path, "| Phase | Status |\n|---|---|\n| Development | running |\n" + summary)
    assert result["phases"][0]["state"] == "running"
    assert not result["delivery_complete"]


def test_delivery_with_nothing_pending_closes_history_but_failed_delivery_does_not(tmp_path):
    prefix = "| Phase | Status |\n|---|---|\n| Development | running |\n"
    result = _map(tmp_path, prefix + "| Delivery | delivered — nothing pending |\n")
    assert result["delivery_complete"]
    assert [row["name"] for row in result["history"]] == ["Development"]
    result = _map(tmp_path, prefix + "| Delivery | completed — but tests failing |\n")
    assert not result["delivery_complete"]
    assert [row["state"] for row in result["phases"]] == ["running", "running"]


def test_delivery_does_not_close_other_tables_or_revision_scopes(tmp_path):
    result = _map(tmp_path, """## Unfinished service
| Phase | Status |
|---|---|
| Service development | running |

## App ledger
| Phase | Status |
|---|---|
| Rev 3 build | running |
| Rev 2 build | running |
| Rev 2 delivery | delivered |
| Rev 2 new repair | running |
""")
    assert [p["name"] for p in result["phases"] if p["state"] == "running"] == [
        "Service development", "Rev 3 build", "Rev 2 new repair",
    ]


def test_explicitly_reopened_row_stays_active_even_before_old_delivery_marker(tmp_path):
    result = _map(tmp_path, """| Phase | Status |
|---|---|
| Development | reopened — regression found after delivery |
| Delivery | delivered |
""")
    assert result["phases"][0]["state"] == "running"
    assert not result["delivery_complete"]


def test_completed_metadata_alone_does_not_hide_running_work(tmp_path):
    result = _map(tmp_path, "Current phase: Delivered\n| Phase | Status |\n|---|---|\n| Development | running |\n")
    assert result["phases"][0]["state"] == "running"
    assert not result["delivery_complete"]


@pytest.mark.parametrize("status", ["running", "reopened", "FAIL", "blocked on owner approval"])
def test_new_qa_status_after_pass_and_delivery_is_still_unfinished(tmp_path, status):
    result = _map(tmp_path, "| Phase | Status |\n|---|---|\n| QA | PASS |\n"
                  f"| Delivery | delivered |\n| QA | {status} |\n")
    assert not result["delivery_complete"]
    assert [(p["name"], p["status"]) for p in result["phases"] if p["state"] != "done"] == [("QA", status)]
