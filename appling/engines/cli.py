"""Claude Code and Copilot CLI adapters, using their installed CLI contracts."""
from __future__ import annotations
import json
import os
import queue
import signal
import subprocess
import threading
import time
from . import environment, result_json


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
        args = [connection.get('binary','claude'), '--print', '--output-format','stream-json','--verbose',
                '--append-system-prompt',run.instructions, '--permission-mode','acceptEdits' if writable else 'plan']
        if writable:
            args += ['--allowedTools','Read,Glob,Grep,Edit,Write,Bash']
        if run.session:
            args += ['--resume',run.session]
        if run.effort:
            if run.effort=='off':
                raise ValueError('Claude Code does not offer an off effort setting. Choose its default or a supported effort.')
            args += ['--effort',run.effort]
        if run.model:
            args += ['--model',run.model]
        args += [run.prompt]
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
    proc = subprocess.Popen(args,cwd=run.root,env=environment(),stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True,bufsize=1,start_new_session=True)
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
    final='';text_parts=[];deadline=time.monotonic()+connection.get('timeout',1800)
    try:
        while True:
            if run.cancel.is_set():
                raise InterruptedError('Stopped. Existing files remain available.')
            if time.monotonic()>deadline:
                raise TimeoutError('CLI task timed out.')
            try:
                line=lines.get(timeout=.2)
            except queue.Empty:
                continue
            if line is None:
                break
            try:
                event=json.loads(line)
            except ValueError:
                text_parts.append(line);continue
            type_=event.get('type','');data=event.get('data',event)
            sid=event.get('session_id') or data.get('sessionId') or data.get('session_id')
            if sid:
                run.save_session(sid)
            if type_=='result':
                if event.get('is_error'):
                    raise RuntimeError(str(event.get('result','CLI task failed')))
                final=event.get('result','');run.save_usage(event.get('usage',{}))
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
        if proc.returncode:
            raise RuntimeError(f'{engine} failed: '+''.join(errors)[-1800:])
        return result_json(final or ''.join(text_parts))
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid,signal.SIGTERM)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGKILL);proc.wait()
        for stream in [proc.stdout,proc.stderr]:
            stream.close()
