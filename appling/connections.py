"""Model discovery and explicit, project-free connection tests."""
from __future__ import annotations
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
import httpx
from .engines import Run, environment, execute
from .engines.claude_support import MODEL_IDS, CliError, claude_environment


class DiscoveryError(Exception):
    pass


class RpcProcess:
    """Bounded metadata-only RPC conversations with installed CLI servers."""
    def __init__(self,args,cwd):
        self.proc=subprocess.Popen(args,cwd=cwd,env=environment(),stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
        self.incoming=queue.Queue();self.seq=0;self.permission_error=False
        def read():
            for line in self.proc.stdout:
                try:self.incoming.put(json.loads(line))
                except ValueError:continue
            self.incoming.put(None)
        def drain():
            for line in self.proc.stderr:
                if any(word in line.lower() for word in ['operation not permitted','permission denied','read-only file system']):
                    self.permission_error=True
        self.reader=threading.Thread(target=read,daemon=True);self.reader.start()
        self.stderr=threading.Thread(target=drain,daemon=True);self.stderr.start()

    def send(self,message):
        self.proc.stdin.write(json.dumps(message)+'\n');self.proc.stdin.flush()

    def call(self,method,params):
        self.seq+=1;ident=self.seq
        self.send(dict(jsonrpc='2.0',id=ident,method=method,params=params))
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            try:message=self.incoming.get(timeout=.2)
            except queue.Empty:continue
            if message is None:
                self.stderr.join(timeout=.1)
                if self.permission_error:
                    raise DiscoveryError('The CLI could not access its state directory. Check permissions for its home/config directory.')
                raise DiscoveryError('The CLI exited during discovery. Check its login and version.')
            if 'method' in message and 'id' in message:
                self.send(dict(jsonrpc='2.0',id=message['id'],error=dict(code=-32601,message='Metadata discovery cannot grant permissions or execute tools.')))
                continue
            if message.get('id')!=ident:continue
            if 'error' in message:
                # CLI error bodies can contain account information or reflected input.
                code=message['error'].get('code')
                raise DiscoveryError(f'The CLI rejected {method} (code {code}). Check CLI login and protocol support.')
            return message.get('result',{})
        raise DiscoveryError('CLI discovery timed out. Check login, network access and the CLI version.')

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait()
        self.reader.join(timeout=1);self.stderr.join(timeout=1)
        for stream in [self.proc.stdin,self.proc.stdout,self.proc.stderr]:stream.close()


def base_url(connection):
    default={'ollama':'http://127.0.0.1:11434/v1','anthropic':'https://api.anthropic.com/v1'}
    base=connection.get('base_url') or default.get(connection['engine'],'https://api.openai.com/v1')
    base=base.rstrip('/')
    if connection['engine']=='ollama' and not base.endswith('/v1'):
        base+='/v1'
    return base


def headers(connection, *, require_key=False):
    engine=connection['engine']
    if engine=='ollama' and not connection.get('api_key_env'):return {}
    key_name=connection.get('api_key_env') or ('ANTHROPIC_API_KEY' if engine=='anthropic' else 'OPENAI_API_KEY')
    key=os.environ.get(key_name,'')
    if require_key and engine!='ollama' and not key:
        raise DiscoveryError(f'{key_name} is not set in the server environment. Set it before starting Appling.')
    if engine=='anthropic':
        return {'x-api-key':key,'anthropic-version':'2023-06-01'}
    return {'Authorization':'Bearer '+key} if key else {}


def http_error(status):
    if status in {401,403}:
        return 'Authentication was rejected. Check the credential, account access and selected provider.'
    if status==404:
        return 'This endpoint does not provide a model catalogue. Check the base URL or enter a model ID manually.'
    if status==429:
        return 'The provider is rate-limiting requests or has no remaining quota.'
    return f'The provider returned HTTP {status}. Check the endpoint and model access.'


def discover(connection):
    engine=connection['engine'];configured=connection.get('models',[])
    names=[];default_model=None;source='provider';state='ready';message='Models loaded from the provider.'
    try:
        if engine=='codex':
            binary=connection.get('binary','codex')
            if not shutil.which(binary):raise DiscoveryError('Codex CLI is not installed or is missing from PATH. Install it, then run codex login.')
            with tempfile.TemporaryDirectory(prefix='appling-models-') as cwd:
                rpc=RpcProcess([binary,'app-server','--listen','stdio://'],cwd)
                try:
                    rpc.call('initialize',dict(clientInfo=dict(name='appling_c',version='0.1.0')))
                    rpc.send(dict(jsonrpc='2.0',method='initialized',params={}))
                    account=rpc.call('account/read',dict(refreshToken=False))
                    cursor=None
                    for page in range(20):
                        result=rpc.call('model/list',dict(limit=100,includeHidden=False,cursor=cursor))
                        for model in result.get('data',[]):
                            if model.get('hidden'):continue
                            name=model.get('model') or model.get('id')
                            if name:names.append(name)
                            if model.get('isDefault'):default_model=name
                        cursor=result.get('nextCursor')
                        if not cursor:break
                    if not account.get('account') and account.get('requiresOpenaiAuth',True):
                        state='login_required';message='Codex models loaded, but no active login was reported. Run codex login, then test the connection.'
                    else:message='Codex account and model catalogue loaded. Test the selected model to confirm generation.'
                finally:rpc.close()
        elif engine=='copilot':
            binary=connection.get('binary','copilot')
            if not shutil.which(binary):raise DiscoveryError('Copilot CLI is not installed or is missing from PATH. Install it, then run copilot login.')
            with tempfile.TemporaryDirectory(prefix='appling-models-') as cwd:
                rpc=RpcProcess([binary,'--acp','--disable-builtin-mcps'],cwd)
                try:
                    rpc.call('initialize',dict(protocolVersion=1,clientCapabilities={},clientInfo=dict(name='appling_c',version='0.1.0')))
                    result=rpc.call('session/new',dict(cwd=cwd,mcpServers=[]))
                    models=result.get('models') or {}
                    names=[m['modelId'] for m in models.get('availableModels',[]) if m.get('modelId')]
                    default_model=models.get('currentModelId')
                    message='Copilot session and available models loaded. Test the selected model to confirm generation.'
                finally:rpc.close()
        elif engine=='claude-cli':
            binary=connection.get('binary','claude')
            if not shutil.which(binary):raise DiscoveryError('Claude Code CLI is not installed or is missing from PATH. Install it, then run claude auth login.')
            result=subprocess.run([binary,'auth','status','--json'],env=claude_environment(),stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=12)
            try:auth=json.loads(result.stdout)
            except ValueError:raise DiscoveryError('Could not read Claude Code login status. Run claude auth status and check its version.')
            names=[*MODEL_IDS,'default','sonnet','opus','haiku','fable'];source='documented_models'
            if not auth.get('loggedIn',False):
                state='login_required';message='Claude Code is not signed in. Run claude auth login, then test the connection.'
            else:
                message='Claude Code is signed in. Versioned IDs and aliases are shown; availability depends on your account. Test a model to verify access.'
        elif engine in {'ollama','openai-compatible','anthropic'}:
            auth=headers(connection,require_key=engine=='anthropic' or bool(connection.get('api_key_env')) and engine!='ollama')
            names=[];cursor=None
            with httpx.Client(timeout=6) as client:
                for page in range(20):
                    response=client.get(base_url(connection)+'/models',headers=auth,
                        params={'after_id':cursor,'limit':1000} if engine=='anthropic' else None)
                    if response.status_code>=400:raise DiscoveryError(http_error(response.status_code))
                    result=response.json();names.extend(m['id'] for m in result.get('data',[]) if m.get('id'))
                    if engine!='anthropic' or not result.get('has_more'):break
                    cursor=result.get('last_id')
                    if not cursor:break
            if not names:
                state='empty';message='Connected, but no models were returned. For Ollama, pull a model first; otherwise enter a model ID supported by this endpoint.'
        else:raise DiscoveryError('Unsupported engine.')
    except (DiscoveryError,httpx.HTTPError,subprocess.TimeoutExpired,OSError,ValueError,KeyError) as exc:
        state='error'
        if isinstance(exc,DiscoveryError):message=str(exc)
        elif isinstance(exc,(httpx.ConnectError,httpx.TimeoutException)):
            message='Could not reach the provider. Check the server address, network access and whether Ollama is running.'
        elif isinstance(exc,subprocess.TimeoutExpired):message='CLI login check timed out. Check its login and version.'
        else:message='Could not discover models. Check the provider endpoint, CLI installation and login.'
        login={'codex':'codex login','copilot':'copilot login','claude-cli':'claude auth login'}.get(engine)
        if login and login not in message:message+=f' To sign in, run {login}.'
    return dict(models=list(dict.fromkeys([*names,*configured])),default_model=default_model,
                state=state,message=message,source=source,checked_at=time.time())


def test_connection(connection,model=''):
    """An explicit user action: make one small inference without project context."""
    engine=connection['engine'];model='' if model=='default' else model
    started=time.monotonic()
    try:
        if engine in {'ollama','openai-compatible','anthropic'}:
            if not model:raise DiscoveryError('Choose a model before testing this API connection.')
            auth=headers(connection,require_key=engine!='ollama')
            body=dict(model=model,messages=[dict(role='user',content='Reply with exactly OK. Do not use tools.')])
            if engine=='anthropic':body['max_tokens']=32
            with httpx.Client(timeout=45) as client:
                response=client.post(base_url(connection)+('/messages' if engine=='anthropic' else '/chat/completions'),headers=auth,json=body)
            if response.status_code>=400:raise DiscoveryError(http_error(response.status_code))
            data=response.json()
            text=''.join(b.get('text','') for b in data.get('content',[]) if b.get('type')=='text') if engine=='anthropic' else data['choices'][0]['message'].get('content','')
            resolved=data.get('model') or model
            if not text:raise DiscoveryError('The provider accepted the request but returned no text. Check the model capability.')
        else:
            with tempfile.TemporaryDirectory(prefix='appling-test-') as cwd:
                run=Run(root=Path(cwd),readonly=True,connection_test=True,model='' if model=='default' else model,
                    instructions='Connection check only. Do not use tools or inspect any files. Return exactly {"summary":"OK"}.',
                    prompt='Return exactly {"summary":"OK"}.')
                result=execute({**connection,'timeout':45},run)
                if not result.get('summary'):raise DiscoveryError('The CLI completed without a valid test response.')
            resolved=result.get('_model') or model or 'CLI default'
        return dict(ok=True,state='connected',model=resolved,message='The selected model responded successfully.',latency_ms=round((time.monotonic()-started)*1000))
    except Exception as exc:
        if isinstance(exc,(DiscoveryError,CliError)):message=str(exc)
        elif isinstance(exc,TimeoutError) and engine=='claude-cli':message=str(exc)
        elif isinstance(exc,(httpx.ConnectError,httpx.TimeoutException,TimeoutError)):message='The model request could not connect or timed out. Check the endpoint and provider status.'
        elif isinstance(exc,FileNotFoundError):message='The CLI executable was not found. Check its installation and PATH.'
        else:message='The model test failed. Check the CLI login, selected model, provider quota and endpoint configuration.'
        return dict(ok=False,state='error',model=model,message=message,latency_ms=round((time.monotonic()-started)*1000))
