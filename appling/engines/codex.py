"""Bidirectional Codex app-server sessions with independent worker activity.

Protocol fields are checked against the installed Codex 0.164 stable schema.
The host schedules isolated task threads; native child activity, if present, is
observable without confusing a child's response with the assigned task result.
"""
from __future__ import annotations
import json
import math
import os
import queue
import re
import signal
import subprocess
import threading
import time
from .. import __version__
from . import environment, result_json

_TASK_ACTIVITY = {
    'turn/started','turn/completed','turn/plan/updated','turn/diff/updated',
    'thread/tokenUsage/updated','thread/compacted','item/started','item/completed',
    'item/agentMessage/delta','item/plan/delta','item/commandExecution/outputDelta',
    'item/commandExecution/terminalInteraction','item/fileChange/outputDelta',
    'item/fileChange/patchUpdated','item/mcpToolCall/progress',
    'item/reasoning/summaryTextDelta','item/reasoning/summaryPartAdded',
    'item/reasoning/textDelta','item/autoApprovalReview/started',
    'item/autoApprovalReview/completed',
}


def _diagnostic(value):
    text = str(value)
    for name, secret in os.environ.items():
        if len(secret) > 5 and any(word in name.upper() for word in ('TOKEN', 'KEY', 'PASSWORD', 'SECRET')):
            text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'(?i)\bBearer\s+\S+', 'Bearer [REDACTED]', text)
    text = re.sub(r'\bsk-[A-Za-z0-9_-]+', '[REDACTED]', text)
    return text[-1800:]


class _IdleTimer:
    """Only silence consumes the budget; human decisions have no idle deadline."""
    def __init__(self, seconds, clock=None):
        self.seconds = float(seconds)
        if not math.isfinite(self.seconds) or self.seconds <= 0:
            raise ValueError('Codex inactivity timeout must be a positive number of seconds.')
        self.clock = clock or time.monotonic
        self.lock = threading.Lock()
        self.pending = set()
        self.last = self.clock()

    def activity(self):
        with self.lock:
            self.last = self.clock()

    def waiting(self, request):
        with self.lock:
            self.pending.add(request)

    def answered(self, request):
        with self.lock:
            self.pending.discard(request)
            self.last = self.clock()

    def expired(self):
        with self.lock:
            return not self.pending and self.clock() - self.last >= self.seconds


def execute(connection, run):
    # Legacy timeout values remain useful as inactivity budgets. There is no
    # total build duration limit; setup RPCs and connection probes stay bounded.
    idle = _IdleTimer(connection.get('idle_timeout',connection.get('timeout',1800)))
    proc = subprocess.Popen([connection.get('binary','codex'), 'app-server', '--listen', 'stdio://'],
        cwd=run.root, env=environment(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, bufsize=1, start_new_session=True)
    incoming = queue.Queue()
    errors = []
    closed = threading.Event()
    send_lock = threading.Lock()
    live_turns = {}
    known_threads = set()
    native_helpers = set()
    spawn_prompts = {}
    seen_requests = set()
    items = {}
    deltas = {}
    seq = 0
    thread_id = None
    turn_id = None

    def reader():
        for line in proc.stdout:
            try:
                incoming.put(json.loads(line))
            except ValueError:
                continue
        incoming.put(None)

    def stderr():
        for line in proc.stderr:
            errors.append(_diagnostic(line[-1000:]))
            del errors[:-10]

    threading.Thread(target=reader, daemon=True, name='codex-events').start()
    threading.Thread(target=stderr, daemon=True, name='codex-errors').start()

    def send(data):
        # Approval responses may arrive concurrently from different child agents.
        with send_lock:
            if closed.is_set():
                return
            proc.stdin.write(json.dumps(data) + '\n'); proc.stdin.flush()

    def approval_question(p):
        context = dict(thread=p.get('threadId',thread_id), cwd=p.get('cwd',str(run.root)))
        for key in ('command','reason','grantRoot','permissions','kind'):
            if p.get(key) is not None:
                context[key] = p[key]
        item = items.get(p.get('itemId'),{})
        if item.get('changes'):
            context['changes'] = item['changes']
        return 'Approve this Codex operation once?\n' + json.dumps(context,ensure_ascii=False)

    def respond(data):
        """Keep reading events while several workers wait for human answers."""
        p = data.get('params', {}); method = data['method']
        try:
            if method == 'item/permissions/requestApproval':
                answer = run.ask('approval',approval_question(p),['once','deny'])
                # A permissions callback has a different wire shape from shell
                # and file approvals. Never accidentally grant session access.
                result = dict(permissions=p.get('permissions',{}) if answer=='once' else {},scope='turn')
            elif method in {'item/commandExecution/requestApproval','item/fileChange/requestApproval'}:
                answer = run.ask('approval',approval_question(p),['once','deny'])
                result = dict(decision='accept' if answer=='once' else 'decline')
            elif method == 'item/tool/requestUserInput':
                answers = {}
                for q in p.get('questions',[]):
                    answer = run.ask('question',q['question'],[o['label'] for o in q.get('options') or []])
                    answers[q['id']] = dict(answers=[str(answer)])
                result = dict(answers=answers)
            else:
                send(dict(id=data['id'],error=dict(code=-32601,message='Unsupported client request; operation denied')))
                return
            if not run.cancel.is_set():
                send(dict(id=data['id'],result=result))
        except BaseException as exc:
            if not closed.is_set():
                incoming.put(('request_error',exc))
        finally:
            idle.answered(data['id'])

    def interrupt():
        nonlocal seq
        targets = dict(live_turns)
        if thread_id and turn_id:
            targets.setdefault(thread_id,turn_id)
        for tid, turn in targets.items():
            seq += 1
            try:
                send(dict(id=1000000+seq,method='turn/interrupt',params=dict(threadId=tid,turnId=turn)))
            except (BrokenPipeError,OSError):
                break

    def receive(deadline=None):
        while True:
            if run.cancel.is_set():
                interrupt()
                raise InterruptedError('Stopped. Project work and checkpoints are saved.')
            if deadline is not None and time.monotonic() >= deadline:
                interrupt()
                raise TimeoutError('Codex request timed out. Saved work can be resumed.')
            if deadline is None and idle.expired():
                interrupt()
                raise TimeoutError(f'Codex reported no task activity for {idle.seconds:g} seconds. '
                                   'Paused for inactivity; saved work can be resumed.')
            try:
                data = incoming.get(timeout=.1)
            except queue.Empty:
                continue
            if data is None:
                raise RuntimeError('Codex exited before completing the task. ' + ''.join(errors)[-1500:])
            if isinstance(data,tuple):
                raise data[1]
            if not isinstance(data,dict):
                continue
            if 'method' in data and 'id' in data:
                if data['id'] not in seen_requests:
                    seen_requests.add(data['id'])
                    idle.waiting(data['id'])
                    threading.Thread(target=respond,args=(data,),daemon=True,name='codex-user-request').start()
                continue
            return data

    def rpc(method, params):
        nonlocal seq
        seq += 1; ident = seq
        send(dict(id=ident, method=method, params=params))
        deadline = time.monotonic() + 90
        while True:
            data = receive(deadline)
            if data.get('id') == ident:
                if 'error' in data:
                    raise RuntimeError(_diagnostic(data['error'].get('message',data['error'])))
                return data.get('result',{})
            # Early tool/activity events are possible before turn/start returns.
            if 'method' in data:
                notification(data)

    final = ''

    def child_label(tid, path=None):
        # Only protocol-supplied facts: the spawn prompt when a collab call carried
        # one, otherwise the child's agent path, otherwise its thread id.
        return (spawn_prompts.get(tid) or (f'Codex agent {path}' if path else f'Codex agent {tid[:8]}'))[:500]

    def sub_agent_activity(item):
        """Newer Codex lifecycle items: started|interacted|interrupted|completed."""
        tid = item.get('agentThreadId')
        if not tid:
            return
        known_threads.add(tid)
        helper = 'codex:'+tid
        kind = item.get('kind')
        if kind in {'started','interacted'} and helper not in native_helpers:
            native_helpers.add(helper)
            run.emit('helper',event='start',subagent_id=helper,goal=child_label(tid,item.get('agentPath')),native=True,
                     agent_path=item.get('agentPath'),model=item.get('model'),reasoning_effort=item.get('reasoningEffort'))
        elif kind in {'completed','interrupted'} and helper in native_helpers:
            native_helpers.remove(helper)
            run.emit('helper',event='complete',subagent_id=helper,status='completed' if kind=='completed' else 'interrupted',native=True)
        run.emit('native_agent',tool='subAgentActivity',status=kind,agents={},threads=[tid],agent_path=item.get('agentPath'))

    def native_activity(item):
        for tid in item.get('receiverThreadIds',[]):
            known_threads.add(tid)
            if item.get('prompt') and tid not in spawn_prompts:
                spawn_prompts[tid] = item['prompt']
            status = item.get('agentsStates',{}).get(tid,{}).get('status','running')
            helper = 'codex:'+tid
            if status in {'pendingInit','running'}:
                if helper not in native_helpers:
                    native_helpers.add(helper)
                    run.emit('helper',event='start',subagent_id=helper,goal=child_label(tid),native=True)
            elif helper in native_helpers:
                native_helpers.remove(helper)
                run.emit('helper',event='complete',subagent_id=helper,status='completed' if status=='completed' else 'error',native=True)
        run.emit('native_agent',tool=item.get('tool'),status=item.get('status'),
                 agents=item.get('agentsStates',{}),threads=item.get('receiverThreadIds',[]))

    def notification(data):
        nonlocal final
        method = data.get('method',''); p = data.get('params',{})
        tid = p.get('threadId',thread_id)
        if method == 'turn/started':
            if p.get('turn',{}).get('id'):
                live_turns[tid] = p['turn']['id']
        if method == 'turn/completed':
            live_turns.pop(tid,None)
        if method in {'item/started','item/completed'}:
            item = p.get('item',{})
            if item.get('id'):
                items[item['id']] = item
            if item.get('type') == 'collabAgentToolCall':
                native_activity(item)
            elif item.get('type') == 'subAgentActivity':
                sub_agent_activity(item)
        if tid != thread_id and tid not in known_threads:
            return
        # Count task events, including silent reasoning and tool output, but
        # not unrelated threads, duplicate RPC replies or transport keepalives.
        if method in _TASK_ACTIVITY:
            idle.activity()
        if method == 'thread/tokenUsage/updated':
            if tid == thread_id:
                run.save_usage(p.get('tokenUsage',{}))
            else:
                run.emit('native_agent_usage',thread_id=tid,usage=p.get('tokenUsage',{}))
        elif method == 'thread/compacted':
            run.emit('context_checkpoint',thread_id=tid,text='Codex compacted its session; durable project handoff remains saved.')
        elif method == 'item/agentMessage/delta':
            key = (tid,p.get('itemId',''))
            deltas[key] = deltas.get(key,'') + p.get('delta','')
            # Final output is task JSON: expose native streaming without pouring
            # raw JSON or child responses into the user's conversation bubble.
            run.emit('worker_delta',thread_id=tid,item_id=p.get('itemId',''),text=p.get('delta',''))
        elif method == 'item/started':
            item = p.get('item',{})
            if item.get('type') not in {'agentMessage','collabAgentToolCall','subAgentActivity'}:
                run.emit('tool',phase='start',id=item.get('id',''),name=item.get('type','work'),args=item.get('command',''),thread_id=tid)
        elif method == 'item/completed':
            item = p.get('item',{})
            if item.get('type') == 'agentMessage':
                text = item.get('text') or deltas.get((tid,item.get('id','')),'')
                if tid == thread_id and item.get('phase') != 'commentary':
                    final = text or final
                elif item.get('phase') == 'commentary':
                    run.emit('worker_commentary',thread_id=tid,text=text)
            elif item.get('type') == 'commandExecution':
                run.emit('tool',phase='complete',id=item.get('id',''),name='commandExecution',
                         exit_code=item.get('exitCode'),thread_id=tid)
        elif method == 'error' and tid == thread_id and not p.get('willRetry',False):
            raise RuntimeError(_diagnostic(p.get('error',p)))

    try:
        rpc('initialize', dict(clientInfo=dict(name='appling_c',version=__version__)))
        send(dict(method='initialized',params={}))
        params = dict(cwd=str(run.root), developerInstructions=run.instructions,
                      approvalPolicy='on-request', sandbox='read-only' if run.readonly else 'workspace-write')
        if run.managed_worker:
            # Appling already owns the bounded swarm of isolated Codex threads.
            # Prevent native descendants from escaping its task/slot accounting.
            params['config'] = {'features.multi_agent':False,'features.multi_agent_v2':False}
        elif run.native_delegation:
            params['config'] = {'features.multi_agent':True,'features.multi_agent_v2':True}
        if run.model:
            params['model'] = run.model
        if connection.get('model_provider'):
            params['modelProvider'] = connection['model_provider']
        if run.session:
            result = rpc('thread/resume', dict(threadId=run.session, **params))
        else:
            result = rpc('thread/start', params)
        thread_id = result['thread']['id']; known_threads.add(thread_id); run.save_session(thread_id)
        run.emit('engine_configuration',model=result.get('model') or run.model or 'provider-default',
                 effort=result.get('reasoningEffort') or run.effort or 'provider-default',
                 model_source='resolved' if result.get('model') else 'requested')
        turn = dict(threadId=thread_id, input=[dict(type='text',text=run.prompt)])
        if run.effort:
            turn['effort'] = 'none' if run.effort=='off' else run.effort
        result = rpc('turn/start', turn)
        turn_id = result['turn']['id']; live_turns[thread_id] = turn_id
        idle.activity()
        deadline = time.monotonic() + connection.get('timeout',45) if run.connection_test else None
        while True:
            data = receive(deadline)
            notification(data)
            p = data.get('params',{})
            if data.get('method') == 'turn/completed' and p.get('threadId',thread_id) == thread_id:
                finished = p.get('turn',{})
                if finished.get('status') != 'completed':
                    raise RuntimeError(_diagnostic(finished.get('error') or finished.get('status')))
                return result_json(final)
    finally:
        closed.set()
        # app-server tools and descendants must not outlive a stopped task.
        # start_new_session makes this process group belong exclusively to it.
        try:
            os.killpg(proc.pid,signal.SIGTERM)
        except (ProcessLookupError,PermissionError):
            if proc.poll() is None:
                proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        # The server may exit before a tool child which ignores SIGTERM.
        # Clean up that process group even after its original leader exited.
        try:
            os.killpg(proc.pid,signal.SIGKILL)
        except (ProcessLookupError,PermissionError):
            if proc.poll() is None:
                proc.kill()
        proc.wait()
        for helper in native_helpers:
            run.emit('helper',event='complete',subagent_id=helper,status='interrupted',native=True)
        for stream in [proc.stdin,proc.stdout,proc.stderr]:
            stream.close()
