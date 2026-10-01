"""One worker per project: runs queued turns in order and records them to files.

Messages, helper completions and (later) watchdog nudges all arrive the same
way — appended to the persisted queue in ``state.json`` — so anything can
drive Lyra without touching a live connection.
"""

from __future__ import annotations

import hashlib
import importlib.util
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from lyra_lite import watchdog
from lyra_lite.engines.base import Engine, TurnResult
from lyra_lite.project_map import read_map
from lyra_lite.settings import effective_engine
from lyra_lite.store import ProjectStore

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
RESTART_NOTE = (
    "(Lyra was restarted before finishing this reply. Work done so far is in "
    "the project files: check git status and .sdlc/progress.md before continuing.)"
)

EngineFactory = Callable[[ProjectStore, str], Engine]


def project_key(root: Path) -> str:
    return hashlib.sha1(str(root).encode("utf-8")).hexdigest()[:10]


def _load_checkpoint():
    path = REPO_ROOT / "plugins" / "ultimate-builder" / "project_checkpoint.py"
    try:
        spec = importlib.util.spec_from_file_location("lyra_lite_project_checkpoint", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module.checkpoint_project
    except Exception:
        logger.warning("lyra-lite: checkpoint module unavailable", exc_info=True)
        return None


_checkpoint_project = None


def checkpoint(workspace: Path, **kwargs) -> str | None:
    global _checkpoint_project
    if _checkpoint_project is None:
        _checkpoint_project = _load_checkpoint() or (lambda *_a, **_k: None)
    try:
        return _checkpoint_project(str(workspace), **kwargs)
    except Exception:
        logger.warning("lyra-lite: checkpoint failed", exc_info=True)
        return None


class _Hooks:
    """The runner's side of the pipe. Lives as long as the runner, because
    background helpers keep reporting after the turn that started them ends;
    ``turn_id`` is None between turns."""

    def __init__(self, runner: "ProjectRunner"):
        self.runner = runner
        self.turn_id: str | None = None

    def emit(self, type_: str, **data: Any) -> None:
        self.runner.store.append_event(type_, turn=self.turn_id, **data)

    def ask(self, kind: str, on_answer: Callable[[Any], None], **fields: Any) -> str:
        return self.runner._open_inbox(kind, on_answer, turn=self.turn_id, **fields)

    def expire(self, item_id: str) -> None:
        self.runner._close_inbox(item_id, "expired")


class ProjectRunner:
    def __init__(self, store: ProjectStore, engine_factory: EngineFactory):
        self.store = store.init()
        self.key_prefix = f"lyra-{project_key(store.root)}"
        self._engine_factory = engine_factory
        self._engine: Engine | None = None
        self._engine_chat: str | None = None
        self._waiters: dict[str, Callable[[Any], None]] = {}
        self._cond = threading.Condition()
        self._stop = False
        self._busy = False
        self._hooks = _Hooks(self)
        self._reload_pending = False
        self._recover()
        self._thread = threading.Thread(
            target=self._loop, name=f"lyra-runner-{store.root.name}", daemon=True
        )
        self._thread.start()

    # -- identity --------------------------------------------------------

    @property
    def root(self) -> Path:
        return self.store.root

    def session_key(self) -> str:
        return f"{self.key_prefix}-{self.store.state().get('chat_id')}"

    def owns_session_key(self, key: str) -> bool:
        return bool(key) and key.startswith(self.key_prefix + "-")

    # -- public API ------------------------------------------------------

    def submit(self, text: str, kind: str = "user", display: str | None = None) -> dict:
        text = (text or "").strip()
        if not text:
            raise ValueError("empty message")
        item = {"id": uuid.uuid4().hex[:10], "text": text, "kind": kind,
                "queued": round(time.time(), 3)}
        if display:
            item["display"] = display
        with self._cond:
            state = self.store.state()
            queue = list(state.get("queue") or [])
            if state.get("paused") and kind == "user":
                # The owner is back after Stop: fold anything that arrived in
                # the meantime into this one turn instead of replaying it.
                held = [q["text"] for q in queue]
                if held:
                    item["text"] = (
                        "While Lyra was stopped, these reports arrived:\n\n"
                        + "\n\n---\n\n".join(held)
                        + "\n\n---\n\nThe owner's message:\n\n" + text
                    )
                    item["display"] = display or text
                queue = []
                self.store.update_state(paused=False)
                self.store.append_event("resumed")
            queue.append(item)
            changes: dict[str, Any] = {"queue": queue}
            if kind == "user":
                wd = dict(state.get("watchdog") or {})
                wd.update(no_progress=0, gave_up=False, last_mark=None)
                changes["watchdog"] = wd
            self.store.update_state(**changes)
            self.store.append_event("queued", item=item)
            self._cond.notify_all()
        return item

    def answer(self, item_id: str, value: Any) -> bool:
        with self._cond:
            waiter = self._waiters.pop(item_id, None)
        if waiter is None:
            self._close_inbox(item_id, "expired")
            return False
        shown = "(hidden)" if (self.store.inbox_item(item_id) or {}).get("kind") == "secret" else value
        self.store.close_inbox(item_id, "answered", answer=value)
        self.store.append_event("inbox_closed", id=item_id, status="answered", answer=shown)
        try:
            waiter(value)
        except Exception:
            logger.warning("lyra-lite: inbox answer handler failed", exc_info=True)
        return True

    def stop_turn(self, clear_queue: bool = True) -> None:
        with self._cond:
            changes: dict[str, Any] = {"paused": True}
            if clear_queue:
                changes["queue"] = []
            self.store.update_state(**changes)
            engine = self._engine
            busy = self._busy
        stopped = 0
        if engine is not None:
            if busy:
                engine.interrupt()
            stop_helpers = getattr(engine, "stop_helpers", None)
            if stop_helpers is not None:
                try:
                    stopped = int(stop_helpers() or 0)
                except Exception:
                    logger.warning("lyra-lite: stopping helpers failed", exc_info=True)
        self.store.append_event("stop_requested", cleared_queue=clear_queue, helpers_stopped=stopped)

    def new_chat(self) -> str:
        with self._cond:
            if self._busy:
                raise RuntimeError("Lyra is busy; stop the current turn first")
            if self.helpers():
                raise RuntimeError("Agents are still working; press Stop first")
            self._drop_engine()
            chat_id = self.store.archive_chat()
        self.store.append_event("chat_started", chat_id=chat_id)
        return chat_id

    def snapshot(self) -> dict:
        state = self.store.state()
        return {
            "root": str(self.root),
            "name": self.root.name,
            "running": bool(state.get("running")),
            "paused": bool(state.get("paused")),
            "keep_going": bool(state.get("keep_going", True)),
            "team": state.get("team") or [],
            "style": state.get("style") or "app-it",
            "profile": state.get("profile"),
            "models": state.get("models") or {},
            "watchdog": state.get("watchdog") or {},
            "has_engine": self._engine is not None,
            "rules_hash": state.get("rules_hash") or "",
            "queue": state.get("queue") or [],
            "turn": state.get("turn"),
            "turn_start_offset": int(state.get("turn_start_offset") or 0),
            "chat_id": state.get("chat_id"),
            "engine": effective_engine(state),
            "engine_override": bool(state.get("engine_override")),
            "claude": {k: v for k, v in (state.get("claude") or {}).items() if k != "auth_token"},
            "inbox": self.store.inbox(status="open"),
            "helpers": self.helpers(),
            "events_size": self.store.events_size(),
        }

    def helpers(self) -> list[dict]:
        engine = self._engine
        lister = getattr(engine, "helpers", None)
        if lister is None:
            return []
        try:
            return list(lister())
        except Exception:
            return []

    def shutdown(self) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify_all()
        self._drop_engine()

    def set_keep_going(self, on: bool) -> None:
        self.store.update_state(keep_going=bool(on))
        self.store.append_event("setting", name="keep_going", value=bool(on))

    def set_engine(self, name: str | None, claude: dict | None = None) -> None:
        """Pick this project's own engine, or None to follow Lyra's default."""
        with self._cond:
            if self._busy or self.helpers():
                raise RuntimeError("Lyra is busy; switch engines when it's idle")
            changes: dict[str, Any] = {"engine": name, "engine_override": name is not None}
            if claude is not None:
                # A blank token field means "keep the saved one".
                merged = {**(self.store.state().get("claude") or {}), **claude}
                changes["claude"] = {k: v for k, v in merged.items() if v != "" or k != "auth_token"}
            self.store.update_state(**changes)
            self._drop_engine()
        self.store.append_event("setting", name="engine", value=name or "default")

    def request_reload(self) -> None:
        """Lyra-wide settings changed: rebuild the engine before the next turn
        (a running turn finishes on the settings it started with)."""
        self._reload_pending = True

    def reload_engine(self) -> None:
        """Rebuild the engine (new rules) at the next turn; refuses while busy."""
        with self._cond:
            if self._busy or self.helpers():
                raise RuntimeError("Lyra is busy; try again when it's idle")
            self._drop_engine()
        self.store.append_event("rules_applied")

    def watchdog_tick(self, settings: dict | None = None, now: float | None = None) -> str:
        """Nudge an idle project with unfinished work. Returns the reason."""
        now = time.time() if now is None else now
        cfg = {**watchdog.DEFAULTS, **(settings or {})}
        with self._cond:
            state = self.store.state()
            wd = dict(state.get("watchdog") or {})
            if wd.get("day") != watchdog.today():
                wd.update(day=watchdog.today(), count=0)
            facts = watchdog.Facts(
                now=now,
                keep_going=bool(state.get("keep_going", True)),
                paused=bool(state.get("paused")),
                busy=self._busy,
                queued=len(state.get("queue") or []),
                helpers=len(self.helpers()),
                open_inbox=len(self.store.inbox(status="open")),
                ledger_running=any(p["state"] == "running" for p in read_map(self.root)["phases"]),
                last_reply=str(state.get("last_reply") or ""),
                last_turn_end=state.get("last_turn_end"),
                progress_mark="",
                nudges_today=int(wd.get("count") or 0),
                no_progress=int(wd.get("no_progress") or 0),
                last_mark=wd.get("last_mark"),
                gave_up=bool(wd.get("gave_up")),
            )
            go, reason = watchdog.decide(facts, cfg)
            if not go:
                return reason
            mark = watchdog.progress_mark(self.root)
            if facts.last_mark is not None and mark == facts.last_mark:
                wd["no_progress"] = facts.no_progress + 1
                if wd["no_progress"] >= cfg["max_no_progress"]:
                    wd["gave_up"] = True
                    self.store.update_state(watchdog=wd)
                    self.store.append_event(
                        "watchdog", action="gave_up",
                        text="Lyra stopped nudging itself: the last nudges made no progress.",
                    )
                    return "gave up: no progress"
            else:
                wd["no_progress"] = 0
            wd.update(count=int(wd.get("count") or 0) + 1, last_mark=mark, last=now)
            self.store.update_state(watchdog=wd)
            self.store.append_event("watchdog", action="nudge", reason=reason)
        self.submit(watchdog.NUDGE, kind="watchdog")
        return reason

    # -- inbox internals -------------------------------------------------

    def _open_inbox(self, kind: str, on_answer: Callable[[Any], None], **fields: Any) -> str:
        item = self.store.add_inbox(kind, **fields)
        with self._cond:
            self._waiters[item["id"]] = on_answer
        public = {k: v for k, v in item.items() if k != "answer"}
        self.store.append_event("inbox", item=public)
        return item["id"]

    def _close_inbox(self, item_id: str, status: str) -> None:
        with self._cond:
            self._waiters.pop(item_id, None)
        item = self.store.inbox_item(item_id)
        if item and item.get("status") == "open":
            self.store.close_inbox(item_id, status)
            self.store.append_event("inbox_closed", id=item_id, status=status)

    def _expire_turn_inbox(self, turn_id: str | None) -> None:
        for item in self.store.inbox(status="open"):
            if turn_id is None or item.get("turn") == turn_id:
                self._close_inbox(item["id"], "expired")

    # -- recovery --------------------------------------------------------

    def _rebuild_transcript(self) -> None:
        """Projects from before the transcript existed: rebuild it once from
        the activity log (current chat only), else from the saved messages."""
        events, _ = self.store.read_events(0)
        entries: list[dict] = []
        if events:
            starts: dict[str, dict] = {}
            for e in events:
                if e.get("type") == "chat_started":
                    entries, starts = [], {}
                elif e.get("type") == "turn_start":
                    starts[str(e.get("turn"))] = e
                elif e.get("type") == "turn_end" and str(e.get("turn")) in starts:
                    entries.append({"role": "user", "content": starts.pop(str(e.get("turn")))["text"]})
                    if e.get("reply"):
                        entries.append({"role": "assistant", "content": e["reply"]})
        else:
            entries = [
                {"role": m["role"], "content": m.get("content")}
                for m in self.store.messages()
                if m.get("role") in {"user", "assistant"} and m.get("content")
            ]
        self.store.write_transcript(entries)

    def _recover(self) -> None:
        """Make the files consistent after a crash or restart."""
        if not self.store.has_transcript():
            self._rebuild_transcript()
        state = self.store.state()
        self._expire_turn_inbox(None)
        turn = state.get("turn")
        if state.get("running") and isinstance(turn, dict):
            messages = self.store.messages()
            user_text = str(turn.get("text") or "")
            if messages and messages[-1].get("role") == "user":
                messages[-1] = {**messages[-1], "content": f"{messages[-1].get('content')}\n\n{user_text}"}
            else:
                messages.append({"role": "user", "content": user_text})
            messages.append({"role": "assistant", "content": RESTART_NOTE})
            self.store.save_messages(messages)
            self.store.append_transcript([{"role": "user", "content": user_text},
                                          {"role": "assistant", "content": RESTART_NOTE}])
            self.store.append_event("turn_end", turn=turn.get("id"), status="lost_on_restart",
                                    reply=RESTART_NOTE)
            checkpoint(self.root, role="lyra", status="interrupted",
                       exit_reason="restart", goal=user_text[:200])
        self.store.update_state(running=False, turn=None)

    # -- worker ----------------------------------------------------------

    def _drop_engine(self) -> None:
        engine, self._engine = self._engine, None
        self._engine_chat = None
        if engine is not None:
            try:
                engine.close()
            except Exception:
                pass

    def _engine_for_chat(self) -> Engine:
        chat_id = str(self.store.state().get("chat_id") or "")
        if self._engine is None or self._engine_chat != chat_id or self._reload_pending:
            self._reload_pending = False
            self._drop_engine()
            self._engine = self._engine_factory(self.store, self.session_key())
            self._engine_chat = chat_id
        return self._engine

    def _loop(self) -> None:
        while True:
            with self._cond:
                while not self._stop and (
                    self.store.state().get("paused") or not (self.store.state().get("queue") or [])
                ):
                    self._cond.wait(timeout=5)
                if self._stop:
                    return
                queue = list(self.store.state().get("queue") or [])
                item = queue.pop(0)
                turn = {"id": item["id"], "text": item["text"], "kind": item.get("kind", "user"),
                        "display": item.get("display"), "started": round(time.time(), 3)}
                offset = self.store.events_size()
                self.store.update_state(queue=queue, running=True, turn=turn,
                                        turn_start_offset=offset)
                self._busy = True
            try:
                self._run_turn(turn)
            except Exception:
                logger.exception("lyra-lite: turn crashed")
                self.store.append_event("turn_end", turn=turn["id"], status="crashed")
            finally:
                with self._cond:
                    self._busy = False
                    self.store.update_state(running=False, turn=None)

    def _run_turn(self, turn: dict) -> None:
        turn_id = turn["id"]
        self.store.append_event("turn_start", turn=turn_id, kind=turn["kind"], text=turn["text"],
                                display=turn.get("display"))
        hooks = self._hooks
        hooks.turn_id = turn_id
        engine = self._engine_for_chat()
        history = self.store.messages()
        try:
            result: TurnResult = engine.run_turn(turn["text"], history, hooks)
        finally:
            hooks.turn_id = None
        # The engine's working conversation is saved even when it shrank:
        # context compression replaces old turns with a summary on purpose.
        # The owner's full chat lives in the append-only transcript.
        entries = [{"role": "user", "content": turn["text"]}]
        if result.reply:
            entries.append({"role": "assistant", "content": result.reply})
        self.store.append_transcript(entries)
        if result.messages and not result.error:
            try:
                self.store.save_messages(result.messages)
            except Exception as exc:
                logger.exception("lyra-lite: could not save the conversation")
                self.store.append_event(
                    "problem", kind="save_failed",
                    text=f"This conversation could not be saved ({type(exc).__name__}: {exc}). "
                    "The project files are safe; check free disk space.",
                )
        self.store.update_state(last_turn_end=round(time.time(), 3),
                                last_reply=(result.reply or "")[-1000:])
        self._expire_turn_inbox(turn_id)
        status = "error" if result.error else "interrupted" if result.interrupted else (
            "done" if result.completed else "incomplete")
        sha = checkpoint(self.root, role="lyra", status=status,
                         exit_reason=status, goal=turn["text"][:200])
        self.store.append_event(
            "turn_end", turn=turn_id, status=status, reply=result.reply,
            error=result.error, usage=result.usage, checkpoint=sha,
        )
