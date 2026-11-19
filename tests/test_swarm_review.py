"""Independent regression checks for snapshot and integration boundaries."""
from pathlib import Path
import threading

import pytest

from appling import workspaces
from appling.store import Store
from appling.swarm import run_worker
from appling.workflow import Workflow


@pytest.mark.parametrize('alias',[False,True])
def test_snapshot_with_ignored_dependencies_and_forced_evidence(tmp_path,alias):
    root=tmp_path/'app';root.mkdir()
    workspaces.git(root,'init','-b','main')
    (root/'source.txt').write_text('initial')
    workspaces.git(root,'add','source.txt')
    workspaces.git(root,'-c','user.name=Tester','-c','user.email=test@example.test','commit','-m','initial')
    (root/'.gitignore').write_text('.appling/\nnode_modules/\ndist/\n.sdlc/\nprototypes/\n')
    for name in ['.appling/private','node_modules/package/index.js','dist/app.js','nested/dist/output',
                 'prototypes/.env.secret','.sdlc/evidence/w/node_modules/private']:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('excluded')
    for name in ['source.txt','literal[1].txt','prototypes/index.html','.sdlc/evidence/w/check.log']:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('captured '+name)
    index=(root/'.git/index').read_bytes();head=workspaces.git(root,'rev-parse','HEAD')
    selected_root=root
    if alias:
        selected_root=tmp_path/'alias';selected_root.symlink_to(root,target_is_directory=True)
    base=workspaces.snapshot(selected_root,include=['.sdlc/evidence/w/'])
    names=set(workspaces.git(root,'ls-tree','-r','--name-only',base).splitlines())
    assert {'source.txt','literal[1].txt','prototypes/index.html','.sdlc/evidence/w/check.log'}<=names
    assert not any(name.startswith(('.appling/','node_modules/','dist/','nested/dist/')) or '.env' in name or '/node_modules/' in name for name in names)
    assert (root/'.git/index').read_bytes()==index and workspaces.git(root,'rev-parse','HEAD')==head
    worker=tmp_path/'worker';workspaces.create(root,worker,base)
    (worker/'literal[1].txt').unlink()
    commit=workspaces.snapshot(worker,base,include=['.sdlc/evidence/w/'])
    assert 'literal[1].txt' in workspaces.changes(worker,base,commit)


def test_private_snapshot_keeps_tracked_source_after_ignore_rule_changes(tmp_path):
    root = tmp_path / 'app'
    root.mkdir()
    workspaces.git(root, 'init', '-b', 'main')
    (root / 'package.json').write_text('{"scripts":{"build":"build-app"}}')
    (root / '.env').write_text('SECRET=dummy-test-value')
    workspaces.git(root, 'add', 'package.json')
    workspaces.git(root, 'add', '--force', '.env')
    workspaces.git(root, '-c', 'user.name=Tester', '-c', 'user.email=test@example.test',
                   'commit', '-m', 'existing source')
    (root / '.gitignore').write_text('*.json\n')
    (root / 'private.json').write_text('ignored and untracked')
    base = workspaces.snapshot(root)
    workspace = tmp_path / 'worker'
    workspaces.create(root, workspace, base)
    assert (workspace / 'package.json').read_bytes() == (root / 'package.json').read_bytes()
    assert not (workspace / 'private.json').exists()
    assert not (workspace / '.env').exists()


def test_rename_cannot_delete_unowned_source_or_move_a_new_user_edit(tmp_path):
    root = tmp_path / 'app'
    root.mkdir()
    (root / 'shared.txt').write_text('shared original')
    base = workspaces.snapshot(root)
    workspace = tmp_path / 'worker'
    workspaces.create(root, workspace, base)
    (workspace / 'owned').mkdir()
    (workspace / 'shared.txt').rename(workspace / 'owned/shared.txt')
    commit = workspaces.snapshot(workspace, base)
    (root / 'shared.txt').write_text('new owner edit')
    with pytest.raises(ValueError, match='outside its assigned ownership'):
        workspaces.integrate(root, workspace, base, commit, ['owned/'], '.sdlc/evidence/w/')
    assert (root / 'shared.txt').read_text() == 'new owner edit'
    assert not (root / 'owned/shared.txt').exists()


def test_partial_already_applied_result_is_not_treated_as_complete(tmp_path):
    root = tmp_path / 'app'
    root.mkdir()
    for name in ['a.txt', 'b.txt']:
        (root / name).write_text('original')
    base = workspaces.snapshot(root)
    workspace = tmp_path / 'worker'
    workspaces.create(root, workspace, base)
    for name in ['a.txt', 'b.txt']:
        (workspace / name).write_text('updated')
    commit = workspaces.snapshot(workspace, base)
    (root / 'a.txt').write_text('updated')
    with pytest.raises(ValueError, match='changed since'):
        workspaces.integrate(root, workspace, base, commit, ['a.txt', 'b.txt'],
                             '.sdlc/evidence/w/', allow_applied=True)
    assert (root / 'b.txt').read_text() == 'original'


def test_parent_directory_alias_cannot_redirect_integration_writes(tmp_path):
    root = tmp_path / 'app'
    root.mkdir()
    for folder in ['owned', 'another']:
        (root / folder).mkdir()
        (root / folder / 'source.txt').write_text('original')
    base = workspaces.snapshot(root)
    workspace = tmp_path / 'worker'
    workspaces.create(root, workspace, base)
    (workspace / 'owned/source.txt').write_text('worker update')
    commit = workspaces.snapshot(workspace, base)
    (root / 'owned/source.txt').unlink()
    (root / 'owned').rmdir()
    (root / 'owned').symlink_to('another', target_is_directory=True)
    with pytest.raises((ValueError, RuntimeError)):
        workspaces.integrate(root, workspace, base, commit, ['owned/'], '.sdlc/evidence/w/')
    assert (root / 'another/source.txt').read_text() == 'original'


def test_worker_evidence_cannot_escape_its_directory_using_parent_segments(tmp_path):
    store = Store(tmp_path / 'studio')
    project = store.add(tmp_path / 'app')
    root = Path(project['root'])
    prefix = '.sdlc/evidence/w/'
    (root / prefix).mkdir(parents=True)
    evidence = prefix + '../another/check.txt'
    path = root / evidence
    path.parent.mkdir(parents=True)
    path.write_text('unowned evidence')
    result = dict(status='completed', checks=[dict(command='check', exit_code=0, evidence=evidence)])
    workflow = Workflow(store, lambda conn, run: result)
    workflow.cancelled[project['id']] = threading.Event()
    worker = dict(id='w', task_id='a', role='sw-developer', goal='a', workspace=str(root),
                  base='not-used-before-evidence-validation', status='pending', evidence=prefix)
    try:
        with pytest.raises(ValueError, match='inside its assigned evidence folder'):
            run_worker(workflow, project['id'], dict(id='a', goal='a', files=['src/']), worker)
    finally:
        workflow.shutdown()
