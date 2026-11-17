"""Direct, bidirectional Codex app-server transport, with resumable threads."""
from __future__ import annotations
import json
import queue
import subprocess
import threading
import time
from . import environment, result_json


def execute(connection, run):
    proc = subprocess.Popen([connection.get('binary','codex'), 'app-server', '--listen', 'stdio://'],
        cwd=run.root, env=environment(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, bufsize=1, start_new_session=True)
    incoming = queue.Queue()
    errors = []

    def reader():
        for line in proc.stdout:
            try:
                incoming.put(json.loads(line))
            except ValueError:
                continue
        incoming.put(None)

    def stderr():
        for line in proc.stderr:
            errors.append(line[-1000:])
            del errors[:-10]

    threading.Thread(target=reader, daemon=True).start()
    threading.Thread(target=stderr, daemon=True).start()
    seq = 0
    thread_id = None
    turn_id = None

    def send(data):
        proc.stdin.write(json.dumps(data) + '\n'); proc.stdin.flush()

    def receive(deadline):
        while time.monotonic() < deadline:
            if run.cancel.is_set():
                if thread_id and turn_id:
                    send(dict(id=999999, method='turn/interrupt', params=dict(threadId=thread_id, turnId=turn_id)))
                raise InterruptedError('Stopped. Project work and checkpoints are saved.')
            try:
                data = incoming.get(timeout=.2)
            except queue.Empty:
                continue
            if data is None:
                raise RuntimeError('Codex exited before completing the task. ' + ''.join(errors)[-1500:])
            if 'method' in data and 'id' in data:
                p = data.get('params', {}); method = data['method']
                if method.endswith('requestApproval'):
                    command = p.get('command') or p.get('reason') or 'Approve the proposed workspace operation?'
                    choice = run.ask('approval', str(command), ['once','deny'])
                    send(dict(id=data['id'], result=dict(decision='accept' if choice == 'once' else 'decline')))
                elif method.endswith('requestUserInput'):
                    answers = {}
                    for q in p.get('questions',[]):
                        answer = run.ask('question', q['question'], [o['label'] for o in q.get('options') or []])
                        answers[q['id']] = dict(answers=[str(answer)])
                    send(dict(id=data['id'], result=dict(answers=answers)))
                else:
                    send(dict(id=data['id'], error=dict(code=-32601, message='Unsupported client request; operation denied')))
                continue
            return data
        raise TimeoutError('Codex task timed out. Saved work can be resumed.')

    def rpc(method, params):
        nonlocal seq
        seq += 1; ident = seq
        send(dict(id=ident, method=method, params=params))
        deadline = time.monotonic() + 90
        while True:
            data = receive(deadline)
            if data.get('id') == ident:
                if 'error' in data:
                    raise RuntimeError(str(data['error'].get('message',data['error'])))
                return data.get('result',{})

    try:
        rpc('initialize', dict(clientInfo=dict(name='appling_c',version='0.1.0')))
        send(dict(method='initialized',params={}))
        params = dict(cwd=str(run.root), developerInstructions=run.instructions,
                      approvalPolicy='on-request', sandbox='read-only' if run.readonly else 'workspace-write')
        if run.model:
            params['model'] = run.model
        if connection.get('model_provider'):
            params['modelProvider'] = connection['model_provider']
        if run.session:
            result = rpc('thread/resume', dict(threadId=run.session, **params))
        else:
            result = rpc('thread/start', params)
        thread_id = result['thread']['id']; run.save_session(thread_id)
        turn = dict(threadId=thread_id, input=[dict(type='text',text=run.prompt)])
        if run.effort:
            turn['effort'] = 'none' if run.effort=='off' else run.effort
        result = rpc('turn/start', turn)
        turn_id = result['turn']['id']
        final = ''
        deadline = time.monotonic() + connection.get('timeout',1800)
        while True:
            data = receive(deadline)
            method = data.get('method',''); p = data.get('params',{})
            if p.get('threadId',thread_id) != thread_id:
                continue
            if method == 'thread/tokenUsage/updated':
                run.save_usage(p.get('tokenUsage',{}))
            elif method == 'thread/compacted':
                run.emit('interim',text='Saved project context is available after session compaction.')
            elif method == 'item/started':
                item = p.get('item',{})
                if item.get('type') != 'agentMessage':
                    run.emit('tool', phase='start', id=item.get('id',''), name=item.get('type','work'), args=item.get('command',''))
            elif method == 'item/completed':
                item = p.get('item',{})
                if item.get('type') == 'agentMessage':
                    final = item.get('text',final)
            elif method == 'turn/completed':
                finished = p.get('turn',{})
                if finished.get('status') != 'completed':
                    raise RuntimeError(str(finished.get('error') or finished.get('status')))
                return result_json(final)
            elif method == 'error' and not p.get('willRetry',False):
                raise RuntimeError(str(p.get('error',p)))
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill();proc.wait()
        for stream in [proc.stdin,proc.stdout,proc.stderr]:
            stream.close()
