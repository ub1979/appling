from pathlib import Path
import json
from fastapi.testclient import TestClient
import pytest
from appling.server import create_app


@pytest.fixture
def client(tmp_path):
    app=create_app(tmp_path/'studio',execute=lambda c,r: {'question':'Who uses it?','choices':['Me','My team']})
    with TestClient(app,base_url='http://127.0.0.1') as client:
        client.headers['x-lyra-token']=app.state.token
        yield client,app,tmp_path


def test_api_auth_and_cross_origin_blocking(client):
    c,app,_=client
    assert c.get('/api/projects').status_code==200
    assert c.get('/api/projects',headers={'x-lyra-token':'wrong'}).status_code==401
    assert c.post('/api/settings',headers={'origin':'https://evil.example'},json={}).status_code==403
    assert c.get('/api/projects',headers={'host':'evil.example'}).status_code==403


def test_project_creation_reopening_and_upload_path_bounds(client):
    c,app,tmp=client;root=tmp/'my-app'
    data=dict(path=str(root),create=True,brief='',kind='app')
    response=c.post('/api/projects',json=data);assert response.status_code==200,response.text
    p=response.json();assert p['inbox'][0]['kind']=='question'
    assert (root/'.git').is_dir()
    assert c.get('/api/projects/'+p['id']).json()['root']==str(root)
    reopened=c.post('/api/projects',json=dict(data,create=False));assert reopened.json()['id']==p['id']
    bad=c.put('/api/projects/'+p['id']+'/files?name=../secret',content=b'x')
    assert bad.status_code==400
    good=c.put('/api/projects/'+p['id']+'/files?name=notes.txt',content=b'hello')
    assert good.status_code==200;assert (root/'assets/uploads/notes.txt').read_text()=='hello'
    usage=c.get('/api/projects/'+p['id']+'/usage').json();assert usage['total']['api_calls']==0


def test_connections_and_role_selections_persist_without_fallback(client):
    c,app,_=client
    conn=dict(engine='openai-compatible',label='My gateway',base_url='http://localhost:9000/v1',api_key_env='MY_KEY',models=['custom-model'])
    assert c.post('/api/settings',json={'connections':{'custom-api':conn}}).status_code==200
    assert c.post('/api/settings/model',json={'provider':'custom-api','model':'custom-model'}).status_code==200
    selection={'provider':'ollama-local','model':'local-coder'}
    assert c.post('/api/settings/agents/qa-engineer',json={'selection':selection}).status_code==200
    key,connection,chosen=app.state.workflow.connection('qa-engineer')
    assert key=='ollama-local';assert chosen['model']=='local-coder'
    key,_,_=app.state.workflow.connection('sw-developer');assert key=='custom-api'
    assert c.post('/api/settings',json={'connections':{'oops':dict(conn,api_key='secret')}}).status_code==400


def test_studio_returns_original_interface_and_runtime_token(client):
    c,app,_=client;r=c.get('/')
    assert r.status_code==200
    assert app.state.token in r.text
    assert 'assets/index-' in r.text


def test_usage_snapshots_are_not_double_counted(client):
    c,app,tmp=client;store=app.state.store;p=store.add(tmp/'counter')
    store.event(p['id'],'helper',event='start',subagent_id='sw-developer')
    for n in [10,20,30]:
        store.event(p['id'],'usage',role='sw-developer',usage={'input_tokens':n,'cached_input_tokens':5,'output_tokens':2})
    result=c.get('/api/projects/'+p['id']+'/usage').json()['total']
    assert result['prompt']==30;assert result['cache_read']==5;assert result['api_calls']==1


def test_model_discovery_cache_refresh_and_visible_status(client,monkeypatch):
    c,app,_=client;calls=[]
    def discover(conn):
        calls.append(conn['engine'])
        return dict(models=['discovered-model'],default_model='discovered-model',state='ready',message='Catalogue connected.',source='provider')
    monkeypatch.setattr('appling.server.connections.discover',discover)
    first=c.get('/api/settings/models').json()
    assert all('discovered-model' in p['models'] for p in first['providers'])
    assert all(p['status']['message']=='Catalogue connected.' for p in first['providers'])
    count=len(calls);c.get('/api/settings/models');assert len(calls)==count
    c.get('/api/settings/models?refresh=true');assert len(calls)>count


def test_connection_test_uses_selected_saved_connection_and_model(client,monkeypatch):
    c,app,_=client;calls=[]
    def test(conn,model):
        calls.append((conn,model));return dict(ok=True,state='connected',message='Responded.',model=model,latency_ms=10)
    monkeypatch.setattr('appling.server.connections.test_connection',test)
    response=c.post('/api/settings/connections/codex/test',json={'model':'chosen-coder'})
    assert response.json()['ok'];assert calls[0][0]['engine']=='codex';assert calls[0][1]=='chosen-coder'
    assert c.post('/api/settings/connections/missing/test',json={'model':'anything'}).status_code==400


def test_agent_slots_are_separate_from_concurrent_project_limit(client):
    c,app,tmp=client
    updated=c.post('/api/settings',json={'parallel_work':{'agents_per_project':4}})
    assert updated.status_code==200
    config=updated.json()['parallel_work']
    assert config['agents_per_project']==4 and config['max_workers']==3
    assert c.post('/api/settings',json={'parallel_work':{'max_workers':2}}).json()['parallel_work']['agents_per_project']==4
    assert c.post('/api/settings',json={'parallel_work':{'agents_per_project':7}}).status_code==400
    p=app.state.store.add(tmp/'workers')
    app.state.store.update(p['id'],workers=[dict(id='w',task_id='a',role='sw-developer',status='running',goal='feature')])
    assert c.get('/api/projects/'+p['id']).json()['task_workers'][0]['task_id']=='a'


def test_interleaved_worker_usage_is_counted_per_invocation(client):
    c,app,tmp=client;store=app.state.store;p=store.add(tmp/'parallel-counter')
    for run_id in ['worker-a','worker-b']:
        store.event(p['id'],'helper',event='start',subagent_id=run_id,run_id=run_id)
    for ident,prompt in [('worker-a',10),('worker-b',20),('worker-a',30)]:
        store.event(p['id'],'usage',role='sw-developer',run_id=ident,usage=dict(input_tokens=prompt,output_tokens=2))
    total=c.get('/api/projects/'+p['id']+'/usage').json()['total']
    assert total['prompt']==50 and total['api_calls']==2


def test_new_projects_default_to_blocks_with_mandatory_design_and_qa(client):
    c,app,tmp=client
    p=c.post('/api/projects',json=dict(path=str(tmp/'simple'),create=True)).json()
    assert p['execution_mode']=='blocks'
    assert {'req-engineer','ui-designer','sw-developer','qa-engineer'}<=set(p['team'])
    names=[row['name'] for row in c.get('/api/projects/'+p['id']+'/map').json()['phases']]
    assert names[:6]==['Requirements','Design','Block plan','Building blocks','Merging into the app','Quality assurance']
    assert c.get('/api/projects/'+p['id']+'/blocks').json()==dict(exists=False,blocks=[],phase='requirements')
    assert 'blocks' in c.get('/api/library').json()
    direct=c.post('/api/projects',json=dict(path=str(tmp/'direct'),create=True,execution_mode='direct')).json()
    assert direct['execution_mode']=='direct'
    names=[row['name'] for row in c.get('/api/projects/'+direct['id']+'/map').json()['phases']]
    assert 'Task planning' not in names and 'Block plan' not in names and 'Development' in names


def test_changing_coordination_preserves_approvals_files_and_retained_workers(client):
    c,app,tmp=client;store=app.state.store
    p=store.add(tmp/'legacy',execution_mode='planned')
    root=Path(p['root']);(root/'source.txt').write_text('retained code')
    workers=[dict(id='old',task_id='old-feature',role='sw-developer',status='blocked',workspace=str(root),goal='Retained feature')]
    approvals=dict(requirements='unchanged',prototype='unchanged',plan='unchanged')
    store.update(p['id'],phase='build',paused=True,workers=workers,approvals=approvals,tasks=[dict(id='old-feature',status='pending')])
    response=c.post('/api/projects/'+p['id']+'/settings',json=dict(execution_mode='direct'))
    assert response.status_code==200
    state=store.get(p['id'])
    assert state['execution_mode']=='direct' and state['paused'] and not state['running']
    assert state['approvals']==approvals and state['workers']==workers
    assert (root/'source.txt').read_text()=='retained code'
    assert not app.state.workflow.active
    with store.connect() as db:
        history=json.loads(db.execute("select data from checkpoints where project=? and role like 'execution-history:%'",(p['id'],)).fetchone()[0])
    assert history['tasks']==[dict(id='old-feature',status='pending')]
    store.update(p['id'],running=True)
    before=store.get(p['id'])
    assert c.post('/api/projects/'+p['id']+'/settings',json=dict(execution_mode='planned')).status_code==400
    assert store.get(p['id'])==before
