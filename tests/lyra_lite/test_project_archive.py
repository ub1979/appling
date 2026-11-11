"""Archive real project folders through the API without starting a server."""

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lyra_lite.runner import project_key
from lyra_lite.server import Lyra, create_app
from lyra_lite.store import ProjectStore


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    manager = Lyra(engine_factory=lambda *_: None)
    client = TestClient(create_app(manager, token="archive-test"), base_url="http://localhost",
                        headers={"x-lyra-token": "archive-test"})
    yield manager, client, tmp_path
    manager.shutdown()
    client.close()


def add_project(studio, folder="Work/Orders"):
    manager, _, home = studio
    root = home / folder
    root.mkdir(parents=True)
    (root / "app.txt").write_text("working app")
    runner = manager.add_project(str(root), create=False)
    runner.store.append_transcript([{"role": "user", "content": "Keep existing orders."}])
    return project_key(root), runner


def test_delete_creates_archive_and_preserves_project_and_chat(studio):
    manager, client, home = studio
    pid, runner = add_project(studio)
    root = runner.root
    response = client.delete(f"/api/projects/{pid}")
    assert response.status_code == 200, response.text
    destination = Path(response.json()["archived_to"])
    assert destination.parent == home / "Appling Projects/Archive"
    assert not root.exists()
    assert (destination / "app.txt").read_text() == "working app"
    assert ProjectStore(destination).transcript()[0]["content"] == "Keep existing orders."
    assert manager.list() == []
    assert manager._load_registry() == []
    assert client.get(f"/api/projects/{pid}").status_code == 404
    assert client.delete(f"/api/projects/{pid}").status_code == 404
    with pytest.raises(ValueError, match="closed"):
        runner.submit("Late message")
    assert runner.watchdog_tick() == "project closed"
    runner._refresh_memory()
    runner.stop_turn()
    runner.set_keep_going(True)
    assert not root.exists()
    restored = manager.add_project(str(destination), create=False)
    assert restored.store.transcript()[0]["content"] == "Keep existing orders."
    assert restored.snapshot()["paused"]


def test_same_project_names_have_separate_archive_destinations(studio):
    _, client, _ = studio
    first, _ = add_project(studio, "One/Orders")
    second, _ = add_project(studio, "Two/Orders")
    destinations = [client.delete(f"/api/projects/{pid}").json()["archived_to"] for pid in (first, second)]
    assert destinations[0] != destinations[1]
    assert all((Path(path) / "app.txt").is_file() for path in destinations)


def test_busy_project_stays_in_place(studio):
    manager, client, _ = studio
    pid, runner = add_project(studio)
    with runner._cond:
        runner._busy = True
    try:
        response = client.delete(f"/api/projects/{pid}")
        assert response.status_code == 409
        assert "Stop Appling" in response.json()["detail"]
        assert manager.get(pid) is runner
        assert (runner.root / "app.txt").is_file()
    finally:
        with runner._cond:
            runner._busy = False


@pytest.mark.parametrize("failure", ["move", "registry"])
def test_failed_archive_keeps_project_registered_and_recoverable(studio, monkeypatch, failure):
    manager, client, _ = studio
    pid, runner = add_project(studio)

    def fail(*args):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(manager, "_move_project" if failure == "move" else "_save_registry", fail)
    response = client.delete(f"/api/projects/{pid}")
    assert response.status_code == 409
    assert (runner.root / "app.txt").read_text() == "working app"
    assert manager.get(pid).snapshot()["paused"]
    assert str(runner.root) in manager._load_registry()
    assert not list((Path.home() / "Appling Projects/Archive").glob("*/app.txt"))


def test_parent_project_cannot_move_another_open_project(studio):
    manager, client, _ = studio
    pid, runner = add_project(studio)
    child, _ = add_project(studio, "Work/Orders/Child")
    assert client.delete(f"/api/projects/{pid}").status_code == 409
    assert manager.get(child).root.is_dir()
    assert runner.root.is_dir()


def test_delete_requires_the_application_token(studio):
    _, client, _ = studio
    pid, runner = add_project(studio)
    response = client.delete(f"/api/projects/{pid}", headers={"x-lyra-token": "wrong"})
    assert response.status_code == 401
    assert runner.root.is_dir()


def test_archiving_a_linked_git_worktree_preserves_git_registration(studio):
    manager, client, home = studio
    repository = home / "Repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    subprocess.run(["git", "-C", str(repository), "-c", "user.name=Test",
                    "-c", "user.email=test@example.invalid", "commit",
                    "--allow-empty", "-qm", "Baseline"], check=True)
    root = home / "Worktree"
    subprocess.run(["git", "-C", str(repository), "worktree", "add", "-qb",
                    "update", str(root)], check=True)
    runner = manager.add_project(str(root), create=False)
    response = client.delete(f"/api/projects/{project_key(root)}")
    assert response.status_code == 200, response.text
    destination = response.json()["archived_to"]
    listing = subprocess.check_output(["git", "-C", str(repository), "worktree", "list", "--porcelain"], text=True)
    assert f"worktree {destination}" in listing
    assert f"worktree {root}\n" not in listing
    assert subprocess.check_output(["git", "-C", destination, "branch", "--show-current"], text=True).strip() == "update"
    assert not runner.root.exists()
