"""lyrad: the Lyra Lite daemon.

A small HTTP API over the per-project files. Sending a message appends to the
project's queue; the UI follows the project's ``events.jsonl`` over SSE.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import secrets
import subprocess
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse

from lyra_lite.runner import REPO_ROOT, ProjectRunner, project_key
from lyra_lite.store import ProjectStore
from lyra_lite.watchdog import NUDGE

logger = logging.getLogger(__name__)

RULES_PATH = Path(__file__).resolve().parent / "rules" / "lyra.md"
UI_DIST = Path(__file__).resolve().parent / "ui" / "dist"
DEFAULT_SKILLS = ["ultimate-builder:app-it"]
ALLOWED_INSIDE_REPO = [REPO_ROOT / "my_projects"]


def projects_root() -> Path:
    return Path.home() / "Lyra Projects"


def _registry_path() -> Path:
    from hermes_constants import get_hermes_home

    return get_hermes_home() / "lyra-lite" / "projects.json"


def rules_text() -> str:
    try:
        return RULES_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


APP_IT_SKILL = REPO_ROOT / "plugins" / "ultimate-builder" / "skills" / "app-it" / "SKILL.md"


def current_rules_hash() -> str:
    """Changes when Lyra's rules or the app-it playbook change."""
    digest = hashlib.sha1(rules_text().encode("utf-8"))
    try:
        digest.update(APP_IT_SKILL.read_bytes())
    except OSError:
        pass
    return digest.hexdigest()[:12]


def lyra_settings() -> dict:
    """The ``lyra_lite:`` section of config.yaml (optional)."""
    try:
        from hermes_cli.config import load_config

        section = (load_config() or {}).get("lyra_lite") or {}
        return section if isinstance(section, dict) else {}
    except Exception:
        return {}


def default_engine_factory(store: ProjectStore, session_key: str):
    from lyra_lite.engines import make_engine

    text = rules_text()
    store.update_state(rules_hash=current_rules_hash())
    prompt = f"{text}\n\nProject folder: {store.root}\n"
    state = store.state()
    name = state.get("engine") or "hermes"
    kwargs: dict[str, Any] = {"workspace": str(store.root), "session_key": session_key,
                              "system_prompt": prompt}
    if name == "hermes":
        kwargs["skills"] = DEFAULT_SKILLS
    else:
        kwargs["store"] = store
        kwargs["settings"] = state.get(name) or {}
    return make_engine(name, **kwargs)


def placement(path: Path, *, creating: bool) -> str | None:
    """Return a reason the folder can't be used, or None when it can."""
    inside_repo = path == REPO_ROOT or path.is_relative_to(REPO_ROOT)
    if inside_repo:
        if creating:
            return f"New projects go outside Lyra's folder, e.g. {projects_root()}."
        if not any(path.is_relative_to(root) for root in ALLOWED_INSIDE_REPO):
            return "That folder holds Lyra's own files."
    home = Path.home().resolve()
    if path == home or not path.is_relative_to(home):
        return "Choose a folder inside your home folder."
    return None


HELD_PREFIX = "While Lyra was stopped, these reports arrived:"
HELD_SPLIT = "The owner's message:"


def display_messages(messages: list[dict]) -> list[dict]:
    """The chat as the owner sees it: user and assistant text only."""
    out: list[dict] = []
    for m in messages:
        role = m.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = m.get("content")
        if isinstance(content, list):
            content = "\n".join(
                str(p.get("text") or "") for p in content if isinstance(p, dict)
            )
        text = str(content or "").strip()
        if not text:
            continue
        kind = "chat"
        if role == "user" and text.startswith(HELD_PREFIX) and HELD_SPLIT in text:
            held, own = text.split(HELD_SPLIT, 1)
            out.append({"role": "user", "content": held.strip(), "kind": "system"})
            text = own.strip()
        elif role == "user" and text == NUDGE:
            out.append({"role": "user", "content": "Lyra kept going on its own.", "kind": "auto"})
            continue
        elif role == "user" and text.startswith("["):
            kind = "system"
        out.append({"role": role, "content": text, "kind": kind})
    return out


class Lyra:
    """Process-wide registry of project runners plus the helper-result poller."""

    def __init__(self, engine_factory=default_engine_factory):
        self.engine_factory = engine_factory
        self.runners: dict[str, ProjectRunner] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._poller: threading.Thread | None = None

    # -- projects --------------------------------------------------------

    def _load_registry(self) -> list[str]:
        try:
            data = json.loads(_registry_path().read_text(encoding="utf-8"))
            return [str(p) for p in data.get("projects", []) if isinstance(p, str)]
        except (OSError, ValueError, AttributeError):
            return []

    def _save_registry(self) -> None:
        path = _registry_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            roots = sorted(str(r.root) for r in self.runners.values())
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"projects": roots}, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)

    def start(self) -> None:
        for root in self._load_registry():
            if Path(root).is_dir():
                try:
                    self._attach(Path(root))
                except Exception:
                    logger.warning("lyra-lite: could not open %s", root, exc_info=True)
        self._poller = threading.Thread(target=self._poll_completions,
                                        name="lyra-completions", daemon=True)
        self._poller.start()
        threading.Thread(target=self._watchdog_loop, name="lyra-watchdog", daemon=True).start()

    def _watchdog_loop(self) -> None:
        while True:
            settings = lyra_settings().get("watchdog") or {}
            if self._stop.wait(float(settings.get("check_seconds") or 30)):
                return
            if settings.get("enabled") is False:
                continue
            with self._lock:
                runners = list(self.runners.values())
            for runner in runners:
                try:
                    runner.watchdog_tick(settings)
                except Exception:
                    logger.warning("lyra-lite: watchdog check failed for %s", runner.root,
                                   exc_info=True)

    def shutdown(self) -> None:
        self._stop.set()
        with self._lock:
            runners = list(self.runners.values())
        for runner in runners:
            runner.shutdown()

    def _attach(self, root: Path) -> ProjectRunner:
        pid = project_key(root)
        with self._lock:
            runner = self.runners.get(pid)
            if runner is None:
                runner = ProjectRunner(ProjectStore(root), self.engine_factory)
                self.runners[pid] = runner
        return runner

    def add_project(self, raw_path: str, *, create: bool) -> ProjectRunner:
        path = Path(raw_path).expanduser().resolve(strict=False)
        reason = placement(path, creating=create and not path.exists())
        if reason:
            raise HTTPException(status_code=400, detail=reason)
        if not path.exists():
            if not create:
                raise HTTPException(status_code=404, detail="Folder not found")
            path.mkdir(parents=True)
        if not path.is_dir():
            raise HTTPException(status_code=400, detail="Not a folder")
        if not (path / ".git").exists():
            subprocess.run(["git", "init", "-q"], cwd=path, check=False)
        runner = self._attach(path)
        self._save_registry()
        return runner

    def get(self, pid: str) -> ProjectRunner:
        with self._lock:
            runner = self.runners.get(pid)
        if runner is None:
            raise HTTPException(status_code=404, detail="Unknown project")
        return runner

    def list(self) -> list[dict]:
        with self._lock:
            items = list(self.runners.items())
        out = []
        for pid, runner in items:
            snap = runner.snapshot()
            out.append({"id": pid, "name": snap["name"], "root": snap["root"],
                        "running": snap["running"], "inbox": len(snap["inbox"])})
        return sorted(out, key=lambda p: p["name"].lower())

    # -- helper results --------------------------------------------------

    def _owner(self, key: str) -> ProjectRunner | None:
        with self._lock:
            for runner in self.runners.values():
                if runner.owns_session_key(key):
                    return runner
        return None

    def _poll_completions(self) -> None:
        from tools.async_delegation import (
            claim_event_delivery,
            complete_event_delivery,
            release_event_delivery,
            restore_undelivered_completions,
        )
        from tools.process_registry import format_process_notification, process_registry

        queue = process_registry.completion_queue
        try:
            # Helpers that finished (or died) while Lyra was down report now.
            restored = restore_undelivered_completions(queue)
            if restored:
                logger.info("lyra-lite: restored %d undelivered helper result(s)", restored)
        except Exception:
            logger.warning("lyra-lite: could not restore helper results", exc_info=True)

        while not self._stop.is_set():
            try:
                evt = queue.get(timeout=1)
            except Exception:
                continue
            runner = self._owner(str(evt.get("session_key") or ""))
            if runner is None:
                # Another app's (or an old chat's) result: leave it pending in
                # the durable store for its own owner instead of adopting it.
                logger.info("lyra-lite: ignoring helper result for %r",
                            evt.get("session_key"))
                continue
            claim = claim_event_delivery(evt, "lyra-lite")
            if claim is None:
                continue
            try:
                text = format_process_notification(evt)
                if text:
                    runner.store.append_event(
                        "helper", event="reported", subagent_id=str(evt.get("delegation_id") or ""),
                        goal=str(evt.get("goal") or "")[:300], status=str(evt.get("status") or ""),
                    )
                    runner.submit(text, kind="helper_done")
                complete_event_delivery(evt, claim)
            except Exception:
                release_event_delivery(evt, claim)
                logger.warning("lyra-lite: helper result delivery failed", exc_info=True)


def create_app(lyra: Lyra | None = None, token: str | None = None) -> FastAPI:
    lyra = lyra or Lyra()
    token = token or secrets.token_urlsafe(24)

    @asynccontextmanager
    async def lifespan(_app):
        lyra.start()
        try:
            yield
        finally:
            lyra.shutdown()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.lyra = lyra
    app.state.token = token

    @app.middleware("http")
    async def _auth(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            given = request.headers.get("x-lyra-token") or request.query_params.get("token")
            if not given or not secrets.compare_digest(given, token):
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return await call_next(request)

    # -- API ---------------------------------------------------------------

    @app.get("/api/projects")
    def list_projects():
        return {"projects": lyra.list(), "default_root": str(projects_root())}

    @app.post("/api/projects")
    def add_project(body: dict = Body(...)):
        runner = lyra.add_project(str(body.get("path") or ""), create=bool(body.get("create")))
        return {"id": project_key(runner.root), **runner.snapshot()}

    @app.get("/api/projects/{pid}")
    def project(pid: str):
        runner = lyra.get(pid)
        snap = runner.snapshot()
        snap["rules_outdated"] = bool(
            snap["has_engine"] and snap["rules_hash"] and snap["rules_hash"] != current_rules_hash()
        )
        return {"id": pid, **snap, "messages": display_messages(runner.store.messages())}

    @app.post("/api/projects/{pid}/settings")
    def settings(pid: str, body: dict = Body(...)):
        runner = lyra.get(pid)
        if "keep_going" in body:
            runner.set_keep_going(bool(body["keep_going"]))
        if "engine" in body or "claude" in body:
            from lyra_lite.engines import ENGINES

            engine = str(body.get("engine") or runner.store.state().get("engine") or "hermes")
            if engine not in ENGINES:
                raise HTTPException(status_code=400, detail="Unknown engine")
            claude = body.get("claude")
            if claude is not None and not isinstance(claude, dict):
                raise HTTPException(status_code=400, detail="Bad Claude settings")
            try:
                runner.set_engine(engine, claude={
                    k: str(v).strip() for k, v in (claude or {}).items()
                    if k in {"model", "base_url", "auth_token"}
                } if claude is not None else None)
            except RuntimeError as exc:
                raise HTTPException(status_code=409, detail=str(exc))
        return {"ok": True, **runner.snapshot()}

    @app.get("/api/engines")
    def engines():
        from lyra_lite.engines import ENGINES

        return {"engines": [{"id": k, "label": v} for k, v in ENGINES.items()],
                "anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())}

    @app.post("/api/projects/{pid}/apply-rules")
    def apply_rules(pid: str):
        try:
            lyra.get(pid).reload_engine()
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return {"ok": True}

    @app.get("/api/projects/{pid}/map")
    def project_map(pid: str):
        from lyra_lite.project_map import read_map

        return read_map(lyra.get(pid).root)

    @app.post("/api/projects/{pid}/messages")
    def send(pid: str, body: dict = Body(...)):
        try:
            item = lyra.get(pid).submit(str(body.get("text") or ""))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"queued": item}

    @app.post("/api/projects/{pid}/inbox/{item_id}")
    def answer(pid: str, item_id: str, body: dict = Body(...)):
        ok = lyra.get(pid).answer(item_id, body.get("answer"))
        if not ok:
            raise HTTPException(status_code=409, detail="That request has expired.")
        return {"ok": True}

    @app.post("/api/projects/{pid}/stop")
    def stop(pid: str):
        lyra.get(pid).stop_turn()
        return {"ok": True}

    @app.post("/api/projects/{pid}/new-chat")
    def new_chat(pid: str):
        try:
            return {"chat_id": lyra.get(pid).new_chat()}
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    @app.get("/api/projects/{pid}/stream")
    async def stream(pid: str, request: Request, offset: int | None = None):
        runner = lyra.get(pid)
        last_id = request.headers.get("last-event-id")
        if last_id and last_id.isdigit():
            offset = int(last_id)
        if offset is None:
            offset = int(runner.store.state().get("turn_start_offset") or 0)

        async def gen():
            pos = max(0, offset)
            quiet = 0.0
            yield f"retry: 2000\n\n"
            while not await request.is_disconnected():
                events, new_pos = await asyncio.to_thread(runner.store.read_events, pos)
                if events:
                    for i, evt in enumerate(events):
                        head = f"id: {new_pos}\n" if i == len(events) - 1 else ""
                        yield f"{head}data: {json.dumps(evt, ensure_ascii=False)}\n\n"
                    pos = new_pos
                    quiet = 0.0
                else:
                    quiet += 0.2
                    if quiet >= 15:
                        quiet = 0.0
                        yield ": keep-alive\n\n"
                await asyncio.sleep(0.2)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    @app.get("/api/folders")
    def folders(path: str | None = None):
        base = Path(path).expanduser().resolve() if path else projects_root()
        home = Path.home().resolve()
        if not base.is_relative_to(home):
            base = home
        if not base.exists():
            base = home
        dirs = sorted(
            (p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")),
            key=str.lower,
        ) if base.is_dir() else []
        return {"path": str(base), "parent": str(base.parent) if base != home else None,
                "folders": dirs}

    # -- UI ----------------------------------------------------------------

    def _index() -> HTMLResponse:
        index = UI_DIST / "index.html"
        if not index.exists():
            return HTMLResponse("<p>Lyra Lite UI is not built. Run <code>npm run build</code> "
                                "in <code>lyra_lite/ui</code>.</p>")
        html = index.read_text(encoding="utf-8")
        tag = f"<script>window.__LYRA_TOKEN__={json.dumps(token)};</script>"
        return HTMLResponse(html.replace("</head>", f"{tag}</head>", 1))

    @app.get("/")
    def root():
        return _index()

    @app.get("/{path:path}")
    def static(path: str):
        target = (UI_DIST / path).resolve()
        if target.is_file() and target.is_relative_to(UI_DIST.resolve()):
            return FileResponse(target)
        return _index()

    return app
