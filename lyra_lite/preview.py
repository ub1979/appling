"""Open app: build the project's site when it needs it, then serve it like a host.

A built site (Vite, React, …) asks for ``/assets/...`` from the root of its
address, so it only works when served at ``/`` — under APP IT's own
``/preview/<id>/`` path its styles and scripts never load. Each project's app
therefore gets its own small local server on a free port (localhost only).
The first visit carries a one-time key in the address, which becomes a cookie
for that port, so other local pages can't read the app.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

# Built output first: a Vite project's root index.html is source, not the app.
PREVIEW_DIRS = ("dist", "build", "out", "", "public")
PREVIEW_TYPES = {
    ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".mjs": "text/javascript",
    ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp", ".avif": "image/avif",
    ".ico": "image/x-icon", ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf",
    ".txt": "text/plain", ".map": "application/json", ".mp4": "video/mp4", ".webm": "video/webm",
    ".mp3": "audio/mpeg", ".glb": "model/gltf-binary", ".gltf": "model/gltf+json", ".wasm": "application/wasm",
}
BUILD_OUTPUTS = ("dist", "build", "out")
# Folders whose changes never make the built site stale.
_NOT_SOURCE = {"node_modules", ".git", ".lyra", ".sdlc", ".vite", "coverage", *BUILD_OUTPUTS}
PICK_SCRIPT = Path(__file__).with_name("preview_pick.js")
PICK_PATH = "/__appit/pick.js"
INSTALL_TIMEOUT = 600
BUILD_TIMEOUT = 300


class PreviewError(RuntimeError):
    """Why the app can't be opened, in words for the owner."""


def preview_root(project: Path) -> Path | None:
    """The folder holding the app's web page, if the project has one."""
    for sub in PREVIEW_DIRS:
        base = project / sub if sub else project
        if (base / "index.html").is_file():
            return base
    return None


def build_script(project: Path) -> str | None:
    try:
        scripts = json.loads((project / "package.json").read_text(encoding="utf-8")).get("scripts") or {}
    except (OSError, ValueError, AttributeError):
        return None
    return scripts.get("build") if isinstance(scripts, dict) else None


def _package(project: Path) -> dict:
    try:
        data = json.loads((project / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def is_expo(project: Path) -> bool:
    pkg = _package(project)
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
    return "expo" in deps


def available(project: Path) -> bool:
    return is_expo(project) or build_script(project) is not None or preview_root(project) is not None


def lan_ip() -> str:
    """This computer's address on the local network (what a phone can reach)."""
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no packet is sent
            ip = s.getsockname()[0]
            if not ip.startswith("127."):
                return ip
    except OSError:
        pass
    return "127.0.0.1"


def _free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("0.0.0.0", 0))
        return s.getsockname()[1]


class _ExpoHost:
    """`expo start` for a phone app, kept running so the phone live-reloads."""

    START_TIMEOUT = 120

    def __init__(self, project: Path):
        import time
        import urllib.request

        self.project = project
        self.port = _free_port()
        local = project / "node_modules" / ".bin" / "expo"
        cmd = [str(local)] if local.exists() else [shutil.which("npx") or "npx", "expo"]
        log = project / ".lyra" / "expo.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        self._log = log.open("ab")
        self.proc = subprocess.Popen(
            [*cmd, "start", "--lan", "--port", str(self.port)], cwd=project, stdin=subprocess.DEVNULL,
            stdout=self._log, stderr=subprocess.STDOUT, start_new_session=True,
            env={**os.environ, "BROWSER": "none", "EXPO_NO_TELEMETRY": "1", "EXPO_NO_REDIRECT_PAGE": "1"})
        deadline = time.time() + self.START_TIMEOUT
        while time.time() < deadline:
            if self.proc.poll() is not None:
                tail = "\n".join(log.read_text(errors="replace").strip().splitlines()[-10:])
                raise PreviewError(f"The phone preview (Expo) stopped while starting. Ask APP IT to fix it:\n{tail}")
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/status", timeout=2)
                return
            except OSError:
                time.sleep(1)
        self.stop()
        raise PreviewError("The phone preview (Expo) took too long to start.")

    def alive(self) -> bool:
        return self.proc.poll() is None

    @property
    def url(self) -> str:
        return f"exp://{lan_ip()}:{self.port}"

    def stop(self) -> None:
        import signal

        if self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
                self.proc.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                self.proc.kill()
        self._log.close()


def _built(project: Path) -> Path | None:
    for sub in BUILD_OUTPUTS:
        if (project / sub / "index.html").is_file():
            return project / sub
    return None


def _newest_source(project: Path) -> float:
    newest = 0.0
    for top, dirs, files in os.walk(project):
        dirs[:] = [d for d in dirs if d not in _NOT_SOURCE and not d.startswith(".")]
        for name in files:
            try:
                newest = max(newest, (Path(top) / name).stat().st_mtime)
            except OSError:
                pass
    return newest


def _run(cmd: list[str], project: Path, timeout: int, what: str) -> None:
    try:
        done = subprocess.run(cmd, cwd=project, capture_output=True, text=True, timeout=timeout,
                              env={**os.environ, "CI": "1", "BROWSER": "none"})
    except subprocess.TimeoutExpired:
        raise PreviewError(f"{what} took longer than {timeout // 60} minutes and was stopped.")
    if done.returncode != 0:
        tail = "\n".join((done.stdout + "\n" + done.stderr).strip().splitlines()[-12:])
        raise PreviewError(f"{what} failed, so there is nothing to open yet. Ask APP IT to fix it:\n{tail}")


_build_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def prepare(project: Path) -> Path:
    """Return the folder to serve, installing and building first when needed."""
    project = Path(project)
    if build_script(project) is None:
        base = preview_root(project)
        if base is None:
            raise PreviewError("This project has no web page yet.")
        return base
    with _locks_guard:
        lock = _build_locks.setdefault(str(project), threading.Lock())
    with lock:
        npm = shutil.which("npm")
        if npm is None:
            raise PreviewError("Node.js isn't installed, so the site can't be built. Install it from nodejs.org.")
        if not (project / "node_modules").is_dir():
            _run([npm, "install", "--no-audit", "--no-fund"], project, INSTALL_TIMEOUT, "Installing the site's packages")
        out = _built(project)
        if out is None or (out / "index.html").stat().st_mtime < _newest_source(project):
            _run([npm, "run", "build"], project, BUILD_TIMEOUT, "Building the site")
            out = _built(project)
        if out is None:
            raise PreviewError("The build finished but made no index.html in dist/ or build/.")
        return out


def _with_pick(html: bytes) -> bytes:
    """Add APP IT's preview helper to a page (inert outside the preview panel)."""
    tag = f'<script src="{PICK_PATH}" defer></script>'.encode()
    lower = html.lower()
    for marker in (b"</head>", b"<body", b"</html>"):
        at = lower.find(marker)
        if at != -1:
            return html[:at] + tag + html[at:]
    return tag + html


class _Host:
    def __init__(self, base: Path):
        self.base = base.resolve()
        self.secret = secrets.token_urlsafe(18)
        host = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args) -> None:
                pass

            def do_HEAD(self) -> None:
                self.do_GET(body=False)

            def do_GET(self, body: bool = True) -> None:
                url = urlsplit(self.path)
                cookie = f"lyra_app_{self.server.server_address[1]}"
                if parse_qs(url.query).get("lyra", [""])[0] == host.secret:
                    self.send_response(302)
                    self.send_header("Location", url.path or "/")
                    self.send_header("Set-Cookie", f"{cookie}={host.secret}; Path=/; HttpOnly; SameSite=Strict")
                    self.end_headers()
                    return
                if url.path == PICK_PATH:  # APP IT's own helper, not part of the app
                    return self._send(200, "text/javascript", PICK_SCRIPT.read_bytes(), body)
                sent = dict(p.strip().split("=", 1) for p in (self.headers.get("Cookie") or "").split(";") if "=" in p)
                if not secrets.compare_digest(sent.get(cookie, ""), host.secret):
                    return self._plain(401, "Open this app from APP IT's Open app button.")
                target = host.resolve(url.path)
                if target is None:
                    return self._plain(404, "Not found")
                data = target.read_bytes()
                kind = PREVIEW_TYPES[target.suffix.lower()]
                if kind == "text/html":
                    data = _with_pick(data)
                self._send(200, kind, data, body)

            def _send(self, code: int, kind: str, data: bytes, body: bool = True) -> None:
                self.send_response(code)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                if body:
                    self.wfile.write(data)

            def _plain(self, code: int, text: str) -> None:
                data = text.encode()
                self.send_response(code)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, name=f"lyra-app-{self.port}", daemon=True).start()

    def resolve(self, raw_path: str) -> Path | None:
        parts = [p for p in unquote(raw_path).split("/") if p]
        if any(p.startswith(".") or "\\" in p for p in parts):
            return None
        target = self.base.joinpath(*parts).resolve() if parts else self.base / "index.html"
        if target.is_dir():
            target = target / "index.html"
        if not target.is_relative_to(self.base):
            return None
        if not target.is_file():
            # Single-page apps route in the browser: unknown pages get the app.
            if parts and "." not in parts[-1]:
                target = self.base / "index.html"
            if not target.is_file():
                return None
        return target if target.suffix.lower() in PREVIEW_TYPES else None

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class AppHosts:
    """One local server per project, reused while it serves the same folder."""

    def __init__(self) -> None:
        self._hosts: dict[str, _Host] = {}
        self._expo: dict[str, _ExpoHost] = {}
        self._lock = threading.Lock()

    def open(self, project: Path) -> dict:
        """Get the project's app ready to look at.

        Web apps: ``{"kind": "web", "url": "http://127.0.0.1:…/?lyra=…"}``.
        Phone apps (Expo): ``{"kind": "expo", "url": "exp://<lan-ip>:<port>"}``
        — the address Expo Go opens from a QR code.
        """
        project = Path(project)
        if is_expo(project):
            return {"kind": "expo", "url": self._open_expo(project)}
        base = prepare(project).resolve()
        with self._lock:
            host = self._hosts.get(str(project))
            if host is None or host.base != base:
                if host is not None:
                    host.stop()
                host = self._hosts[str(project)] = _Host(base)
        return {"kind": "web", "url": f"http://127.0.0.1:{host.port}/?lyra={host.secret}"}

    def _open_expo(self, project: Path) -> str:
        with _locks_guard:
            lock = _build_locks.setdefault(str(project), threading.Lock())
        with lock:
            host = self._expo.get(str(project))
            if host is not None and host.alive():
                return host.url
            if not (project / "node_modules").is_dir():
                npm = shutil.which("npm")
                if npm is None:
                    raise PreviewError("Node.js isn't installed, so the phone preview can't start. Install it from nodejs.org.")
                _run([npm, "install", "--no-audit", "--no-fund"], project, INSTALL_TIMEOUT, "Installing the app's packages")
            host = _ExpoHost(project)
            self._expo[str(project)] = host
            return host.url

    def stop_all(self) -> None:
        with self._lock:
            for host in self._hosts.values():
                host.stop()
            self._hosts.clear()
            for host in self._expo.values():
                host.stop()
            self._expo.clear()
