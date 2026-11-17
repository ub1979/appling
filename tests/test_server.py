from pathlib import Path
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
