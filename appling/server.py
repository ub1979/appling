"""Local studio HTTP API, retaining the existing React interface contract."""
from __future__ import annotations
import asyncio
import json
import os
import re
import secrets
import shutil
import subprocess
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from .context import CATALOG, ROOT
from .engines import available
from .preview import Previews
from .store import Store, safe_path
from . import DISPLAY_VERSION
from .workflow import Workflow, ARTIFACTS, artifact_revision
from . import connections
from .messaging import PhoneConnections


def create_app(home=None,execute=None):
    home=Path(home or ROOT/'.appling_c');home.mkdir(parents=True,exist_ok=True,mode=0o700)
    store=Store(home/'studio.db')
    workflow=Workflow(store,**({'execute':execute} if execute else {}));previews=Previews()
    token=secrets.token_urlsafe(32)
    default_root=home/'projects';default_root.mkdir(exist_ok=True)
    model_cache={}
    phone=PhoneConnections(store,workflow,home)

    @asynccontextmanager
    async def lifespan(app):
        phone.start()
        try:
            yield
        finally:
            await asyncio.to_thread(phone.close)
            await asyncio.to_thread(workflow.shutdown);await asyncio.to_thread(previews.close)

    app=FastAPI(title='Appling C',lifespan=lifespan)
    app.state.store=store;app.state.workflow=workflow;app.state.token=token;app.state.phone=phone

    @app.exception_handler(ValueError)
    async def bad_request(request,exc):
        return JSONResponse({'detail':str(exc)},400)

    @app.exception_handler(KeyError)
    async def missing(request,exc):
        return JSONResponse({'detail':'Project or requested item was not found.'},404)

    @app.middleware('http')
    async def authenticate(request,call_next):
        host=request.url.hostname
        if host not in {'127.0.0.1','localhost','::1'}:
            return JSONResponse({'detail':'Open Appling at localhost.'},403)
        origin=request.headers.get('origin')
        if origin and origin!=str(request.base_url).rstrip('/'):
            return JSONResponse({'detail':'Requests from another origin are not allowed.'},403)
        if request.url.path.startswith('/api/'):
            given=request.headers.get('x-lyra-token') or request.query_params.get('token','')
            if not given or not secrets.compare_digest(given,token):
                return JSONResponse({'detail':'Open the Appling page again to reconnect.'},401)
        response=await call_next(request)
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["Referrer-Policy"]="no-referrer"
        return response
    def settings_payload():
        s=workflow.settings();selection=dict(provider=s['provider'],model=s['model'],effort=s.get('effort',''))
        return dict(engine=s['provider'],hermes=selection,hermes_effort=dict(effort=s.get('effort',''),effective=s.get('effort',''),overridden=False),
            about_me=s.get('about_me',''),connections=s['connections'],installed=available(),
            parallel_work=dict(max_workers=s.get('parallel_work',{}).get('max_workers',3),maximum=8,default=3,active=len(workflow.active),
                agents_per_project=s.get('parallel_work',{}).get('agents_per_project',3),agents_maximum=6),
            agent_models=[dict(id=a[0],label=a[1],default=selection,selection=s.get('agent_models',{}).get(a[0])) for a in CATALOG['AGENTS']])

    def detail(pid):
        p=store.get(pid);items=store.inbox(pid)
        helpers=[dict(id=role,role=role,goal=role,started=None) for role in [
            {'requirements':'req-engineer','prototype':'ui-designer','plan':'task-planner','build':'sw-developer','qa':'qa-engineer','security':'security-auditor','code-review':'code-reviewer','accessibility':'a11y-auditor'}.get(p['phase'],'app-it')]
            if p['running']]
        working=[dict(id=w['id'],role=w['role'],goal=w['goal'],started=None) for w in p.get('workers',[])
                 if w['status'] in {'running','completed','integrating'}]
        if p['running'] and working:helpers=working
        if p['running']:helpers.extend(p.get('native_helpers',{}).values())
        return dict(p,inbox=items,messages=store.messages(pid),helpers=helpers,task_workers=p.get('workers',[]),
            engine_override=False,engine_locked=False,keep_going=False,models={},rules_outdated=False,
            active_update=p.get('active_update'),update_available=p['phase']=='delivered',next_revision=p['revision']+1,
            review_pending=any(i['kind'] in ARTIFACTS for i in items),watchdog={},
            turn=p.get('turn'),turn_start_offset=store.event_cursor(pid),started_at=workflow.started)

    @app.get('/api/projects')
    def projects():
        return dict(projects=[dict(p,inbox=len(store.inbox(p['id']))) for p in store.projects()],default_root=str(default_root),version='C '+DISPLAY_VERSION)

    @app.get('/api/catalog')
    def catalog():
        return dict(agents=[dict(id=a[0],label=a[1],description=a[2],required=a[0] in CATALOG['REQUIRED']) for a in CATALOG['AGENTS']],
                    styles=CATALOG['STYLES'],default_root=str(default_root))

    @app.post('/api/projects')
    async def add_project(request:Request):
        data=await request.json();root=Path(data['path']).expanduser().resolve()
        if ROOT.is_relative_to(root) or root.is_relative_to(ROOT) and not root.is_relative_to(default_root):
            raise ValueError('Choose a project folder outside the Appling application source.')
        if data.get('create') and root.exists() and any(root.iterdir()):
            raise ValueError('A new project needs an empty folder. Use Open project for existing work.')
        if not data.get('create') and not root.is_dir():
            raise ValueError('The selected project folder does not exist.')
        for p in store.projects():
            if p['root']==str(root):
                return detail(p['id'])
        team=list(dict.fromkeys([*CATALOG['REQUIRED'],*data.get('team',[])]))
        execution_mode=data.get('execution_mode') or 'blocks'
        if execution_mode not in {'direct','planned','blocks'}:raise ValueError('Choose blocks, direct or planned execution.')
        p=store.add(root,team=team,style=data.get('style','app-it'),profile=data.get('profile','personal'),
                    kind=data.get('kind','app'),platforms=data.get('platforms') or ['web'],engine=workflow.settings()['provider'],execution_mode=execution_mode,
                    decide_for_me=bool(data.get('decide_for_me',True)))
        if not (root/'.git').exists():
            subprocess.run(['git','init','-b','main',str(root)],capture_output=True,check=True)
        ignore=root/'.gitignore'
        if not ignore.exists():
            ignore.write_text('.env\n.env.*\n!.env.example\nnode_modules/\ndist/\n.appling/\n')
        if data.get('template'):
            template=safe_path(home/'templates' if data['template'].startswith('own-') else ROOT/'templates',data['template'])
            if (template/'spec.md').is_file():
                kit=root/'.sdlc'/'template';kit.mkdir(parents=True,exist_ok=True)
                shutil.copy2(template/'spec.md',kit/'spec.md')
                if (template/'demo').is_dir():
                    shutil.copytree(template/'demo',kit/'reference',dirs_exist_ok=True)
        brief=data.get('brief','').strip()
        if brief:
            workflow.submit(p['id'],brief)
        else:
            store.ask(p['id'],'question',f'What would you like to build or change in {root.name}?',[])
        return detail(p['id'])

    @app.get('/api/projects/{pid}')
    def project(pid:str):
        return detail(pid)

    @app.delete('/api/projects/{pid}')
    def archive(pid:str):
        if pid in workflow.active:
            raise ValueError('Stop the project and wait for its current task to finish before archiving.')
        p=store.get(pid);root=Path(p['root']);archive_root=home/'Archive';archive_root.mkdir(exist_ok=True)
        target=archive_root/(root.name+'-'+pid)
        shutil.move(str(root),target)
        with store.connect() as c:
            c.execute('DELETE FROM projects WHERE id=?',(pid,))
        return dict(archived_to=str(target))

    @app.post('/api/projects/{pid}/messages')
    async def message(pid:str,request:Request):
        return workflow.submit(pid,str((await request.json()).get('text','')))

    @app.post('/api/projects/{pid}/inbox/{iid}')
    async def answer(pid:str,iid:str,request:Request):
        return workflow.answer(pid,iid,(await request.json())['answer'])

    @app.get('/api/projects/{pid}/acceptance')
    def acceptance_status(pid:str):
        return workflow.acceptance_status(pid)

    @app.post('/api/projects/{pid}/prerequisites/{ident}')
    async def prerequisite(pid:str,ident:str,request:Request):
        body=await request.json() if (await request.body()) else {}
        return workflow.set_prerequisite(pid,ident,bool(body.get('done',True)))

    @app.get('/api/projects/{pid}/blocks')
    def project_blocks(pid:str):
        from . import blocks as block_plan
        p=store.get(pid);root=Path(p['root'])
        plan=block_plan.load(root)
        if not plan:return dict(exists=False,blocks=[],phase=p['phase'])
        from .acceptance import load as load_spec
        later=block_plan.deferred(plan,load_spec(root))
        status=p.get('block_status') or {}
        workers={w['id']:w for w in p.get('workers',[])}
        helpers=list((p.get('native_helpers') or {}).values()) if p.get('running') else []
        rows=[]
        for b in plan['blocks']:
            info=status.get(b['id'],{})
            state='later' if b['id'] in later else info.get('status') or 'planned'
            worker=workers.get(info.get('worker')) if state=='building' else None
            rows.append(dict(id=b['id'],name=b['name'],purpose=b['purpose'],status=state,label=block_plan.STATUS_LABELS.get(state,state),
                reason=info.get('reason'),library=info.get('library') or (b['source'][8:] if b['source'].startswith('library:') else None),
                depends_on=b['depends_on'],runtime=b['runtime'],agent=bool(worker and worker.get('status')=='running')))
        return dict(exists=True,phase=p['phase'],blocks=rows,body=plan['body']['purpose'],helpers=helpers,
                    approved=bool(p['approvals'].get('blocks')))

    @app.get('/api/library')
    def library():
        from . import blocks as block_plan
        return dict(home=str(block_plan.library_home()),blocks=block_plan.catalogue())

    @app.post('/api/projects/{pid}/stop')
    def stop(pid:str):
        workflow.stop(pid);return dict(ok=True)

    @app.get('/api/projects/{pid}/stream')
    async def stream(pid:str,request:Request,offset:int=0):
        store.get(pid)
        try:
            offset=max(offset,int(request.headers.get('last-event-id','0')))
        except ValueError:
            offset=0
        async def events():
            cursor=offset
            while not await request.is_disconnected():
                for event in store.events(pid,cursor):
                    cursor=event['seq']
                    yield f'id: {cursor}\ndata: {json.dumps(event)}\n\n'
                yield ': keepalive\n\n'
                await asyncio.sleep(.3)
        return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-cache'})

    @app.get('/api/projects/{pid}/map')
    def project_map(pid:str):
        p=store.get(pid);phase=p['phase'];labels=dict((a[0],a[1]) for a in CATALOG['AGENTS'])
        phases=[]
        mode=p.get('execution_mode','planned')
        names=(['requirements','prototype','blocks','blocks_build','body','qa'] if mode=='blocks' else
               ['requirements','prototype',*(['plan'] if mode=='planned' else []),'build','qa'])
        names += [name for name,role in [('code-review','code-reviewer'),('security','security-auditor'),('accessibility','a11y-auditor')] if role in p['team']]
        stage={'criteria':'requirements','rescope':'requirements','requirements_update':'requirements','implementation_verified':'qa','blocks_plan':'blocks'}.get(phase,phase.replace('_review',''))
        position=names.index(stage) if stage in names else len(names)
        role_map={'requirements':'req-engineer','prototype':'ui-designer','plan':'task-planner','build':'sw-developer','qa':'qa-engineer','security':'security-auditor','code-review':'code-reviewer','accessibility':'a11y-auditor'}
        stage_labels={'blocks':'Block plan','blocks_build':'Building blocks','body':'Merging into the app'}
        for index,name in enumerate(names):
            if name=='security' and 'security-auditor' not in p['team']:
                continue
            status='done' if index<position or phase=='delivered' else ('owner' if '_review' in phase or phase=='implementation_verified' else 'blocked' if p['paused'] else 'running') if index==position else 'pending'
            role={'blocks':'sw-architect','blocks_build':'sw-developer','body':'sw-developer'}.get(name) or role_map[name]
            phases.append(dict(name=stage_labels.get(name) or labels[role_map[name]],state=status,status=status,note='',role=role,stage=name))
        markdown='| Phase | Status | Note |\n|---|---|---|\n'+'\n'.join(f'| {r["name"]} | {r["status"]} | |' for r in phases)
        return dict(exists=True,phases=phases,current_phase=phase,updated=str(p['updated']),markdown=markdown)

    @app.get('/api/projects/{pid}/usage')
    def usage(pid:str):
        store.get(pid)
        by={}
        # Engines emit cumulative snapshots per invocation. Keep the latest per
        # running step rather than adding every streaming snapshot repeatedly.
        current={};run_key=0
        for event in store.events(pid,limit=1000000):
            if event['type']=='helper' and event.get('event')=='start':
                run_key=event['seq']
            if event['type']=='usage':
                current[(event.get('run_id',run_key),event.get('role','app-it'))]=event['usage']
        def empty():
            return dict(api_calls=0,input=0,cache_read=0,output=0,prompt=0,cached_pct=0,cost_usd=0)
        for (_,role),raw in current.items():
            u=raw.get('last',raw)
            prompt=u.get('inputTokens',u.get('input_tokens',0))
            cached=u.get('cachedInputTokens',u.get('cached_input_tokens',u.get('cache_read_input_tokens',0)))
            row=by.setdefault(role,dict(empty(),id=role,label=dict((a[0],a[1]) for a in CATALOG['AGENTS']).get(role,role)))
            row['api_calls']+=1;row['prompt']+=prompt;row['cache_read']+=cached
            row['input']+=max(0,prompt-cached);row['output']+=u.get('outputTokens',u.get('output_tokens',0))
        total=empty()
        for row in by.values():
            row['cached_pct']=round(100*row['cache_read']/row['prompt']) if row['prompt'] else 0
            for key in ['api_calls','input','cache_read','output','prompt']:
                total[key]+=row[key]
        total['cached_pct']=round(100*total['cache_read']/total['prompt']) if total['prompt'] else 0
        return dict(lyra=empty(),agents=total,total=total,by_agent=list(by.values()))

    @app.post('/api/projects/{pid}/team')
    async def team(pid:str,request:Request):
        data=await request.json();ids={a[0] for a in CATALOG['AGENTS']}
        selected=list(dict.fromkeys([*CATALOG['REQUIRED'],*(i for i in data.get('team',[]) if i in ids)]))
        store.update(pid,team=selected);store.message(pid,'assistant','Team updated.','status')
        return detail(pid)

    @app.post('/api/projects/{pid}/settings')
    async def project_settings(pid:str,request:Request):
        data=await request.json()
        if data.get('keep_going'):
            raise ValueError('Tasks already continue until an approval, blocker, or completion. Automatic retry loops are disabled.')
        if 'execution_mode' in data:
            from .direct import set_mode
            set_mode(workflow,pid,data['execution_mode'])
        return detail(pid)

    @app.post('/api/projects/{pid}/new-chat')
    def new_chat(pid:str):
        if pid in workflow.active:
            raise ValueError('Stop the running task before starting a new conversation.')
        store.update(pid,sessions={},session_usage={},chat_id=secrets.token_hex(12))
        return detail(pid)

    @app.post('/api/projects/{pid}/apply-rules')
    def apply_rules(pid:str):
        return detail(pid)

    @app.post('/api/projects/{pid}/update')
    async def update(pid:str,request:Request):
        p=store.get(pid)
        if pid in workflow.active or store.inbox(pid):
            raise ValueError('Finish or stop the current work before starting a new version.')
        branch=(await request.json()).get('branch')
        if branch:
            proc=subprocess.run(['git','switch','-c',branch],cwd=p['root'],capture_output=True,text=True)
            if proc.returncode:
                raise ValueError('Could not create the update branch. Commit current work or choose another branch name.')
        store.update(pid,phase='requirements',revision=p['revision']+1,requirements_notes=[],active_update=dict(revision=p['revision']+1,branch=branch))
        return dict(chat_id=p['chat_id'])

    @app.post('/api/projects/{pid}/review/reopen')
    async def reopen(pid:str,request:Request):
        phase=store.get(pid)['phase'];kind=phase.removesuffix('_review')
        if kind not in ARTIFACTS:
            raise ValueError('No artifact review is pending.')
        for item in store.inbox(pid):
            if item['kind']==kind:
                store.close(pid,item['id'])
        workflow.review(pid,kind);return detail(pid)

    @app.get('/api/projects/{pid}/preview')
    def preview_status(pid:str):
        root=Path(store.get(pid)['root'])
        return dict(available=any((root/d/'index.html').exists() for d in ['','dist','build','out']),
                    build=(root/'package.json').exists(),prototype=artifact_revision(root,'prototype'))

    @app.post('/api/projects/{pid}/preview/{mode}')
    def open_preview(pid:str,mode:str):
        p=store.get(pid)
        if mode not in {'prototype','open'}:
            raise ValueError('Unknown preview mode.')
        result=previews.open(p['root'],mode=='prototype')
        if mode=='prototype':
            result['revision']=artifact_revision(Path(p['root']),'prototype')
        return result

    @app.put('/api/projects/{pid}/files')
    async def upload(pid:str,request:Request,name:str):
        if not name or Path(name).name!=name or name.startswith('.'):
            raise ValueError('Use a plain filename.')
        target=safe_path(Path(store.get(pid)['root']),'assets/uploads/'+name);target.parent.mkdir(parents=True,exist_ok=True)
        temporary=target.with_suffix(target.suffix+'.upload');size=0
        try:
            with temporary.open('wb') as out:
                async for chunk in request.stream():
                    size+=len(chunk)
                    if size>25*1024*1024:
                        raise ValueError('Files must be smaller than 25 MB.')
                    out.write(chunk)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return dict(path=str(target.relative_to(Path(store.get(pid)['root']))),size=size)

    @app.get('/api/settings/phone')
    def phone_settings():
        return phone.snapshot()

    @app.post('/api/settings/phone/{channel}')
    async def phone_action(channel:str,request:Request):
        data=await request.json()
        return await asyncio.to_thread(phone.action,channel,data)

    @app.get('/api/settings')
    def settings():
        return settings_payload()

    @app.post('/api/settings')
    async def save_settings(request:Request):
        data=await request.json();s=workflow.settings()
        if 'about_me' in data:
            s['about_me']=str(data['about_me'])[:10000]
        if 'parallel_work' in data:
            current=s.get('parallel_work',{});selected=data['parallel_work']
            n=int(selected.get('max_workers',current.get('max_workers',3)))
            agents=int(selected.get('agents_per_project',current.get('agents_per_project',3)))
            if not 1<=n<=8:
                raise ValueError('Choose 1–8 concurrent projects.')
            if not 1<=agents<=6:
                raise ValueError('Choose 1–6 development agents per project.')
            s['parallel_work']=dict(max_workers=n,agents_per_project=agents)
        if 'connections' in data:
            for key,conn in data['connections'].items():
                if not re.fullmatch(r'[a-z0-9-]{1,60}',key):
                    raise ValueError('Connection IDs use lowercase letters, digits and hyphens.')
                if conn.get('engine') not in {'codex','claude-cli','copilot','ollama','openai-compatible','anthropic'}:
                    raise ValueError('Unsupported connection engine.')
                if 'api_key' in conn or 'token' in conn:
                    raise ValueError('Store credentials in environment variables, not settings.')
                if conn.get('base_url'):
                    parsed=urlsplit(conn['base_url'])
                    if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password:
                        raise ValueError('Use an HTTP(S) API URL without embedded credentials.')
                s['connections'][key]=conn
        store.save_setting('ai',s);return settings_payload()

    @app.post('/api/settings/model')
    async def save_model(request:Request):
        data=await request.json();s=workflow.settings()
        if data['provider'] not in s['connections']:
            raise ValueError('Configure this connection first.')
        s.update(provider=data['provider'],model='' if data['model']=='default' else data['model'])
        store.save_setting('ai',s);return dict(ok=True)

    @app.post('/api/settings/effort')
    async def effort(request:Request):
        s=workflow.settings();s['effort']=str((await request.json())['effort'])
        store.save_setting('ai',s);return settings_payload()['hermes_effort']

    @app.post('/api/settings/agents/{role}')
    async def agent_model(role:str,request:Request):
        if role not in {a[0] for a in CATALOG['AGENTS']}:
            raise ValueError('Unknown project role.')
        s=workflow.settings();selection=(await request.json()).get('selection')
        if selection and selection.get('provider') not in s['connections']:
            raise ValueError('Configure this connection first.')
        s.setdefault('agent_models',{})[role]=selection;store.save_setting('ai',s)
        return settings_payload()

    @app.get('/api/settings/models')
    async def models(refresh:bool=False):
        s=workflow.settings()
        async def discover_one(key,conn):
            fingerprint=json.dumps(conn,sort_keys=True)
            cached=model_cache.get(key)
            if not refresh and cached and cached['fingerprint']==fingerprint and time.monotonic()-cached['time']<60:
                result=cached['result']
            else:
                result=await asyncio.to_thread(connections.discover,conn)
                model_cache[key]=dict(fingerprint=fingerprint,time=time.monotonic(),result=result)
            names=list(result['models'])
            if key==s['provider'] and s['model'] and s['model'] not in names:names.append(s['model'])
            return dict(slug=key,name=conn.get('label',key),models=names,current=key==s['provider'],
                        default_model=result.get('default_model'),status={k:result[k] for k in ['state','message','source']})
        providers=await asyncio.gather(*(discover_one(key,conn) for key,conn in s['connections'].items()))
        return dict(providers=providers,provider=s['provider'],model=s['model'])

    @app.post('/api/settings/connections/{key}/test')
    async def connection_test(key:str,request:Request):
        s=workflow.settings()
        if key not in s['connections']:raise ValueError('Configure this connection before testing it.')
        data=await request.json()
        result=await asyncio.to_thread(connections.test_connection,s['connections'][key],str(data.get('model','')))
        model_cache.pop(key,None)
        return result

    @app.get('/api/engines')
    def engines_list():
        return dict(engines=available())

    @app.get('/api/folders')
    def folders(path:str|None=None):
        base=Path(path or default_root).expanduser().resolve()
        if not base.is_dir():
            raise ValueError('Folder does not exist.')
        try:
            names=sorted(p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith('.'))
        except OSError:
            raise ValueError('Cannot open this folder.')
        return dict(path=str(base),parent=str(base.parent) if base.parent!=base else None,folders=names[:300])

    @app.post('/api/folders/pick')
    def pick_folder():
        raise HTTPException(501,'Use the folder browser.')

    @app.get('/api/templates')
    def templates(kind:str='website'):
        result=[]
        for base in [ROOT/'templates',home/'templates']:
            if not base.exists():
                continue
            for path in sorted(base.glob('*/template.json')):
                d=json.loads(path.read_text())
                if d.get('kind')==kind:
                    tid=path.parent.name
                    result.append(dict(d,id=tid,own=base==home/'templates',has_demo=(path.parent/'demo/index.html').exists(),
                        demo_url=f'/template-assets/{tid}/demo/index.html',thumb_url=f'/template-assets/{tid}/demo/thumb.jpg' if (path.parent/'demo/thumb.jpg').exists() else None))
        return dict(templates=result)

    @app.post('/api/templates')
    async def add_template(request:Request):
        d=await request.json();tid='own-'+secrets.token_hex(6);base=home/'templates'/tid;base.mkdir(parents=True)
        info=dict(id=tid,name=str(d['name'])[:80],kind=d['kind'],tagline=str(d.get('tagline',''))[:300],best_for='',palette=[],own=True,has_demo=False,demo_url=None)
        (base/'template.json').write_text(json.dumps(info));(base/'spec.md').write_text(str(d['spec'])[:20000]);return info

    @app.delete('/api/templates/{tid}')
    def delete_template(tid:str):
        if not tid.startswith('own-'):
            raise ValueError('Built-in templates cannot be deleted.')
        path=safe_path(home/'templates',tid)
        if path.exists():
            shutil.rmtree(path)
        return dict(ok=True)

    app.mount('/avatars',StaticFiles(directory=ROOT/'ui/public/avatars'),name='avatars')
    app.mount('/template-assets',StaticFiles(directory=ROOT/'templates'),name='template-assets')
    dist=ROOT/'ui/dist'
    if (dist/'assets').exists():
        app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')

    @app.get('/{path:path}')
    def index(path:str):
        if path.startswith('api/'):
            raise HTTPException(404)
        if not (dist/'index.html').exists():
            return HTMLResponse('Build the interface with: cd ui && npm ci && npm run build',503)
        html=(dist/'index.html').read_text()
        html=html.replace('</head>',f'<script>window.__LYRA_TOKEN__={json.dumps(token)};</script></head>')
        return HTMLResponse(html,headers={'Cache-Control':'no-store','X-Frame-Options':'DENY'})

    return app
