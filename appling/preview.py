"""Serve generated pages on a separate origin, never beside the studio API."""
from __future__ import annotations
import http.cookies
import mimetypes
import secrets
import subprocess
import threading
import socket
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from . import children, procs
from .store import safe_path


class Previews:
    def __init__(self):
        self.hosts={};self.expo={};self.lock=threading.Lock()

    def open(self,root,prototype=False):
        root=Path(root)
        if not prototype and (root/'package.json').is_file():
            import json
            package=json.loads((root/'package.json').read_text())
            if 'expo' in {**package.get('dependencies',{}),**package.get('devDependencies',{})}:
                with self.lock:
                    key=str(root)
                    if key not in self.expo or self.expo[key].proc.poll() is not None:
                        if key in self.expo:
                            self.expo[key].stop()
                        self.expo[key]=ExpoPreview(root)
                    return dict(kind='expo',url=self.expo[key].url)
        if prototype:
            base=safe_path(root,'prototypes')
        else:
            base=next((root/d for d in ['dist','build','out'] if (root/d/'index.html').is_file()),None)
            if base is None:
                package=root/'package.json'
                if package.exists():
                    import json
                    if json.loads(package.read_text()).get('scripts',{}).get('build'):
                        proc=subprocess.run(procs.command(['npm','run','build']),cwd=root,capture_output=True,text=True,timeout=300)
                        if proc.returncode:
                            raise ValueError('The application build failed. Ask Appling to inspect the build output.')
                        base=next((root/d for d in ['dist','build','out'] if (root/d/'index.html').is_file()),None)
                if base is None and (root/'index.html').is_file():
                    base=root
        if base is None or not (base/'index.html').is_file():
            raise ValueError('No browser preview exists yet. Ask Appling to create or build it first.')
        base=base.resolve()
        if not base.is_relative_to(root.resolve()):
            raise ValueError('Preview is outside this project.')
        key=(str(root),prototype)
        with self.lock:
            if key not in self.hosts or self.hosts[key][0]!=base:
                if key in self.hosts:
                    self.hosts[key][1].shutdown();self.hosts[key][1].server_close()
                token=secrets.token_urlsafe(24)
                cookie_name='appling_preview_'+secrets.token_hex(6)
                picker=(Path(__file__).resolve().parent.parent/'preview_pick.js').read_text()
                class Handler(BaseHTTPRequestHandler):
                    def log_message(self,*args):
                        pass
                    def do_GET(self):
                        request=urlsplit(self.path)
                        cookies=http.cookies.SimpleCookie()
                        try:
                            cookies.load(self.headers.get('Cookie',''))
                        except http.cookies.CookieError:
                            pass
                        given=parse_qs(request.query).get('key',[''])[0]
                        valid_cookie=cookies.get(cookie_name)
                        if given and secrets.compare_digest(given,token):
                            self.send_response(302)
                            self.send_header('Set-Cookie',f'{cookie_name}={token}; HttpOnly; SameSite=Strict; Path=/')
                            self.send_header('Location',request.path or '/')
                            self.end_headers();return
                        if not valid_cookie or not secrets.compare_digest(valid_cookie.value,token):
                            self.send_error(403);return
                        relative=unquote(request.path).lstrip('/') or 'index.html'
                        if any(part.startswith('.') for part in Path(relative).parts):
                            self.send_error(404);return
                        if relative=='__appit/pick.js':
                            content=picker.encode();mime='text/javascript'
                        else:
                            try:
                                path=safe_path(base,relative)
                                if not path.is_file():
                                    if Path(relative).suffix:
                                        self.send_error(404);return
                                    path=base/'index.html'
                                if path.suffix in {'.py','.toml','.yaml','.yml','.sqlite','.db'} or path.name in {'package-lock.json','package.json'}:
                                    self.send_error(404);return
                                content=path.read_bytes();mime=mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
                            except (ValueError,OSError):
                                self.send_error(404);return
                            if mime=='text/html':
                                content=content.replace(b'</body>',b'<script src="/__appit/pick.js"></script></body>')
                        self.send_response(200);self.send_header('Content-Type',mime)
                        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
                        self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)
                host=ThreadingHTTPServer(('127.0.0.1',0),Handler)
                threading.Thread(target=host.serve_forever,daemon=True).start()
                self.hosts[key]=(base,host,token)
            _,host,token=self.hosts[key]
        return dict(kind='web',url=f'http://127.0.0.1:{host.server_port}/?key={token}')

    def close(self):
        for _,server,_ in self.hosts.values():
            server.shutdown();server.server_close()
        self.hosts.clear()
        for host in self.expo.values():
            host.stop()
        self.expo.clear()


class ExpoPreview:
    """Own the mobile dev server lifecycle and its Expo Go QR URL."""
    def __init__(self,root):
        executable=root/'node_modules/.bin'/('expo.cmd' if procs.WINDOWS else 'expo')   # npm makes .cmd wrappers on Windows
        if not executable.exists():
            raise ValueError('Install this project’s Expo dependencies before opening its phone preview.')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        self.port=port
        log_path=root/'.appling/expo.log';log_path.parent.mkdir(parents=True,exist_ok=True)
        self.log=log_path.open('ab')
        from .engines import environment
        self.proc=procs.spawn([str(executable),'start','--lan','--port',str(port)],cwd=root,
            stdin=subprocess.DEVNULL,stdout=self.log,stderr=subprocess.STDOUT,
            env={**environment(),'BROWSER':'none','EXPO_NO_TELEMETRY':'1'})
        children.track(self.proc)
        try:
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                if self.proc.poll() is not None:
                    raise ValueError('Expo stopped while starting. Check .appling/expo.log in this project.')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/status',timeout=2) as response:
                        if response.status==200:
                            return
                except OSError:
                    time.sleep(.3)
            raise ValueError('Expo took too long to start. Check its project log.')
        except BaseException:
            self.stop();raise

    @property
    def url(self):
        ip='127.0.0.1'
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
                sock.connect(('10.255.255.255',1));ip=sock.getsockname()[0]
        except OSError:
            pass
        return f'exp://{ip}:{self.port}'

    def stop(self):
        procs.stop(self.proc,3)
        children.forget(self.proc)
        self.log.close()
