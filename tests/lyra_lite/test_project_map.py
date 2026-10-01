from pathlib import Path

from lyra_lite.project_map import read_map, row_state

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
    assert row_state("complete") == "done"


def test_missing_ledger_is_an_empty_map(tmp_path: Path):
    assert read_map(tmp_path) == {"exists": False, "phases": [], "current_phase": None, "updated": None}


def test_titled_ledger_heading_and_bare_phase_table_are_read(tmp_path: Path):
    (tmp_path / ".sdlc").mkdir()
    body = "| Phase | Status | Evidence |\n|---|---|---|\n| Task planning | verified | x |\n| QA | blocked | phone check |\n"
    for heading in ("# Scientific calculator — phase ledger\n\n", "# Progress\n\n"):
        (tmp_path / ".sdlc" / "progress.md").write_text(heading + body + "\n## Planned wave/task ledger\n| Wave | Rows |\n|---|---|\n| 1 | T-001 verified |\n")
        rows = [(p["name"], p["state"]) for p in read_map(tmp_path)["phases"]]
        assert rows == [("Task planning", "done"), ("QA", "blocked")], heading
