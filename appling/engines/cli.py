"""Claude Code and Copilot CLI adapters, using their installed CLI contracts."""
from __future__ import annotations
import json
import queue
import subprocess
import threading
import time
from .. import children, procs
from . import environment, result_json
from .claude_support import CliError, claude_environment


def _reported_model(event):
    usage=event.get('modelUsage')
    if isinstance(usage,dict) and usage:return next(iter(usage))
    message=event.get('message')
    return event.get('model') or (message.get('model') if isinstance(message,dict) else None)


def _result_text(event):
    if event.get('is_error'):
        errors=event.get('errors',[])
        detail=event.get('result') or (errors if isinstance(errors,str) else '\n'.join(str(e) for e in errors)) or event.get('subtype') or 'CLI task failed'
        raise CliError(detail)
    structured=event.get('structured_output')
    return json.dumps(structured) if isinstance(structured,dict) else event.get('result','')


def execute(connection, run):
    engine = connection['engine']
    # Neither CLI exposes the Codex approval protocol. Require explicit consent
    # for a task with shell/edit capability; never bypass path verification.
    writable = not run.readonly
    if writable:
        answer = run.ask('approval', f'Allow {engine} to edit this project and run its build/test commands for this task? '
                         'This CLI uses its own permissions and is not an operating-system sandbox.', ['once','deny'])
        if answer != 'once':
            raise PermissionError('Task command access was declined.')
    if engine == 'claude-cli':
        args = [connection.get('binary','claude'), '--print', '--output-format','json' if run.connection_test else 'stream-json','--verbose',
                '--append-system-prompt',run.instructions, '--permission-mode','acceptEdits' if writable else 'plan']
        if writable:
            args += ['--allowedTools','Read,Glob,Grep,Edit,Write,Bash']
        if run.connection_test:
            args += ['--tools','','--no-session-persistence']
        if run.session:
            args += ['--resume',run.session]
        if run.effort:
            if run.effort=='off':
                raise ValueError('Claude Code does not offer an off effort setting. Choose its default or a supported effort.')
            args += ['--effort',run.effort]
        if run.model:
            args += ['--model',run.model]
        args += [run.prompt]
        if run.connection_test:
            # Match the simple headless invocation used by the existing CoB
            # connector. No project session, plan mode or task-specific prompt.
            args=[connection.get('binary','claude'),'--print',run.prompt,'--output-format','json',
                  '--tools','','--no-session-persistence']
            if run.model:args+=['--model',run.model]
    else:
        args = [connection.get('binary','copilot'), '-p',run.instructions+'\n\n'+run.prompt,
                '--output-format','json','--stream','on','--disable-builtin-mcps']
        if writable:
            args += ['--allow-tool','write','--allow-tool','shell']
        else:
            args += ['--deny-tool','write','--deny-tool','shell']
        if run.session:
            args += ['--resume',run.session]
        if run.model:
            args += ['--model',run.model]
        if run.effort:
            args += ['--reasoning-effort','none' if run.effort=='off' else run.effort]
    proc = procs.spawn(args,cwd=run.root,env=claude_environment() if engine=='claude-cli' else environment(),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',bufsize=1)
    children.track(proc)
    lines = queue.Queue(); errors=[]
    def read():
        for line in proc.stdout:
            lines.put(line)
        lines.put(None)
    def err():
        for line in proc.stderr:
            errors.append(line[-1000:]);del errors[:-8]
    threading.Thread(target=read,daemon=True).start()
    threading.Thread(target=err,daemon=True).start()
    final='';reported_model=None;text_parts=[]
    # A connection test keeps a total deadline. A real task has no total limit: only silence ends it,
    # so a long build that keeps reporting is never cut off.
    probe=bool(run.connection_test)
    limit=connection.get('timeout',1800) if probe else connection.get('idle_timeout',connection.get('timeout',1800))
    last_activity=time.monotonic()
    try:
        while True:
            if run.cancel.is_set():
                raise InterruptedError('Stopped. Existing files remain available.')
            if time.monotonic()-last_activity>limit:
                if probe:
                    raise TimeoutError(f'{engine} did not respond within {limit} seconds. Check the CLI directly for login, connectivity or startup-hook problems.')
                raise TimeoutError(f'{engine} reported no activity for {limit} seconds. Paused for inactivity; saved work can be resumed.')
            try:
                line=lines.get(timeout=.2)
            except queue.Empty:
                continue
            if not probe:last_activity=time.monotonic()
            if line is None:
                break
            try:
                event=json.loads(line)
            except ValueError:
                text_parts.append(line);continue
            if not isinstance(event,dict):continue
            type_=event.get('type','');data=event.get('data',event)
            if not isinstance(data,dict):data={}
            reported_model=_reported_model(event) or reported_model
            sid=event.get('session_id') or data.get('sessionId') or data.get('session_id')
            if sid:
                run.save_session(sid)
            if type_=='result':
                # Copilot's closing result event carries only usage; it must not erase the answer already received.
                final=_result_text(event) or final
                run.save_usage(event.get('usage',{}))
            elif type_=='assistant':
                for block in event.get('message',{}).get('content',[]):
                    if block.get('type')=='text':
                        final=block.get('text','')
                    elif block.get('type')=='tool_use':
                        run.emit('tool',phase='start',id=block.get('id',''),name=block.get('name','work'),args='')
            elif type_=='assistant.message':
                final=data.get('content','')
            elif type_.startswith('tool.'):
                run.emit('tool',phase='start',id=data.get('toolCallId',''),name=data.get('toolName','work'),args='')
        proc.wait(timeout=5)
        if not final and text_parts:
            try:envelope=json.loads(''.join(text_parts))
            except ValueError:envelope=None
            if isinstance(envelope,dict) and envelope.get('type')=='result':
                final=_result_text(envelope)
                reported_model=_reported_model(envelope) or reported_model
                run.save_usage(envelope.get('usage',{}))
        if proc.returncode:
            raise CliError(f'{engine} failed: '+(''.join(errors) or final or ''.join(text_parts) or f'exit code {proc.returncode}'))
        if run.connection_test:
            reply=final or ''.join(text_parts)
            if not reply.strip():raise CliError('The CLI exited without a model response.')
            return dict(summary=reply.strip(),_model=reported_model)
        result=result_json(final or ''.join(text_parts))
        if reported_model:result['_model']=reported_model
        return result
    finally:
        procs.stop(proc,3)   # an exit between check and signal is handled there and never hides the real CLI error
        children.forget(proc)
        for stream in [proc.stdout,proc.stderr]:
            stream.close()
