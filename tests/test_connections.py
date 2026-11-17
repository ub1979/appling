import json
import sys
import textwrap
import httpx
from appling import connections
from appling.engines import environment


def executable(tmp_path,source):
    path=tmp_path/'engine';path.write_text('#!'+sys.executable+'\n'+textwrap.dedent(source));path.chmod(0o755)
    return str(path)


def test_codex_catalogue_uses_live_rpc_with_pagination_and_account(tmp_path):
    binary=executable(tmp_path,'''
        import sys,json
        for line in sys.stdin:
            m=json.loads(line);method=m.get('method');r={}
            if method=='initialized':continue
            if method=='account/read':r={'account':{'type':'chatgpt'},'requiresOpenaiAuth':True}
            if method=='model/list':
                r={'data':[{'model':'coder-two','isDefault':True}],'nextCursor':None} if m['params']['cursor'] else {'data':[{'model':'coder-one'},{'model':'hidden','hidden':True}],'nextCursor':'page-two'}
            print(json.dumps({'id':m['id'],'result':r}),flush=True)
    ''')
    result=connections.discover({'engine':'codex','binary':binary,'models':['manual-coder']})
    assert result['models']==['coder-one','coder-two','manual-coder']
    assert result['default_model']=='coder-two';assert result['state']=='ready'


def test_copilot_models_come_from_acp_session(tmp_path):
    binary=executable(tmp_path,'''
        import sys,json
        for line in sys.stdin:
            m=json.loads(line)
            r={'protocolVersion':1} if m['method']=='initialize' else {'models':{'availableModels':[{'modelId':'available-copilot-model'}],'currentModelId':'available-copilot-model'}}
            print(json.dumps({'id':m['id'],'result':r}),flush=True)
    ''')
    result=connections.discover({'engine':'copilot','binary':binary})
    assert result['models']==['available-copilot-model'];assert result['state']=='ready'


def test_claude_aliases_do_not_claim_account_catalogue_or_successful_login(tmp_path):
    binary=executable(tmp_path,"print('{\"loggedIn\":false}')")
    result=connections.discover({'engine':'claude-cli','binary':binary})
    assert result['state']=='login_required';assert result['source']=='documented_models'
    assert 'sonnet' in result['models'];assert 'claude auth login' in result['message']
    assert {'claude-sonnet-4-6','claude-opus-4-6'}<=set(result['models'])


def mock_http(monkeypatch,handler):
    original=httpx.Client
    monkeypatch.setattr(connections.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))


def test_ollama_discovers_models_without_forwarding_openai_key(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','private-openai-key')
    def handler(request):
        assert request.url.path=='/v1/models';assert 'authorization' not in request.headers
        return httpx.Response(200,json={'data':[{'id':'local-code-model'}]})
    mock_http(monkeypatch,handler)
    result=connections.discover({'engine':'ollama','base_url':'http://127.0.0.1:11434','models':['saved-model']})
    assert result['models']==['local-code-model','saved-model'];assert result['state']=='ready'


def test_api_catalogue_auth_errors_are_visible_without_leaking_provider_body(monkeypatch):
    monkeypatch.setenv('CATALOG_KEY','private-key')
    mock_http(monkeypatch,lambda request:httpx.Response(401,json={'error':'private-key'}))
    result=connections.discover({'engine':'openai-compatible','api_key_env':'CATALOG_KEY','models':['manual-model']})
    assert result['state']=='error';assert 'Authentication' in result['message']
    assert 'private-key' not in json.dumps(result);assert result['models']==['manual-model']


def test_selected_api_model_is_requested_without_tools_or_project_data(monkeypatch):
    monkeypatch.setenv('TEST_MODEL_KEY','secret');captured=[]
    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200,json={'model':'resolved-model','choices':[{'message':{'content':'OK'}}]})
    mock_http(monkeypatch,handler)
    result=connections.test_connection({'engine':'openai-compatible','api_key_env':'TEST_MODEL_KEY'},'chosen-model')
    assert result['ok'];assert result['model']=='resolved-model'
    assert captured[0]['model']=='chosen-model';assert 'tools' not in captured[0]
    assert all('project' not in m['content'].lower() for m in captured[0]['messages'])


def test_missing_key_and_empty_model_fail_before_network(monkeypatch):
    monkeypatch.delenv('UNSET_TEST_KEY',raising=False)
    def fail(*args,**kwargs):raise AssertionError('No network call expected')
    monkeypatch.setattr(connections.httpx,'Client',fail)
    result=connections.test_connection({'engine':'openai-compatible','api_key_env':'UNSET_TEST_KEY'},'some-model')
    assert not result['ok'];assert 'UNSET_TEST_KEY' in result['message']
    result=connections.test_connection({'engine':'ollama'},'')
    assert not result['ok'];assert 'model' in result['message']


def test_claude_connection_test_disables_tools_and_session_persistence(tmp_path):
    binary=executable(tmp_path,'''
        import json,sys
        assert sys.argv[sys.argv.index('--tools')+1]==''
        assert '--no-session-persistence' in sys.argv
        print(json.dumps({'type':'result','result':'{"summary":"OK"}'}))
    ''')
    assert connections.test_connection({'engine':'claude-cli','binary':binary},'sonnet')['ok']


def test_copilot_token_is_passed_to_cli_environment(monkeypatch):
    monkeypatch.setenv('COPILOT_GITHUB_TOKEN','test-token')
    assert environment()['COPILOT_GITHUB_TOKEN']=='test-token'


def test_claude_plain_success_reports_actual_model_and_stdin_eof(tmp_path):
    binary=executable(tmp_path,'''
        import sys,json
        assert sys.stdin.read()==''
        assert sys.argv[sys.argv.index('--output-format')+1]=='json'
        assert '--permission-mode' not in sys.argv
        print(json.dumps({'type':'result','result':'OK','modelUsage':{'claude-sonnet-4-6':{'inputTokens':2}}}))
    ''')
    result=connections.test_connection({'engine':'claude-cli','binary':binary},'sonnet')
    assert result['ok'];assert result['model']=='claude-sonnet-4-6'


def test_claude_errors_from_stdout_are_actionable_and_redacted(tmp_path,monkeypatch):
    monkeypatch.setenv('ANTHROPIC_AUTH_TOKEN','private-test-credential')
    binary=executable(tmp_path,'''
        import os,json
        print(json.dumps({'type':'result','is_error':True,'errors':['Login expired for '+os.environ['ANTHROPIC_AUTH_TOKEN']+'; run claude auth login']}))
    ''')
    result=connections.test_connection({'engine':'claude-cli','binary':binary},'sonnet')
    assert not result['ok'];assert 'Login expired' in result['message']
    assert 'claude auth login' in result['message']
    assert 'private-test-credential' not in result['message'];assert '[REDACTED]' in result['message']


def test_claude_custom_config_used_for_both_login_and_inference(tmp_path,monkeypatch):
    monkeypatch.setenv('CLAUDE_CONFIG_DIR',str(tmp_path/'my-login'))
    monkeypatch.setenv('CLAUDECODE','parent-session')
    binary=executable(tmp_path,'''
        import sys,os,json
        assert os.environ['CLAUDE_CONFIG_DIR'].endswith('my-login')
        assert 'CLAUDECODE' not in os.environ
        if 'auth' in sys.argv:print(json.dumps({'loggedIn':True}))
        else:print(json.dumps({'type':'result','result':'OK'}))
    ''')
    conn={'engine':'claude-cli','binary':binary}
    assert connections.discover(conn)['state']=='ready'
    assert connections.test_connection(conn,'sonnet')['ok']


def test_claude_pretty_printed_json_result_is_parsed_as_an_envelope(tmp_path):
    binary=executable(tmp_path,'''
        import json
        print(json.dumps({'type':'result','result':'OK','modelUsage':{'versioned-model':{}}},indent=2))
    ''')
    result=connections.test_connection({'engine':'claude-cli','binary':binary},'sonnet')
    assert result['ok'];assert result['model']=='versioned-model'
