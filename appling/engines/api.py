"""Ollama, OpenAI-compatible and Anthropic APIs with a bounded tool loop."""
from __future__ import annotations
import json
import os
import uuid
import httpx
from .. import tools
from ..connections import base_url, headers as connection_headers
from . import result_json


def execute(connection,run):
    engine=connection['engine']
    base=base_url(connection)
    anthropic=engine=='anthropic'
    if run.effort and engine in {'anthropic','ollama'}:
        raise ValueError('This API adapter does not yet map effort settings for this provider. Choose default effort for this connection.')
    headers=connection_headers(connection)
    private=run.root/'.appling'/'sessions';private.mkdir(parents=True,exist_ok=True)
    # Session IDs never become arbitrary paths.
    sid=run.session if run.session and all(c in '0123456789abcdef-' for c in run.session) else str(uuid.uuid4())
    path=private/(sid+'.json')
    messages=json.loads(path.read_text()) if path.exists() else []
    if messages and (messages[-1].get('role')!='assistant' or messages[-1].get('tool_calls') or
                     anthropic and any(b.get('type')=='tool_use' for b in messages[-1].get('content',[]) if isinstance(b,dict))):
        # An interrupted HTTP/tool exchange is not a valid prefix to replay.
        # Keep it on disk and resume in a new session with a brief handoff.
        run.prompt+='\nRecovery: the previous request was interrupted. Inspect existing files before repeating work. Recent saved conversation:\n'+json.dumps(messages[-4:])[-10000:]
        sid=str(uuid.uuid4());path=private/(sid+'.json');messages=[]
    if not messages and not anthropic:
        messages.append(dict(role='system',content=run.instructions))
    messages.append(dict(role='user',content=run.prompt))
    run.save_session(sid)
    usage=dict(input_tokens=0,output_tokens=0,cached_input_tokens=0)
    def save():
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(messages));tmp.replace(path)
        path.chmod(0o600)
    save()
    def recover_context(reason):
        nonlocal messages,sid,path
        # Compression is an explicit session boundary. Preserve the complete
        # old transcript on disk and build a bounded handoff rather than edit
        # any prefix of a live cached conversation.
        journal=[]
        for message in messages[-18:]:
            if message.get('tool_calls'):
                journal.append(dict(action=message['tool_calls']))
            elif message.get('role')=='tool':
                journal.append(dict(result=str(message.get('content',''))[-1200:]))
            elif anthropic and message.get('role')=='user' and isinstance(message.get('content'),list):
                journal.append(dict(results=message['content']))
        handoff='Context recovery: '+reason+'\nOriginal current task briefing:\n'+run.prompt+'\nRecent actions (verify files before repeating):\n'+json.dumps(journal)[-14000:]
        sid=str(uuid.uuid4());path=private/(sid+'.json')
        messages=[] if anthropic else [dict(role='system',content=run.instructions)]
        messages.append(dict(role='user',content=handoff));run.save_session(sid);save()
        run.emit('interim',text='Resuming from the saved task briefing and recent actions after context recovery.')
    with httpx.Client(timeout=httpx.Timeout(120,connect=10)) as client:
        for iteration in range(connection.get('max_iterations',60)):
            if run.cancel.is_set():
                raise InterruptedError('Stopped. The task can be resumed.')
            if len(json.dumps(messages))>connection.get('context_chars',240000):
                recover_context('The previous session reached its configured context budget.')
                if len(json.dumps(messages))>connection.get('context_chars',240000):
                    raise RuntimeError('The task briefing itself exceeds this connection’s context budget. Raise its budget or split the task.')
            if anthropic:
                body=dict(model=run.model,max_tokens=8192,system=run.instructions,messages=messages,
                          tools=[dict(name=t['function']['name'],description=t['function']['description'],input_schema=t['function']['parameters']) for t in tools.TOOLS])
                response=client.post(base+'/messages',headers=headers,json=body)
            else:
                body=dict(model=run.model,messages=messages,tools=tools.TOOLS)
                if run.effort:
                    body['reasoning_effort']='none' if run.effort=='off' else run.effort
                response=client.post(base+'/chat/completions',headers=headers,json=body)
            if response.status_code>=400:
                # Provider bodies can reflect credentials. Keep raw error bodies out of durable logs.
                raise RuntimeError(f'{engine} returned HTTP {response.status_code}. Check the selected model, endpoint and credentials.')
            data=response.json();u=data.get('usage',{})
            usage['input_tokens']+=u.get('prompt_tokens',u.get('input_tokens',0))+(u.get('cache_read_input_tokens',0)+u.get('cache_creation_input_tokens',0) if anthropic else 0)
            usage['output_tokens']+=u.get('completion_tokens',u.get('output_tokens',0))
            usage['cached_input_tokens']+=u.get('prompt_tokens_details',{}).get('cached_tokens',u.get('cache_read_input_tokens',0))
            run.save_usage(usage)
            if anthropic:
                content=data['content'];messages.append(dict(role='assistant',content=content))
                calls=[b for b in content if b['type']=='tool_use']
                final=''.join(b.get('text','') for b in content if b['type']=='text')
            else:
                message=data['choices'][0]['message'];messages.append(message)
                calls=[dict(id=c['id'],name=c['function']['name'],input=json.loads(c['function']['arguments'])) for c in message.get('tool_calls') or []]
                final=message.get('content') or ''
            if not calls:
                save()
                return result_json(final)
            results=[]
            for call in calls:
                run.emit('tool',phase='start',id=call['id'],name=call['name'],args=json.dumps(call['input'])[:200])
                try:
                    output=tools.execute(run,call['name'],call['input'])
                except (ValueError,OSError,KeyError) as exc:
                    output=f'{type(exc).__name__}: {exc}'
                if anthropic:
                    results.append(dict(type='tool_result',tool_use_id=call['id'],content=output))
                else:
                    messages.append(dict(role='tool',tool_call_id=call['id'],content=output))
            if anthropic:
                messages.append(dict(role='user',content=results))
            save()
    raise RuntimeError('Task reached its tool-call budget. Work is saved; continue with a narrower task.')
