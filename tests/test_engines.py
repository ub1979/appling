import json
import sys
import time
import textwrap
import threading
from pathlib import Path
import httpx
import pytest
from appling.engines import Run, result_json
from appling.engines.codex import execute as codex_execute
from appling.engines.cli import execute as cli_execute
from appling.engines.api import execute as api_execute


def executable(tmp_path,source):
    path=tmp_path/'fake-engine'
    path.write_text('#!'+sys.executable+'\n'+textwrap.dedent(source));path.chmod(0o755)
    return str(path)


def test_codex_real_subprocess_protocol_routes_approvals_and_resumes(tmp_path):
    binary=executable(tmp_path,'''
        import sys,json
        def send(x): print(json.dumps(x),flush=True)
        for line in sys.stdin:
            m=json.loads(line);method=m.get('method')
            if method=='initialize': send({'id':m['id'],'result':{}})
            elif method in ['thread/start','thread/resume']:
                assert m['params']['sandbox']=='workspace-write'
                if method=='thread/resume': assert m['params']['threadId']=='saved-thread'
                send({'id':m['id'],'result':{'thread':{'id':'saved-thread'}}})
            elif method=='turn/start':
                send({'id':m['id'],'result':{'turn':{'id':'turn-1'}}})
                send({'id':800,'method':'item/commandExecution/requestApproval','params':{'command':'npm test'}})
            elif m.get('id')==800:
                assert m['result']['decision']=='accept'
                send({'id':801,'method':'item/tool/requestUserInput','params':{'questions':[{'id':'q','question':'Pick one','options':[{'label':'A'}]}]}})
            elif m.get('id')==801:
                assert m['result']['answers']['q']['answers']==['A']
                send({'method':'thread/tokenUsage/updated','params':{'threadId':'saved-thread','tokenUsage':{'last':{'inputTokens':100,'cachedInputTokens':80,'outputTokens':10}}}})
                send({'method':'item/completed','params':{'threadId':'saved-thread','item':{'type':'agentMessage','text':json.dumps({'summary':'Built','status':'completed'})}}})
                send({'method':'turn/completed','params':{'threadId':'saved-thread','turn':{'id':'turn-1','status':'completed'}}})
    ''')
    sessions=[];usage=[];questions=[]
    def ask(kind,question,choices):
        questions.append(kind);return 'once' if kind=='approval' else 'A'
    run=Run(tmp_path,'stable instructions','Build it',session='saved-thread',ask=ask,save_session=sessions.append,save_usage=usage.append)
    result=codex_execute({'binary':binary,'timeout':10},run)
    assert result['status']=='completed';assert sessions==['saved-thread']
    assert questions==['approval','question'];assert usage[0]['last']['cachedInputTokens']==80


@pytest.mark.parametrize('engine',['claude-cli','copilot'])
def test_cli_uses_structured_result_and_requires_task_permission(tmp_path,engine):
    binary=executable(tmp_path,'''
        import json,sys
        if '--print' in sys.argv:
            assert '--reasoning-effort' not in sys.argv
            assert '--effort' in sys.argv
            print(json.dumps({'type':'system','session_id':'claude-session'}))
            print(json.dumps({'type':'result','result':json.dumps({'summary':'Built','status':'completed'}),'usage':{'input_tokens':10}}))
        else:
            assert '--reasoning-effort' in sys.argv
            print(json.dumps({'type':'assistant.message','data':{'content':json.dumps({'summary':'Built','status':'completed'})}}))
    ''')
    asks=[]
    def allow(*args):asks.append(args);return 'once'
    result=cli_execute({'engine':engine,'binary':binary},Run(tmp_path,'instructions','task',ask=allow,effort='high'))
    assert result['status']=='completed';assert asks
    with pytest.raises(PermissionError):
        cli_execute({'engine':engine,'binary':binary},Run(tmp_path,'instructions','task'))


def test_copilot_answer_survives_its_closing_result_event_without_text(tmp_path):
    """Copilot sends its answer in assistant.message and then a result event carrying only usage."""
    binary=executable(tmp_path,'''
        import json,sys
        answer=json.dumps({'summary':'Built','status':'completed'}) if '--allow-tool' in sys.argv or '--deny-tool' in sys.argv else 'pong'
        print(json.dumps({'type':'assistant.message','data':{'content':answer}}),flush=True)
        print(json.dumps({'type':'result','usage':{'premiumRequests':1}}),flush=True)
    ''')
    usage=[]
    result=cli_execute({'engine':'copilot','binary':binary},Run(tmp_path,'instructions','task',readonly=True,save_usage=usage.append))
    assert result['status']=='completed' and result['summary']=='Built' and usage==[{'premiumRequests':1}]
    probe=cli_execute({'engine':'copilot','binary':binary},Run(tmp_path,'instructions','ping',readonly=True,connection_test=True))
    assert probe['summary']


def test_cli_task_that_keeps_reporting_outlasts_the_limit_but_silence_and_probes_still_time_out(tmp_path):
    busy=executable(tmp_path,'''
        import json,sys,time
        for _ in range(8):
            print(json.dumps({'type':'assistant','message':{'content':[{'type':'tool_use','id':'t','name':'Bash'}]}}),flush=True)
            time.sleep(.15)
        print(json.dumps({'type':'result','result':json.dumps({'summary':'Built','status':'completed'})}),flush=True)
    ''')
    # 1.2 seconds of steady work against a 0.6 second limit: only silence may end a real task.
    result=cli_execute({'engine':'claude-cli','binary':busy,'timeout':.6},Run(tmp_path,'instructions','task',readonly=True))
    assert result['status']=='completed'
    silent=tmp_path/'silent';silent.mkdir()
    quiet=executable(silent,'import time\ntime.sleep(30)\n')
    started=time.monotonic()
    with pytest.raises(TimeoutError,match='no activity'):
        cli_execute({'engine':'claude-cli','binary':quiet,'timeout':.5},Run(tmp_path,'instructions','task',readonly=True))
    assert time.monotonic()-started<10
    with pytest.raises(TimeoutError,match='did not respond'):
        cli_execute({'engine':'claude-cli','binary':busy,'timeout':.5},Run(tmp_path,'instructions','task',readonly=True,connection_test=True))


def test_api_tool_loop_writes_project_and_keeps_prompt_prefix_on_resume(tmp_path,monkeypatch):
    requests=[];sessions=[]
    def handler(request):
        body=json.loads(request.content);requests.append(body)
        if len(requests)==1:
            return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':None,'tool_calls':[
                {'id':'write-1','type':'function','function':{'name':'write_file','arguments':json.dumps({'path':'app.js','content':'export const value = 1;'})}}]}}],
                'usage':{'prompt_tokens':100,'completion_tokens':10,'prompt_tokens_details':{'cached_tokens':50}}})
        return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':json.dumps({'summary':'Done','status':'completed'})}}],
            'usage':{'prompt_tokens':120,'completion_tokens':10,'prompt_tokens_details':{'cached_tokens':100}}})
    original=httpx.Client
    monkeypatch.setattr('appling.engines.api.httpx.Client',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    conn={'engine':'ollama','base_url':'http://local.test/v1'}
    run=Run(tmp_path,'stable instructions','Build value',model='local-model',save_session=sessions.append)
    assert api_execute(conn,run)['status']=='completed'
    assert (tmp_path/'app.js').read_text()=='export const value = 1;'
    run.session=sessions[-1];run.prompt='Explain value'
    api_execute(conn,run)
    assert requests[2]['messages'][:len(requests[1]['messages'])]==requests[1]['messages']
    assert requests[0]['tools']==requests[2]['tools']


def test_anthropic_uses_messages_protocol(tmp_path,monkeypatch):
    captured=[]
    def handler(request):
        captured.append((request.url.path,json.loads(request.content)))
        return httpx.Response(200,json={'content':[{'type':'text','text':'{"summary":"Ready","question":"Who uses it?"}'}],'usage':{'input_tokens':5,'output_tokens':5}})
    original=httpx.Client
    monkeypatch.setattr('appling.engines.api.httpx.Client',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    result=api_execute({'engine':'anthropic','base_url':'https://api.test/v1'},Run(tmp_path,'instructions','interview',model='my-claude'))
    assert result['question']=='Who uses it?';assert captured[0][0]=='/v1/messages'
    assert captured[0][1]['system']=='instructions'


def test_unstructured_response_never_implies_completed():
    with pytest.raises(ValueError):result_json('Everything is done, probably.')


def test_api_context_recovery_preserves_old_transcript(tmp_path,monkeypatch):
    saved=tmp_path/'.appling/sessions';saved.mkdir(parents=True)
    old_id='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
    old=[{'role':'system','content':'stable'},{'role':'user','content':'x'*20000},{'role':'assistant','content':'old answer'}]
    path=saved/(old_id+'.json');path.write_text(json.dumps(old));before=path.read_bytes()
    captured=[];sessions=[]
    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':'{"summary":"resumed"}'}}]})
    original=httpx.Client
    monkeypatch.setattr('appling.engines.api.httpx.Client',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    run=Run(tmp_path,'stable','Continue current task',session=old_id,model='local',save_session=sessions.append)
    api_execute({'engine':'ollama','context_chars':8000},run)
    assert json.loads(path.read_text())[:len(old)]==json.loads(before)
    assert sessions[-1]!=old_id
    assert 'Context recovery' in captured[0]['messages'][1]['content']


def test_api_interrupted_exchange_starts_new_session_with_valid_roles(tmp_path,monkeypatch):
    folder=tmp_path/'.appling/sessions';folder.mkdir(parents=True)
    sid='bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
    (folder/(sid+'.json')).write_text(json.dumps([{'role':'system','content':'stable'},{'role':'user','content':'unfinished task'}]))
    captured=[];sessions=[]
    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':'{"summary":"resumed"}'}}]})
    original=httpx.Client
    monkeypatch.setattr('appling.engines.api.httpx.Client',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    api_execute({'engine':'ollama'},Run(tmp_path,'stable','Continue',session=sid,save_session=sessions.append))
    assert sessions[-1]!=sid
    assert [m['role'] for m in captured[0]['messages']]==['system','user']
