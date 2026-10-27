"""Project memory (search index) and the focus note."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from lyra_lite.focus import focus_note
from lyra_lite.memory import ProjectMemory, chunks, fts_query
from lyra_lite.store import ProjectStore


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "gym"
    store = ProjectStore(root).init()
    store.append_transcript([
        {"role": "user", "content": "Export should be a CSV with semicolons between columns.", "ts": 1790000000},
        {"role": "assistant", "content": "Noted: CSV export uses semicolons.", "ts": 1790000060},
        {"role": "user", "content": "Machines: leg press, lat pulldown and chest press.", "ts": 1790000120},
    ])
    (root / ".sdlc").mkdir()
    (root / "requirements.md").write_text("# Requirements\n\nFR-7 Rest timer of 90 seconds between sets.\n")
    for args in (["init", "-q"], ["config", "user.email", "t@t.invalid"], ["config", "user.name", "T"]):
        subprocess.run(["git", *args], cwd=root, check=True)
    subprocess.run(["git", "add", "requirements.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "Add rest timer requirement"], cwd=root, check=True)
    return root


def test_recall_finds_owner_words_documents_and_history(tmp_path):
    root = _project(tmp_path)
    memory = ProjectMemory(root)
    hits = memory.search("what separator for the CSV export?")
    assert any(h["text"].startswith("Owner:") and "semicolons" in h["text"] for h in hits)
    assert "rest timer" in memory.search("rest timer")[0]["text"].lower()
    assert any(r["ref"].startswith("commit") for r in memory.search("rest timer requirement", limit=10))
    assert memory.search("unrelated spaceship") == []


def test_index_follows_file_changes_and_deletions(tmp_path):
    root = _project(tmp_path)
    memory = ProjectMemory(root)
    assert memory.search("rest timer")
    (root / "requirements.md").write_text("# Requirements\n\nFR-7 Interval beeps.\n")
    assert not [r for r in memory.search("rest timer") if r["source"] == "requirements.md"]
    (root / "requirements.md").unlink()
    assert not [r for r in memory.search("interval beeps") if r["source"] == "requirements.md"]


def test_new_chat_messages_are_indexed_incrementally(tmp_path):
    root = _project(tmp_path)
    memory = ProjectMemory(root)
    assert memory.search("dark mode") == []
    ProjectStore(root).append_transcript([{"role": "user", "content": "Please add a dark mode."}])
    assert "dark mode" in memory.search("dark mode")[0]["text"]


def test_query_and_chunk_helpers():
    assert fts_query('what did we say about "CSV" export?') == '"say" OR "csv" OR "export"'
    assert fts_query("the and of") == ""
    pieces = chunks("word " * 1000)
    assert len(pieces) > 1 and all(len(p) <= 1200 for p in pieces)


def test_focus_note_comes_from_ledger_and_brain(tmp_path):
    root = tmp_path / "p"
    (root / ".sdlc").mkdir(parents=True)
    (root / ".sdlc" / "progress.md").write_text(
        "Current phase: Development\n\n## Phase ledger\n| Phase | Status |\n|---|---|\n"
        "| Requirements | verified |\n| Development | running — T-002 left |\n")
    (root / ".sdlc" / "project-brain.md").write_text(
        "# Brain\n## Goal\nGym tracker\n## Next actions\n- Finish CSV export\n## Open questions\n- Pictures source?\n")
    note = focus_note(root, open_inbox=1)
    assert note.startswith("[Project focus")
    for expected in ("Current step: Development", "Done: Requirements", "Not done: Development",
                     "Finish CSV export", "Pictures source?", "1 open question"):
        assert expected in note, expected
    assert "Gym tracker" not in note  # only the focus sections, not the whole brain
    assert focus_note(tmp_path / "empty") == ""


def test_focus_note_does_not_reopen_closed_work(tmp_path):
    (tmp_path / ".sdlc").mkdir()
    (tmp_path / ".sdlc" / "progress.md").write_text(
        "## Phase ledger\n| Phase | Status |\n|---|---|\n"
        "| Development history | superseded — see the Development row below |\n"
        "| Post-send corrections | **DESCOPED BY OWNER** |\n"
        "| Private access decision | RESOLVED — decided by the owner's real run |\n"
        "| Development | running |\n"
        "| Owner acceptance | pending owner confirmation |\n"
        "| Service connection | blocked |\n")

    note = focus_note(tmp_path)
    unfinished = [line for line in note.splitlines() if line.startswith("Not done:")]
    assert unfinished == [
        "Not done: Development — running",
        "Not done: Owner acceptance — pending owner confirmation",
        "Not done: Service connection — blocked",
    ]
    for phase in ("Development history", "Post-send corrections", "Private access decision"):
        assert phase in note


def test_delivery_focus_uses_current_ledger_instead_of_old_status_and_next_actions(tmp_path):
    from tests.lyra_lite.progress_cases import CLAUDE_DELIVERED, NEW_FEATURE

    (tmp_path / ".sdlc").mkdir()
    ledger = tmp_path / ".sdlc/progress.md"
    ledger.write_text(CLAUDE_DELIVERED)
    (tmp_path / ".sdlc/project-brain.md").write_text(
        "## Current state\nDevelopment still running.\n## Next actions\nRun QA again.\n"
        "## Open risks\nLocal storage only.\n")
    note = focus_note(tmp_path)
    assert "Not done:" not in note
    assert "Current step: Development" not in note
    assert "Development still running" not in note
    assert "Run QA again" not in note
    assert "Delivered" in note and "Local storage only" in note
    assert "1 open question" in focus_note(tmp_path, open_inbox=1)

    ledger.write_text(CLAUDE_DELIVERED + NEW_FEATURE)
    note = focus_note(tmp_path)
    assert "Not done: Export development — running" in note
    assert "Not done: Export QA — pending" in note
    assert "Not done: Development — running" not in note
