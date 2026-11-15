"""Real Git worktrees exercise ownership and atomic integration guards."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from lyra_lite.development import DevelopmentWave, git
from lyra_lite.store import ProjectStore


@pytest.fixture
def project(tmp_path, monkeypatch):
    for key, value in {"GIT_AUTHOR_NAME": "Test", "GIT_COMMITTER_NAME": "Test",
                       "GIT_AUTHOR_EMAIL": "test@example.invalid", "GIT_COMMITTER_EMAIL": "test@example.invalid"}.items():
        monkeypatch.setenv(key, value)
    root = tmp_path / "Project with spaces"
    ProjectStore(root).init()
    git(root, "init")
    (root / "shared.txt").write_text("contract\n")
    git(root, "add", "shared.txt")
    git(root, "commit", "-m", "Initial contract")
    return root


def _wave(root, ownership=(['a.txt'], ['b.txt'])):
    base = git(root, "rev-parse", "HEAD")
    wave = root / ".lyra/development/test"
    wave.mkdir(parents=True)
    records = []
    for i, paths in enumerate(ownership):
        path = wave / f"worker-{i}"
        branch = f"worker-{i}"
        git(root, "worktree", "add", "-b", branch, str(path), base)
        records.append({"workspace": str(path), "branch": branch, "owned_paths": paths})
    return wave, {"base": base, "branch": git(root, "symbolic-ref", "--short", "HEAD"), "workers": records}


def test_disjoint_workers_integrate_with_separate_indexes(project):
    wave, meta = _wave(project)
    for i, record in enumerate(meta["workers"]):
        path = Path(record["workspace"])
        (path / record["owned_paths"][0]).write_text(f"worker {i}\n")
        git(path, "add", record["owned_paths"][0])
    assert git(project, "diff", "--cached", "--name-only") == ""
    DevelopmentWave(project).integrate(wave, meta)
    assert (project / "a.txt").read_text() == "worker 0\n"
    assert (project / "b.txt").read_text() == "worker 1\n"
    assert git(project, "status", "--porcelain") == ""
    assert len(git(project, "rev-list", "--parents", "HEAD").splitlines()[0].split()) == 3


@pytest.mark.parametrize("case", ["outside-ownership", "dirty-primary", "advanced-primary", "integration-conflict"])
def test_rejected_integration_preserves_primary_and_worker_files(project, case):
    wave, meta = _wave(project, ownership=(['shared.txt'], ['shared.txt']))
    for i, record in enumerate(meta["workers"]):
        path = Path(record["workspace"])
        (path / "shared.txt").write_text(f"worker {i}\n")
    if case == "outside-ownership":
        (Path(meta["workers"][0]["workspace"]) / "outside.txt").write_text("keep me")
    if case == "dirty-primary":
        (project / "shared.txt").write_text("owner edits\n")
    if case == "advanced-primary":
        (project / "owner.txt").write_text("owner commit")
        git(project, "add", "owner.txt")
        git(project, "commit", "-m", "Owner change")
    # The first three cases must get past the temporary merge to exercise
    # primary drift, rather than failing earlier from a deliberate conflict.
    if case != "integration-conflict":
        (Path(meta["workers"][1]["workspace"]) / "shared.txt").write_text("contract\n")
    head, content = git(project, "rev-parse", "HEAD"), (project / "shared.txt").read_bytes()
    with pytest.raises(ValueError):
        DevelopmentWave(project).integrate(wave, meta)
    assert git(project, "rev-parse", "HEAD") == head
    assert (project / "shared.txt").read_bytes() == content
    assert (Path(meta["workers"][0]["workspace"]) / "shared.txt").exists()


@pytest.mark.parametrize("paths", [["../outside"], [".git/config"], [".sdlc/"], ["package.json"], ["src/*"]])
def test_invalid_ownership_rejected_before_any_worker_starts(project, paths):
    args = {"tasks": [{"goal": "Code", "context": json.dumps({"owned_paths": paths})}]}
    result = json.loads(DevelopmentWave(project).dispatch(SimpleNamespace(), args))
    assert result["error"] and result["recovery"] is None
    assert "worker-" not in git(project, "worktree", "list")


@pytest.mark.parametrize("ownership", [(["src/"], ["src/feature.ts"]), (["src/A.ts"], ["src/a.ts"])])
def test_overlapping_directory_and_file_rejected(project, ownership):
    tasks = [{"goal": "Code", "context": json.dumps({"owned_paths": paths})}
             for paths in ownership]
    result = json.loads(DevelopmentWave(project).dispatch(SimpleNamespace(), {"tasks": tasks}))
    assert "overlapping" in result["error"]


def test_unowned_intermediate_commits_cannot_hide_behind_a_revert(project):
    wave, meta = _wave(project)
    worker = Path(meta["workers"][0]["workspace"])
    (worker / "shared.txt").write_text("outside ownership\n")
    git(worker, "add", "shared.txt")
    git(worker, "commit", "-m", "Unowned edit")
    (worker / "shared.txt").write_text("contract\n")
    git(worker, "add", "shared.txt")
    git(worker, "commit", "-m", "Revert unowned edit")
    with pytest.raises(ValueError, match="outside its ownership"):
        DevelopmentWave(project).integrate(wave, meta)
    assert git(project, "rev-parse", "HEAD") == meta["base"]


@pytest.mark.parametrize("outcome", ["interrupted", "max_iterations", "failed"])
def test_incomplete_wave_keeps_primary_unchanged(project, monkeypatch, outcome):
    def run_workers(**kwargs):
        worktree = Path(kwargs["task_runtimes"][0]["workspace"])
        (worktree / "a.txt").write_text("partial implementation")
        return json.dumps({"results": [{"status": "completed" if outcome == "max_iterations" else outcome,
                                       "exit_reason": outcome}]})

    monkeypatch.setattr("tools.delegate_tool.delegate_task", run_workers)
    base = git(project, "rev-parse", "HEAD")
    result = json.loads(DevelopmentWave(project).dispatch(SimpleNamespace(), {"tasks": [{
        "goal": "Code A", "context": json.dumps({"owned_paths": ["a.txt"]}),
    }]}))
    assert "did not finish" in result["error"]
    assert not (project / "a.txt").exists()
    assert git(project, "rev-parse", "HEAD") == base
    assert (Path(result["recovery"]) / "worker-0/a.txt").read_text() == "partial implementation"


@pytest.mark.parametrize('changed', [False, True])
def test_read_only_worker_cannot_integrate_source_edits(project, changed):
    wave, meta = _wave(project, ownership=([],))
    record = meta['workers'][0]
    record['read_only'] = True
    if changed:
        (Path(record['workspace']) / 'shared.txt').write_text('unexpected edit\n')
        with pytest.raises(ValueError, match='read-only worker modified'):
            DevelopmentWave(project).integrate(wave, meta)
        assert Path(record['workspace']).exists()
    else:
        DevelopmentWave(project).integrate(wave, meta)
        assert meta['validated_baseline'] == meta['base']
        assert not Path(record['workspace']).exists()
    assert git(project, 'rev-parse', 'HEAD') == meta['base']
    assert (project / 'shared.txt').read_text() == 'contract\n'


def test_mixed_wave_requires_checks_after_integration(project):
    def execute(prepared, records):
        (Path(records[0]['workspace']) / 'feature.txt').write_text('new behavior\n')
        return json.dumps({'results': [{'status': 'completed', 'exit_reason': 'completed'} for _ in records]})
    tasks = [{'goal': 'Implement', 'context': json.dumps({'owned_paths': ['feature.txt']})},
             {'goal': 'Review baseline', 'context': json.dumps({'read_only': True})}]
    result = json.loads(DevelopmentWave(project).dispatch(SimpleNamespace(), {'tasks': tasks}, executor=execute))
    assert 'error' not in result
    assert result['checks_require_rerun'] is True
    assert result['baseline'] != git(project, 'rev-parse', 'HEAD')
    assert (project / 'feature.txt').read_text() == 'new behavior\n'
