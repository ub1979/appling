"""lyrad: the APP IT daemon.

A small HTTP API over the per-project files. Sending a message appends to the
project's queue; the UI follows the project's ``events.jsonl`` over SSE.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import secrets
import subprocess
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse

from lyra_lite import agents
from lyra_lite.preview import PREVIEW_TYPES, AppHosts, PreviewError

UPLOADS = Path("assets") / "uploads"
BUILTIN_TEMPLATES = Path(__file__).resolve().parent / "templates"
MAX_UPLOAD = 2 * 1024 ** 3
from lyra_lite.runner import REPO_ROOT, ProjectRunner, project_key
from lyra_lite.store import ProjectStore
from lyra_lite.watchdog import NUDGE

logger = logging.getLogger(__name__)

RULES_PATH = Path(__file__).resolve().parent / "rules" / "lyra.md"
UI_DIST = Path(__file__).resolve().parent / "ui" / "dist"
AVATARS = REPO_ROOT / "web" / "public" / "skill-avatars"
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
    """Changes when APP IT's rules or the app-it playbook change."""
    from lyra_lite.settings import about_me

    digest = hashlib.sha1((rules_text() + about_me()).encode("utf-8"))
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
    from lyra_lite.settings import about_me

    prompt = f"{text}\n\nProject folder: {store.root}\n"
    if about_me():
        prompt += f"\nAbout the owner (written by them; applies to every project):\n{about_me()}\n"
    from lyra_lite.settings import effective_claude, effective_engine

    state = store.state()
    name = effective_engine(state)
    kwargs: dict[str, Any] = {"workspace": str(store.root), "session_key": session_key,
                              "system_prompt": prompt}
    if name == "hermes":
        kwargs["skills"] = DEFAULT_SKILLS
    else:
        kwargs["store"] = store
        kwargs["settings"] = effective_claude(state)
    return make_engine(name, **kwargs)


def placement(path: Path, *, creating: bool) -> str | None:
    """Return a reason the folder can't be used, or None when it can."""
    inside_repo = path == REPO_ROOT or path.is_relative_to(REPO_ROOT)
    if inside_repo:
        if creating:
            return f"New projects go outside APP IT's folder, e.g. {projects_root()}."
        if not any(path.is_relative_to(root) for root in ALLOWED_INSIDE_REPO):
            return "That folder holds APP IT's own files."
    home = Path.home().resolve()
    if path == home or not path.is_relative_to(home):
        return "Choose a folder inside your home folder."
    return None


HELD_PREFIX = "While APP IT was stopped, these reports arrived:"
# Chats saved before the rename still say Lyra.
HELD_PREFIXES = (HELD_PREFIX, "While Lyra was stopped, these reports arrived:")
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
        internal = agents.describe_internal(text) if role == "user" else None
        if internal is not None:
            out.append(internal)
            continue
        if role == "user" and text.startswith(HELD_PREFIXES) and HELD_SPLIT in text:
            held, own = text.split(HELD_SPLIT, 1)
            out.append({"role": "user", "content": held.strip(), "kind": "system"})
            text = own.strip()
        elif role == "user" and text == NUDGE:
            out.append({"role": "user", "content": "APP IT kept going on its own.", "kind": "auto"})
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

    def add_project(self, raw_path: str, *, create: bool, team: list[str] | None = None,
                    style: str | None = None, brief: str = "",
                    models: dict | None = None, profile: str | None = None,
                    kind: str | None = None, template_id: str | None = None,
                    platforms: list[str] | None = None) -> ProjectRunner:
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
        if team is not None or brief or style or profile or kind:
            from lyra_lite.templates import KINDS, get_template

            chosen = agents.normalise_team(team)
            profile = profile if profile in agents.PROFILES else None
            kind = kind if kind in KINDS else None
            if kind == "website":
                # Websites skip the size question: they always get the full
                # functional + visual QA that a public page needs.
                profile = "reusable"
            template = get_template(template_id) if template_id else None
            platforms = agents.normalise_platforms(platforms) if kind == "app" else None
            runner.store.update_state(team=chosen, style=style or "app-it", models=models or {},
                                      profile=profile, project_kind=kind,
                                      template=template["id"] if template else None, platforms=platforms)
            if not runner.store.transcript() and not runner.snapshot()["running"]:
                runner.submit(agents.setup_message(path, chosen, models, brief, profile, kind, template, platforms),
                              kind="setup",
                              display=brief.strip() or "Project opened")
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
            try:
                updated = runner.store.events_path.stat().st_mtime
            except OSError:
                updated = 0.0
            out.append({"id": pid, "name": snap["name"], "root": snap["root"],
                        "running": snap["running"] or bool(snap["helpers"]),
                        "inbox": len(snap["inbox"]), "engine": snap["engine"],
                        "team": snap["team"], "updated": updated})
        return sorted(out, key=lambda p: -p["updated"])

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
            hosts.stop_all()
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
        from lyra_lite import VERSION_LABEL

        return {"projects": lyra.list(), "default_root": str(projects_root()), "version": VERSION_LABEL}

    @app.post("/api/projects")
    def add_project(body: dict = Body(...)):
        team = body.get("team")
        runner = lyra.add_project(
            str(body.get("path") or ""), create=bool(body.get("create")),
            team=[str(t) for t in team] if isinstance(team, list) else None,
            style=str(body.get("style") or "") or None,
            brief=str(body.get("brief") or ""),
            models=body.get("models") if isinstance(body.get("models"), dict) else None,
            profile=str(body.get("profile") or "") or None,
            kind=str(body.get("kind") or "") or None,
            template_id=str(body.get("template") or "") or None,
            platforms=[str(p) for p in body["platforms"]] if isinstance(body.get("platforms"), list) else None,
        )
        return {"id": project_key(runner.root), **runner.snapshot()}

    @app.get("/api/catalog")
    def catalog():
        return {
            "agents": [{"id": i, "label": l, "description": d, "required": i in agents.REQUIRED}
                       for i, l, d in agents.AGENTS],
            "styles": agents.STYLES,
            "default_root": str(projects_root()),
        }

    @app.post("/api/projects/{pid}/team")
    def set_team(pid: str, body: dict = Body(...)):
        runner = lyra.get(pid)
        team = agents.normalise_team([str(t) for t in (body.get("team") or [])])
        models = body.get("models") if isinstance(body.get("models"), dict) else runner.store.state().get("models") or {}
        runner.store.update_state(team=team, models=models)
        runner.submit(agents.team_message(team, models), kind="team",
                      display="Team updated: " + ", ".join(agents.LABELS[t] for t in team))
        return {"ok": True, "team": team}

    @app.get("/api/projects/{pid}")
    def project(pid: str):
        runner = lyra.get(pid)
        snap = runner.snapshot()
        snap["rules_outdated"] = bool(
            snap["has_engine"] and snap["rules_hash"] and snap["rules_hash"] != current_rules_hash()
        )
        return {"id": pid, **snap, "messages": display_messages(runner.store.transcript())}

    @app.post("/api/projects/{pid}/settings")
    def settings(pid: str, body: dict = Body(...)):
        runner = lyra.get(pid)
        if "keep_going" in body:
            runner.set_keep_going(bool(body["keep_going"]))
        if "engine" in body or "claude" in body:
            from lyra_lite.engines import ENGINES

            raw = body.get("engine", runner.store.state().get("engine") if runner.store.state().get("engine_override") else "default")
            engine = None if raw in (None, "", "default") else str(raw)
            if engine is not None and engine not in ENGINES:
                raise HTTPException(status_code=400, detail="Unknown engine")
            claude = body.get("claude")
            if claude is not None and not isinstance(claude, dict):
                raise HTTPException(status_code=400, detail="Bad Claude settings")
            try:
                runner.set_engine(engine, claude={
                    k: str(v).strip() for k, v in (claude or {}).items()
                    if k in {"model", "base_url", "auth_token", "route"}
                } if claude is not None else None)
            except RuntimeError as exc:
                raise HTTPException(status_code=409, detail=str(exc))
        return {"ok": True, **runner.snapshot()}

    # -- Lyra-wide AI settings ----------------------------------------------

    def _settings_view() -> dict:
        from lyra_lite import settings as st

        from lyra_lite.engines.claude import claude_route

        claude = st.claude_defaults()
        return {
            "engine": st.default_engine(),
            "hermes": st.hermes_model(),
            "claude": {"model": claude.get("model", ""), "base_url": claude.get("base_url", ""),
                       "route": claude_route(claude), "has_token": bool(claude.get("auth_token"))},
            "anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()),
            "about_me": st.about_me(),
        }

    def _apply_everywhere() -> None:
        with lyra._lock:
            runners = list(lyra.runners.values())
        for runner in runners:
            runner.request_reload()

    @app.get("/api/settings")
    def get_settings():
        return _settings_view()

    @app.get("/api/settings/models")
    async def settings_models(refresh: bool = False):
        from lyra_lite.settings import model_options

        return await asyncio.to_thread(model_options, refresh)

    @app.post("/api/settings")
    def save_settings(body: dict = Body(...)):
        from lyra_lite import settings as st

        changes: dict[str, Any] = {}
        if "engine" in body:
            if body["engine"] not in st.ENGINES:
                raise HTTPException(status_code=400, detail="Unknown engine")
            changes["engine"] = body["engine"]
        if isinstance(body.get("claude"), dict):
            current = st.claude_defaults()
            for key in ("model", "base_url", "auth_token", "route"):
                if key in body["claude"]:
                    value = str(body["claude"][key] or "").strip()
                    if key == "auth_token" and not value:
                        continue  # blank token field keeps the saved one
                    current[key] = value
            changes["claude"] = {k: v for k, v in current.items() if v}
        if "about_me" in body:
            changes["about_me"] = str(body.get("about_me") or "").strip()[:st.ABOUT_ME_LIMIT]
        if changes:
            st.save_section(changes)
            _apply_everywhere()
        return _settings_view()

    @app.get("/api/settings/claude-cli")
    async def claude_cli():
        from lyra_lite.engines.claude import claude_cli_status

        return await asyncio.to_thread(claude_cli_status)

    @app.post("/api/settings/model")
    async def save_model(body: dict = Body(...)):
        from lyra_lite.settings import set_hermes_model

        provider = str(body.get("provider") or "").strip()
        model = str(body.get("model") or "").strip()
        if not provider or not model:
            raise HTTPException(status_code=400, detail="Choose a provider and a model")
        result = await asyncio.to_thread(set_hermes_model, provider, model, bool(body.get("confirm")))
        if result.get("ok"):
            _apply_everywhere()
        return result

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

    @app.get("/api/projects/{pid}/usage")
    def usage(pid: str):
        from lyra_lite.usage import summarise_usage

        return summarise_usage(lyra.get(pid).store)

    @app.put("/api/projects/{pid}/files")
    async def upload(pid: str, request: Request, name: str = ""):
        """Save an attached file into the project (assets/uploads/), streamed
        so a long video never sits in memory. Returns its project path."""
        root = lyra.get(pid).root
        stem = re.sub(r"[^A-Za-z0-9._ -]+", "-", Path(name).name).strip(" .-")[:120]
        if not stem:
            raise HTTPException(status_code=400, detail="The file needs a name")
        folder = root / UPLOADS
        folder.mkdir(parents=True, exist_ok=True)
        ignore = folder / ".gitignore"
        if not ignore.exists():
            # Originals (often big videos) stay out of the project's history;
            # what the site actually uses (frames, cut-outs) is committed.
            ignore.write_text("*\n!.gitignore\n")
        target, n = folder / stem, 2
        while target.exists():
            target, n = folder / f"{Path(stem).stem}-{n}{Path(stem).suffix}", n + 1
        size = 0
        part = target.with_name(target.name + ".part")
        try:
            with part.open("wb") as fh:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_UPLOAD:
                        raise HTTPException(status_code=413, detail="That file is over 2 GB")
                    fh.write(chunk)
            part.replace(target)
        finally:
            part.unlink(missing_ok=True)
        rel = target.relative_to(root).as_posix()
        runner = lyra.get(pid)
        runner.store.append_event("file_added", path=rel, size=size)
        return {"path": rel, "size": size}

    hosts = AppHosts()
    app.state.app_hosts = hosts

    @app.get("/api/projects/{pid}/preview")
    def preview_info(pid: str):
        from lyra_lite import preview

        root = lyra.get(pid).root
        return {"available": preview.available(root), "build": preview.build_script(root) is not None}

    @app.post("/api/projects/{pid}/preview/open")
    def preview_open(pid: str):
        """Build the site if it needs it, serve it at its own address, return that address."""
        try:
            return hosts.open(lyra.get(pid).root)
        except PreviewError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    def _serve_static(base: Path, path: str):
        parts = [p for p in (path or "index.html").split("/") if p]
        if any(p.startswith(".") for p in parts):
            raise HTTPException(status_code=404)
        target = (base.joinpath(*parts) if parts else base / "index.html").resolve()
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file() or not target.is_relative_to(base.resolve()):
            raise HTTPException(status_code=404)
        kind = PREVIEW_TYPES.get(target.suffix.lower())
        if kind is None:
            raise HTTPException(status_code=404)
        return FileResponse(target, media_type=kind, headers={"Cache-Control": "no-store"})

    def _check_cookie(request: Request) -> None:
        # Browser tabs can't send headers, so previews use Lyra's cookie.
        if not secrets.compare_digest(request.cookies.get("lyra_token", ""), token):
            raise HTTPException(status_code=401, detail="Open this from APP IT")

    # Declared before the project preview so "templates" is never read as a project id.
    @app.get("/preview/templates/{tid}/{path:path}")
    def template_demo(tid: str, path: str, request: Request):
        from lyra_lite.templates import demo_dir

        _check_cookie(request)
        base = demo_dir(tid)
        if base is None:
            raise HTTPException(status_code=404, detail="This template has no live demo")
        return _serve_static(base, path)

    # -- templates -----------------------------------------------------------

    @app.get("/api/templates")
    def templates_list(kind: str | None = None):
        from lyra_lite.templates import list_templates

        items = list_templates(kind or None)
        for t in items:
            preview = t.get("preview") or {}
            if t.pop("local_demo", False):
                t["demo_url"] = f"/preview/templates/{t['id']}/"
                has_thumb = (BUILTIN_TEMPLATES / t["id"] / "demo" / "thumb.jpg").is_file()
                t["thumb_url"] = t["demo_url"] + "thumb.jpg" if has_thumb else None
            else:
                t["demo_url"] = preview.get("video")
                t["thumb_url"] = preview.get("poster")
        return {"templates": items}

    @app.post("/api/templates")
    def templates_add(body: dict = Body(...)):
        from lyra_lite.templates import save_user_template

        try:
            return save_user_template(str(body.get("name") or ""), str(body.get("kind") or "website"),
                                      str(body.get("spec") or ""), str(body.get("tagline") or ""))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.delete("/api/templates/{tid}")
    def templates_delete(tid: str):
        from lyra_lite.templates import delete_user_template

        if not delete_user_template(tid):
            raise HTTPException(status_code=404, detail="Only your own templates can be removed")
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
        runner = lyra.get(pid)
        try:
            chat_id = runner.new_chat()
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        state = runner.store.state()
        if state.get("team"):
            from lyra_lite.templates import get_template

            template = get_template(state["template"]) if state.get("template") else None
            runner.submit(agents.setup_message(runner.root, state["team"], state.get("models"), "",
                                               state.get("profile"), state.get("project_kind"), template,
                                               state.get("platforms")),
                          kind="setup", display="Project opened")
        return {"chat_id": chat_id}

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
            return HTMLResponse("<p>APP IT UI is not built. Run <code>npm run build</code> "
                                "in <code>lyra_lite/ui</code>.</p>")
        html = index.read_text(encoding="utf-8")
        tag = f"<script>window.__LYRA_TOKEN__={json.dumps(token)};</script>"
        res = HTMLResponse(html.replace("</head>", f"{tag}</head>", 1))
        res.set_cookie("lyra_token", token, httponly=True, samesite="strict", path="/preview")
        return res

    @app.get("/avatars/{name}")
    def avatar(name: str):
        target = (AVATARS / name).resolve()
        if target.is_file() and target.is_relative_to(AVATARS.resolve()) and target.suffix == ".webp":
            return FileResponse(target, headers={"Cache-Control": "max-age=86400"})
        raise HTTPException(status_code=404)

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
