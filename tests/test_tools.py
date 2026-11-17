from pathlib import Path
import threading
import pytest
from appling.engines import Run
from appling.tools import execute


def test_api_file_tools_respect_readonly_private_state_and_path_bounds(tmp_path):
    run=Run(tmp_path,'instructions','task')
    execute(run,'write_file',{'path':'src/app.ts','content':'export const value = 1;'})
    assert execute(run,'read_file',{'path':'src/app.ts'})=='export const value = 1;'
    for path in ['../escape.txt','.git/config','.appling/sessions/private.json','.env']:
        with pytest.raises((ValueError,PermissionError)):
            execute(run,'write_file',{'path':path,'content':'bad'})
    run.readonly=True
    with pytest.raises(PermissionError):
        execute(run,'write_file',{'path':'src/app.ts','content':'changed'})


def test_skills_are_read_completely_and_cannot_escape_bundle(tmp_path):
    result=execute(Run(tmp_path,'',''),'read_skill',{'name':'ultimate-builder:req-engineer'})
    assert 'Conversation Contract' in result
    assert 'Step 6.5' in result
    with pytest.raises(ValueError):
        execute(Run(tmp_path,'',''),'read_skill',{'name':'../store'})


def test_command_requires_consent_and_records_real_exit_output(tmp_path):
    run=Run(tmp_path,'','')
    assert 'denied' in execute(run,'run_command',{'command':'printf hello'})
    run.ask=lambda *args:'once'
    import json
    result=json.loads(execute(run,'run_command',{'command':'printf hello'}))
    assert result=={'exit_code':0,'output':'hello'}


def test_source_memory_removes_deleted_code_references(tmp_path):
    from appling.store import Store
    from appling.context import refresh
    store=Store(tmp_path/'studio.db');p=store.add(tmp_path/'app');root=Path(p['root'])
    file=root/'feature.ts';file.write_text('const unicornFlag = true;')
    refresh(store,p['id']);assert store.search(p['id'],'unicornFlag')
    file.unlink();refresh(store,p['id']);assert not store.search(p['id'],'unicornFlag')
