"""Real-git tests for automatic checkpoint commits (no mocks)."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location(
        "project_checkpoint_under_test", ROOT / "project_checkpoint.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
    ).stdout


def _repo(path: Path, *, builder: bool = True) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "Test")
    if builder:
        (path / ".sdlc").mkdir()
        (path / ".sdlc" / "progress.md").write_text("# SDLC Progress\n")
    (path / "README.md").write_text("start\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "baseline")
    return path


def test_checkpoints_helper_work_and_skips_secrets(tmp_path):
    cp = _module()
    project = _repo(tmp_path / "app")
    (project / "server.py").write_text("print('hi')\n")
    (project / "README.md").write_text("changed\n")
    (project / ".env").write_text("TOKEN=abc\n")
    (project / ".env.example").write_text("TOKEN=\n")

    commit = cp.checkpoint_project(
        str(project), role="sw-developer", status="completed",
        exit_reason="max_iterations", goal="Build the YouTube connection",
    )

    assert commit
    committed = set(_git(project, "show", "--name-only", "--format=", "HEAD").split())
    assert committed == {"server.py", "README.md", ".env.example"}
    assert _git(project, "status", "--porcelain").strip() == "?? .env"
    subject = _git(project, "log", "-1", "--format=%s")
    assert "checkpoint" in subject and "step limit" in subject
    assert "Build the YouTube connection" in _git(project, "log", "-1", "--format=%b")


def test_nothing_to_record_makes_no_commit(tmp_path):
    cp = _module()
    project = _repo(tmp_path / "app")
    before = _git(project, "rev-parse", "HEAD")
    assert cp.checkpoint_project(str(project)) is None
    assert _git(project, "rev-parse", "HEAD") == before


def test_never_commits_into_a_parent_repository(tmp_path):
    """A project folder without its own .git must not be committed into the
    repository that contains it (e.g. Lyra's own checkout)."""
    cp = _module()
    parent = _repo(tmp_path / "lyra", builder=False)
    project = parent / "my_projects" / "app"
    (project / ".sdlc").mkdir(parents=True)
    (project / "main.py").write_text("x = 1\n")
    before = _git(parent, "rev-parse", "HEAD")
    assert cp.checkpoint_project(str(project)) is None
    assert _git(parent, "rev-parse", "HEAD") == before


def test_skips_folders_that_are_not_builder_projects(tmp_path):
    cp = _module()
    project = _repo(tmp_path / "plain", builder=False)
    (project / "notes.txt").write_text("mine\n")
    assert cp.checkpoint_project(str(project)) is None
    assert "notes.txt" in _git(project, "status", "--porcelain")


def test_hook_signature_accepts_subagent_stop_kwargs(tmp_path):
    cp = _module()
    project = _repo(tmp_path / "app")
    (project / "a.py").write_text("a = 1\n")
    cp.on_subagent_stop(
        parent_session_id="p", child_session_id="c", child_role="leaf",
        child_summary="done", child_status="completed", duration_ms=5,
        workspace=str(project), child_exit_reason="completed", child_goal="Add a",
    )
    assert _git(project, "status", "--porcelain").strip() == ""
