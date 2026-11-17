"""Small tool bridge for API models, with workspace bounds and explicit shell consent."""
from __future__ import annotations
import json
import os
import signal
import subprocess
import time
from .store import safe_path


def spec(name, description, properties, required):
    return dict(type='function',function=dict(name=name,description=description,
        parameters=dict(type='object',properties=properties,required=required,additionalProperties=False)))


TOOLS = [
    spec('read_skill','Read a complete bundled specialist skill by name, including its full instructions.',
         dict(name=dict(type='string'),resource=dict(type='string',description='Optional relative reference path inside that skill.')),['name']),
    spec('read_file','Read a project file. Large files can be read in bounded line ranges.',
         dict(path=dict(type='string'),start=dict(type='integer'),lines=dict(type='integer')),['path']),
    spec('write_file','Write a complete project file. Parent directories are created.',
         dict(path=dict(type='string'),content=dict(type='string')),['path','content']),
    spec('list_files','List project source files, excluding dependencies and Git metadata.',{},[]),
    spec('project_recall','Find earlier user answers, decisions and project evidence.',dict(query=dict(type='string')),['query']),
    spec('run_command','Run a project command after the owner approves it. Use for builds, tests and browser automation.',
         dict(command=dict(type='string')),['command']),
]


def execute(run,name,args):
    if name=='read_skill':
        from .context import ROOT
        skill=args['name'].split(':')[-1]
        if not skill or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in skill):
            raise ValueError('Use a bundled skill name.')
        path=safe_path(ROOT/'skills'/skill,args.get('resource','SKILL.md'))
        return path.read_text()
    if name=='project_recall':
        return json.dumps(run.recall(args['query']))
    if name=='list_files':
        skip={'.git','.appling','node_modules','.venv','dist','build','__pycache__'}
        paths=[]
        for base,dirs,files in os.walk(run.root):
            dirs[:]=[d for d in dirs if d not in skip]
            for file in files:
                p=os.path.relpath(os.path.join(base,file),run.root)
                if not file.startswith('.env'):
                    paths.append(p)
            if len(paths)>3000:
                break
        return '\n'.join(paths[:3000])
    if name in {'read_file','write_file'}:
        p=safe_path(run.root,args['path'])
        parts=p.relative_to(run.root).parts
        if '.appling' in parts or p.name.startswith('.env'):
            raise PermissionError('Private state and credentials are not model-readable files.')
        if name=='read_file':
            lines=p.read_text(errors='replace').splitlines()
            start=max(0,int(args.get('start',1))-1)
            return '\n'.join(lines[start:start+min(400,int(args.get('lines',200)))])[:16000]
        if run.readonly:
            raise PermissionError('This task cannot edit project source.')
        p.parent.mkdir(parents=True,exist_ok=True);p.write_text(args['content'])
        return 'File saved.'
    if name=='run_command':
        command=args['command']
        if run.ask('approval',f'Run this command in {run.root}?\n\n{command}\n\nCommands run with your local account permissions.', ['once','deny'])!='once':
            return 'Command denied by the owner.'
        from .engines import environment
        proc=subprocess.Popen(command,shell=True,cwd=run.root,env=environment(),stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT,text=True,start_new_session=True)
        deadline=time.monotonic()+120
        try:
            while True:
                try:
                    output,_=proc.communicate(timeout=.2)
                    return json.dumps(dict(exit_code=proc.returncode,output=output[-12000:]))
                except subprocess.TimeoutExpired:
                    if run.cancel.is_set():
                        raise InterruptedError('Command stopped.')
                    if time.monotonic()>deadline:
                        raise TimeoutError('Command exceeded 120 seconds. Use a smaller check.')
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid,signal.SIGTERM)
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid,signal.SIGKILL);proc.wait()
    raise ValueError('Unknown tool: '+name)
