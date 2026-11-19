"""Native Codex protocol behavior using real controlled child processes."""
import concurrent.futures
import json
import os
import signal
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest
from appling.engines import Run
from appling.engines.codex import execute
from appling.engines.codex import _IdleTimer


def binary(tmp_path, source):
    path = tmp_path / 'codex-test'
    path.write_text('#!' + sys.executable + '\n' + textwrap.dedent(source))
    path.chmod(0o755)
    return str(path)


PRELUDE = '''
import json,sys

def send(data): print(json.dumps(data),flush=True)
for line in sys.stdin:
 m=json.loads(line); method=m.get('method')
 if method=='initialize': send({'id':m['id'],'result':{}})
 elif method in ['thread/start','thread/resume']:
  send({'id':m['id'],'result':{'thread':{'id':'root'}}})
 elif method=='turn/start':
  send({'id':m['id'],'result':{'turn':{'id':'root-turn'}}})
'''


def test_native_children_do_not_overwrite_root_result_and_stream_progress(tmp_path):
    exe = binary(tmp_path, PRELUDE + '''
  send({'method':'item/started','params':{'threadId':'root','item':{
    'id':'spawn','type':'collabAgentToolCall','tool':'spawnAgent','status':'inProgress',
    'receiverThreadIds':['child'],'senderThreadId':'root','agentsStates':{'child':{'status':'running'}},'prompt':'Review API contract'}}})
  send({'method':'item/agentMessage/delta','params':{'threadId':'root','itemId':'answer','delta':'{"status":"completed"}'}})
  send({'method':'item/completed','params':{'threadId':'root','item':{'id':'answer','type':'agentMessage','phase':'final_answer','text':'{"status":"completed"}'}}})
  send({'method':'item/completed','params':{'threadId':'child','item':{'id':'child-answer','type':'agentMessage','text':'not a root result'}}})
  send({'method':'turn/completed','params':{'threadId':'child','turn':{'id':'child-turn','status':'completed'}}})
  send({'method':'item/completed','params':{'threadId':'root','item':{
    'id':'wait','type':'collabAgentToolCall','tool':'wait','status':'completed',
    'receiverThreadIds':['child'],'senderThreadId':'root','agentsStates':{'child':{'status':'completed'}}}}})
  send({'method':'turn/completed','params':{'threadId':'root','turn':{'id':'root-turn','status':'completed'}}})
''')
    events = []
    result = execute({'binary':exe}, Run(tmp_path,'instructions','task',emit=lambda kind,**data: events.append(dict(type=kind,**data))))
    assert result['status'] == 'completed'
    assert any(e['type']=='worker_delta' and e['thread_id']=='root' for e in events)
    starts = [e for e in events if e['type']=='helper' and e['event']=='start']
    ends = [e for e in events if e['type']=='helper' and e['event']=='complete']
    assert starts[0]['subagent_id']==ends[0]['subagent_id']=='codex:child'
    assert ends[0]['status']=='completed'


def test_multiple_native_approvals_wait_concurrently_and_keep_correct_shapes(tmp_path):
    exe = binary(tmp_path, PRELUDE + '''
  responses={}
  send({'id':501,'method':'item/commandExecution/requestApproval','params':{'threadId':'root','command':'npm test','cwd':'/workspace'}})
  send({'id':502,'method':'item/permissions/requestApproval','params':{'threadId':'child','permissions':{'network':{'enabled':True}},'reason':'Fetch dependency metadata'}})
 elif m.get('id') in [501,502] and 'result' in m:
  responses[m['id']]=m['result']
  if len(responses)==2:
   assert responses[501]=={'decision':'accept'},responses
   assert responses[502]=={'permissions':{},'scope':'turn'},responses
   send({'method':'item/completed','params':{'threadId':'root','item':{'type':'agentMessage','text':'{"status":"completed"}'}}})
   send({'method':'turn/completed','params':{'threadId':'root','turn':{'status':'completed'}}})
''')
    barrier = threading.Barrier(2)
    questions = []
    def ask(kind, question, choices):
        questions.append(question)
        barrier.wait(timeout=2)
        return 'deny' if 'Fetch dependency' in question else 'once'
    result = execute({'binary':exe,'timeout':5}, Run(tmp_path,'instructions','task',ask=ask))
    assert result['status']=='completed'
    assert any('npm test' in q and '/workspace' in q for q in questions)
    assert any('"enabled": true' in q for q in questions)


def test_permission_acceptance_is_scoped_to_turn_and_contains_exact_profile(tmp_path):
    exe = binary(tmp_path, PRELUDE + '''
  send({'id':501,'method':'item/permissions/requestApproval','params':{'permissions':{'fileSystem':{'write':['/workspace/reports']}}}})
 elif m.get('id')==501 and 'result' in m:
  assert m['result']=={'permissions':{'fileSystem':{'write':['/workspace/reports']}},'scope':'turn'}
  send({'method':'item/completed','params':{'item':{'type':'agentMessage','text':'{"status":"completed"}'}}})
  send({'method':'turn/completed','params':{'turn':{'status':'completed'}}})
''')
    assert execute({'binary':exe}, Run(tmp_path,'instructions','task',ask=lambda *args:'once'))['status']=='completed'


def test_stop_interrupts_root_and_child_even_with_pending_human_input(tmp_path):
    logfile = tmp_path/'interrupts.jsonl'
    exe = binary(tmp_path, 'import signal\nsignal.signal(signal.SIGTERM,lambda *args: None)\n' + PRELUDE + f'''
  send({{'method':'turn/started','params':{{'threadId':'child','turn':{{'id':'child-turn'}}}}}})
  send({{'id':501,'method':'item/commandExecution/requestApproval','params':{{'threadId':'child','command':'npm test'}}}})
 elif method=='turn/interrupt':
  with open({str(logfile)!r},'a') as out: out.write(json.dumps(m['params'])+'\\n');out.flush()
  if sum(1 for _ in open({str(logfile)!r}))==2: sys.exit(0)
''')
    cancel=threading.Event();waiting=threading.Event()
    def ask(*args):
        waiting.set()
        cancel.wait(2)
        return 'deny'
    with concurrent.futures.ThreadPoolExecutor() as pool:
        future=pool.submit(execute,{'binary':exe,'timeout':5},Run(tmp_path,'instructions','task',cancel=cancel,ask=ask))
        assert waiting.wait(2)
        cancel.set()
        with pytest.raises(InterruptedError): future.result(timeout=5)
    interrupted=[json.loads(line) for line in logfile.read_text().splitlines()]
    assert {(i['threadId'],i['turnId']) for i in interrupted}=={('root','root-turn'),('child','child-turn')}


def test_native_stderr_credentials_are_redacted(tmp_path,monkeypatch):
    secret='private-codex-token-123456789';monkeypatch.setenv('CODEX_TEST_TOKEN',secret)
    exe=binary(tmp_path, '''
import sys,time
sys.stderr.write('private-codex-token-123456789');sys.stderr.flush();time.sleep(.05)
sys.exit(1)
''')
    with pytest.raises(RuntimeError) as exc:
        execute({'binary':exe},Run(tmp_path,'instructions','task'))
    assert secret not in str(exc.value)
    assert '[REDACTED]' in str(exc.value)


@pytest.mark.parametrize('resume',[False,True])
def test_managed_swarm_thread_disables_untracked_nested_agents(tmp_path,resume):
    exe=binary(tmp_path, '''
import json,sys
for line in sys.stdin:
 m=json.loads(line);method=m.get('method')
 if method=='initialize':print(json.dumps({'id':m['id'],'result':{}}),flush=True)
 elif method in ['thread/start','thread/resume']:
  assert m['params']['config']=={'features.multi_agent':False,'features.multi_agent_v2':False}
  assert m['params']['sandbox']=='workspace-write'
  print(json.dumps({'id':m['id'],'result':{'thread':{'id':'worker'}}}),flush=True)
 elif method=='turn/start':
  print(json.dumps({'id':m['id'],'result':{'turn':{'id':'turn'}}}),flush=True)
  print(json.dumps({'method':'item/completed','params':{'item':{'type':'agentMessage','text':'{"status":"completed"}'}}}),flush=True)
  print(json.dumps({'method':'turn/completed','params':{'turn':{'status':'completed'}}}),flush=True)
''')
    result=execute({'binary':exe},Run(tmp_path,'instructions','task',managed_worker=True,session='worker' if resume else None))
    assert result['status']=='completed'


def test_direct_codex_enables_native_agents_and_reports_peer_communication(tmp_path):
    exe=binary(tmp_path, '''
import json,sys
def send(data):print(json.dumps(data),flush=True)
for line in sys.stdin:
 m=json.loads(line);method=m.get('method')
 if method=='initialize':send({'id':m['id'],'result':{}})
 elif method=='thread/start':
  assert m['params']['config']=={'features.multi_agent':True,'features.multi_agent_v2':True}
  assert m['params']['approvalPolicy']=='on-request'
  assert m['params']['sandbox']=='workspace-write'
  send({'id':m['id'],'result':{'thread':{'id':'root'}}})
 elif method=='turn/start':
  send({'id':m['id'],'result':{'turn':{'id':'build'}}})
  for tool in ['spawnAgent','sendInput','wait']:
   send({'method':'item/completed','params':{'threadId':'root','item':{'id':tool,'type':'collabAgentToolCall',
    'tool':tool,'status':'completed','receiverThreadIds':['specialist'],
    'agentsStates':{'specialist':{'status':'completed' if tool=='wait' else 'running'}},'prompt':'Use the shared API contract'}}})
  send({'method':'item/completed','params':{'threadId':'root','item':{'type':'agentMessage','text':'{"status":"completed"}'}}})
  send({'method':'turn/completed','params':{'threadId':'root','turn':{'status':'completed'}}})
''')
    events=[]
    result=execute({'binary':exe},Run(tmp_path,'direct instructions','task',native_delegation=True,
        emit=lambda kind,**data:events.append(dict(type=kind,**data))))
    assert result['status']=='completed'
    assert [e['tool'] for e in events if e['type']=='native_agent']==['spawnAgent','sendInput','wait']
    assert any(e['type']=='helper' and e['event']=='start' for e in events)
    assert any(e['type']=='helper' and e['event']=='complete' for e in events)


def test_idle_budget_renews_and_multiple_human_decisions_suspend_it():
    now=[0]
    timer=_IdleTimer(1800,clock=lambda:now[0])
    now[0]=1799
    assert not timer.expired()
    timer.activity()
    now[0]=3000
    assert not timer.expired()  # Total runtime may exceed thirty minutes.
    timer.waiting('first');timer.waiting('second')
    now[0]=10000
    assert not timer.expired()
    timer.answered('first')
    now[0]=20000
    assert not timer.expired()
    timer.answered('second')
    now[0]=21799
    assert not timer.expired()
    now[0]=21800
    assert timer.expired()


@pytest.mark.parametrize('method,thread',[
    ('item/agentMessage/delta','root'),
    ('item/reasoning/summaryTextDelta','root'),
    ('item/commandExecution/outputDelta','root'),
    ('item/mcpToolCall/progress','root'),
    ('item/reasoning/textDelta','child'),
])
def test_live_task_activity_outlasts_old_total_deadline(tmp_path,method,thread):
    exe=binary(tmp_path,'import time\n'+PRELUDE+f'''
  send({{'method':'item/started','params':{{'threadId':'root','item':{{
   'id':'spawn','type':'collabAgentToolCall','receiverThreadIds':['child'],
   'agentsStates':{{'child':{{'status':'running'}}}}}}}}}})
  for i in range(8):
   time.sleep(.15)
   send({{'method':{method!r},'params':{{'threadId':{thread!r},'itemId':'work','delta':'working'}}}})
  open('retained-work.txt','w').write('built across the old deadline')
  send({{'method':'item/completed','params':{{'threadId':'root','item':{{'type':'agentMessage','text':'{{"status":"completed"}}'}}}}}})
  send({{'method':'turn/completed','params':{{'threadId':'root','turn':{{'status':'completed'}}}}}})
''')
    started=time.monotonic()
    assert execute({'binary':exe,'timeout':.6},Run(tmp_path,'instructions','task'))['status']=='completed'
    assert time.monotonic()-started>1
    assert (tmp_path/'retained-work.txt').read_text()=='built across the old deadline'


@pytest.mark.parametrize('noise',[False,True])
def test_inactive_task_times_out_even_with_unrelated_traffic_and_is_reaped(tmp_path,monkeypatch,noise):
    import subprocess
    processes=[];popen=subprocess.Popen
    def capture(*args,**kwargs):
        proc=popen(*args,**kwargs);processes.append(proc);return proc
    monkeypatch.setattr('appling.engines.codex.subprocess.Popen',capture)
    exe=binary(tmp_path,'import time\n'+PRELUDE+f'''
  open('checkpoint.txt','w').write('saved work')
  for i in range(50):
   time.sleep(.04)
   if {noise!r}:
    send({{'method':'transport/keepalive','params':{{}}}})
    send({{'method':'item/agentMessage/delta','params':{{'threadId':'unrelated','delta':'unrelated work'}}}})
''')
    started=time.monotonic()
    with pytest.raises(TimeoutError,match='Paused for inactivity'):
        execute({'binary':exe,'timeout':10,'idle_timeout':.3},Run(tmp_path,'instructions','task'))
    assert time.monotonic()-started<2
    assert processes[0].poll() is not None
    assert (tmp_path/'checkpoint.txt').read_text()=='saved work'


def test_waiting_for_owner_input_does_not_consume_inactivity_budget(tmp_path):
    exe=binary(tmp_path,PRELUDE+'''
  send({'id':501,'method':'item/tool/requestUserInput','params':{'questions':[{'id':'q','question':'Choose','options':[{'label':'A'}]}]}})
 elif m.get('id')==501 and 'result' in m:
  assert m['result']['answers']['q']['answers']==['A']
  send({'method':'item/completed','params':{'item':{'type':'agentMessage','text':'{"status":"completed"}'}}})
  send({'method':'turn/completed','params':{'turn':{'status':'completed'}}})
''')
    def ask(*args):
        time.sleep(.7)
        return 'A'
    assert execute({'binary':exe,'idle_timeout':.3},Run(tmp_path,'instructions','task',ask=ask))['status']=='completed'


def test_connection_probe_keeps_a_total_deadline_despite_activity(tmp_path):
    exe=binary(tmp_path,'import time\n'+PRELUDE+'''
  for i in range(50):
   time.sleep(.04)
   send({'method':'item/reasoning/textDelta','params':{'threadId':'root','delta':'working'}})
''')
    with pytest.raises(TimeoutError,match='request timed out'):
        execute({'binary':exe,'timeout':.3},Run(tmp_path,'instructions','task',connection_test=True))


@pytest.mark.parametrize('seconds',[0,-1,float('inf'),float('nan')])
def test_invalid_idle_budget_is_rejected_before_starting_process(tmp_path,seconds):
    with pytest.raises(ValueError,match='inactivity timeout'):
        execute({'binary':'missing-codex','idle_timeout':seconds},Run(tmp_path,'instructions','task'))


def test_sub_agent_activity_items_report_child_lifecycle_without_invented_goals(tmp_path):
    exe=binary(tmp_path, PRELUDE+'''
  for item_id,kind in [('a1','started'),('a2','interacted'),('a3','completed'),('b1','started'),('b2','interrupted')]:
   child='child-1' if item_id[0]=='a' else 'child-2'
   send({'method':'item/started','params':{'threadId':'root','item':{'id':item_id,'type':'subAgentActivity','kind':kind,
    'agentThreadId':child,'agentPath':'root/frontend' if child=='child-1' else None,'model':'gpt-test','reasoningEffort':None}}})
  send({'method':'thread/tokenUsage/updated','params':{'threadId':'child-1','tokenUsage':{'total':{'inputTokens':5}}}})
  send({'method':'item/completed','params':{'threadId':'root','item':{'type':'agentMessage','text':'{"status":"completed"}'}}})
  send({'method':'turn/completed','params':{'threadId':'root','turn':{'status':'completed'}}})
''')
    events=[]
    result=execute({'binary':exe},Run(tmp_path,'direct instructions','task',native_delegation=True,
        emit=lambda kind,**data:events.append(dict(type=kind,**data))))
    assert result['status']=='completed'
    helpers=[e for e in events if e['type']=='helper']
    assert [(e['subagent_id'],e['event'],e.get('status')) for e in helpers]==[
        ('codex:child-1','start',None),('codex:child-1','complete','completed'),
        ('codex:child-2','start',None),('codex:child-2','complete','interrupted')]
    assert helpers[0]['goal']=='Codex agent root/frontend' and helpers[0]['model']=='gpt-test'
    assert helpers[2]['goal']=='Codex agent child-2'
    assert not any(e['type']=='tool' and e.get('name')=='subAgentActivity' for e in events)
    assert any(e['type']=='native_agent_usage' and e['thread_id']=='child-1' for e in events)
