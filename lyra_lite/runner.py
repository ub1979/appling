"""One worker per project: runs queued turns in order and records them to files.

Messages, helper completions and (later) watchdog nudges all arrive the same
way — appended to the persisted queue in ``state.json`` — so anything can
drive Appling without touching a live connection.
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

from lyra_lite import agents, review, watchdog
from lyra_lite.engines.base import Engine, TurnResult
from lyra_lite.project_map import read_map
from lyra_lite.settings import effective_engine
from lyra_lite.store import ProjectStore, _atomic_write_text

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
RESTART_NOTE = (
    "(Appling was restarted before finishing this reply. Work done so far is in "
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
        event = self.runner.store.append_event(type_, turn=self.turn_id, **data)
        if type_ == "interim" and str(data.get("text") or "").strip():
            # Intermediate explanations are owner-facing conversation too.
            # Persist them independently of the engine's cached message history.
            self.runner.store.append_transcript([{
                "role": "assistant", "content": str(data["text"]), "kind": "interim",
                "turn": self.turn_id, "ts": event["ts"],
            }])

    def ask(self, kind: str, on_answer: Callable[[Any], None], **fields: Any) -> str:
        # Permission waits own their lifetime: a helper may ask during an
        # unrelated owner turn, or between turns entirely.
        turn = None if kind == "approval" else self.turn_id
        return self.runner._open_inbox(kind, on_answer, turn=turn, **fields)

    def expire(self, item_id: str) -> None:
        self.runner._close_inbox(item_id, "expired")



WEBSITE_FOCUS = (
    "Website rule: the template's live demo at .lyra/kit/reference/index.html (when present) "
    "is the approved look and motion — reuse its techniques. QA runs `node .lyra/kit/site-check.mjs "
    "dist --compare .lyra/kit/reference/index.html` and checks every contact sheet it names; "
    "no browser means BLOCKED, never APPROVED.")


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
        self._memory_lock = threading.Lock()  # one index refresh at a time
        self._hooks = _Hooks(self)
        self._reload_pending = False
        # Problems from before this start belong to an earlier run of Appling.
        self.started_at = round(time.time(), 3)
        self._recover()
        from lyra_lite.status_updates import StatusUpdates

        self._status_updates = StatusUpdates(self.store)
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
            if self._stop:
                raise ValueError("This project has been closed.")
            # The composer and a question card answer the same wait. Resolve
            # under the queue lock so clarify cannot open between this check
            # and enqueueing the message.
            targets = [i for i in self.store.inbox(status="open")
                       if i["id"] in self._waiters
                       and i.get("kind") in {"question", "prototype", "requirements", "plan"}]
            target = targets[0] if (kind == "user" and len(targets) == 1
                                   and not self.store.state().get("paused")) else None
            if target is not None:
                value = text if target["kind"] == "question" else {"choice": "Request changes", "feedback": text}
                if self.answer(target["id"], value):
                    return {**item, "answered": target["id"]}
            state = self.store.state()
            queue = list(state.get("queue") or [])
            if state.get("paused") and kind == "user":
                # The owner is back after Stop: fold anything that arrived in
                # the meantime into this one turn instead of replaying it.
                held = [q["text"] for q in queue]
                if held:
                    item["text"] = (
                        "While Appling was stopped, these reports arrived:\n\n"
                        + "\n\n---\n\n".join(held)
                        + "\n\n---\n\nThe owner's message:\n\n" + text
                    )
                    item["display"] = display or text
                queue = []
                self.store.update_state(paused=False)
                self.store.append_event("resumed")
            queue.append(item)
            changes: dict[str, Any] = {"queue": queue}
            if kind == "approval_continue":
                # Persist the queued handoff and its consumed flag together.
                changes["approval_followup"] = None
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
            waiter = self._waiters.get(item_id)
            if waiter is not None:
                item = self.store.inbox_item(item_id) or {}
                kind = item.get("kind")
                state = self.store.state()
                feedback = value.get("feedback") if isinstance(value, dict) else None
                if feedback is not None and not isinstance(feedback, str):
                    raise ValueError("Feedback must be text.")
                if kind == "prototype":
                    choice = value.get("choice") if isinstance(value, dict) else value
                    if choice not in review.PROTOTYPE_CHOICES:
                        raise ValueError("Choose an answer from the prototype review.")
                    if choice == review.PROTOTYPE_CHOICES[0]:
                        revision = value.get("revision") if isinstance(value, dict) else None
                        if not revision or revision != item.get("revision") or revision != review.prototype_revision(self.root):
                            raise ValueError("Open the current prototype before approving it.")
                        self.store.update_state(prototype_approved=revision, prototype_needs_changes=None)
                    else:
                        self.store.update_state(prototype_approved=None, prototype_needs_changes=item.get("revision"))
                    value = choice
                elif kind == "plan":
                    choice = value.get("choice") if isinstance(value, dict) else value
                    if choice not in review.PLAN_CHOICES:
                        raise ValueError("Choose an answer from the implementation plan review.")
                    plan = review.implementation_plan(self.root)
                    if choice == review.PLAN_CHOICES[0]:
                        revision = value.get("revision") if isinstance(value, dict) else None
                        if not plan or revision != item.get("revision") or revision != plan["revision"]:
                            raise ValueError("Review the current implementation plan before approving it.")
                        requirements = review.requirements_revision(self.root)
                        if (requirements != item.get("requirements") or requirements != state.get("requirements_approved")
                                or state.get("requirements_review")):
                            raise ValueError("The requirements changed. Review the plan against the current approved requirements.")
                        if review.visual_project(self.root, state) and review.prototype_revision(self.root) != state.get("prototype_approved"):
                            raise ValueError("Review the current prototype before approving the implementation plan.")
                        self.store.update_state(plan_approved=revision, plan_needs_changes=None,
                                                plan_requirements=requirements, plan_execution=None,
                                                approval_followup={"revision": requirements, "offset": self.store.events_size(), "after": "plan"})
                    else:
                        self.store.update_state(plan_approved=None, plan_needs_changes=item.get("revision"))
                    value = choice
                elif kind == "requirements":
                    choice = value.get("choice") if isinstance(value, dict) else value
                    if choice not in review.REQUIREMENTS_CHOICES:
                        raise ValueError("Choose an answer from the requirements review.")
                    if choice == review.REQUIREMENTS_CHOICES[0]:
                        revision = review.requirements_revision(self.root)
                        if not revision or revision != item.get("revision"):
                            raise ValueError("The requirements changed. Ask Appling to share the revised draft.")
                        if item.get("prototype") and (item["prototype"] != state.get("prototype_approved")
                                                      or item["prototype"] != review.prototype_revision(self.root)):
                            raise ValueError("Review the current prototype before approving the requirements.")
                        self.store.update_state(requirements_approved=revision, requirements_review=False,
                                                requirements_revision_format=2,
                                                approval_followup={"revision": revision,
                                                                   "offset": self.store.events_size()})
                    else:
                        self.store.update_state(requirements_approved=None)
                    value = choice
                if kind in {"prototype", "requirements", "plan"} and value == "Request changes" and feedback:
                    value += "\n\nOwner feedback:\n" + feedback.strip()
                self._waiters.pop(item_id)
                shown = "(hidden)" if kind == "secret" else value
                self.store.close_inbox(item_id, "answered", answer=value)
                self.store.append_event("inbox_closed", id=item_id, status="answered", answer=shown)
        if waiter is None:
            self._close_inbox(item_id, "expired")
            return False
        try:
            waiter(value)
        except Exception:
            logger.warning("lyra-lite: inbox answer handler failed", exc_info=True)
        return True

    def stop_turn(self, clear_queue: bool = True) -> None:
        with self._cond:
            if self._stop:
                return
            changes: dict[str, Any] = {"paused": True, "provider_statuses": {}, "approval_followup": None}
            if clear_queue:
                changes["queue"] = []
            self.store.update_state(**changes)
            engine = self._engine
            busy = self._busy
        self._expire_turn_inbox(None)
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
            if self._stop:
                raise RuntimeError("This project has been closed.")
            if self._busy:
                raise RuntimeError("Appling is busy; stop the current turn first")
            if self.helpers():
                raise RuntimeError("Agents are still working; press Stop first")
            self._drop_engine()
            chat_id = self.store.archive_chat()
            self.store.update_state(focus_hash=None, focus_turns=0, provider_statuses={}, approval_followup=None)
        self.store.append_event("chat_started", chat_id=chat_id)
        return chat_id

    def recoverable_review(self) -> dict | None:
        """The most recent expired review, only while its exact draft is current."""
        state = self.store.state()
        if not state.get("requirements_review") and not state.get("plan_review_required"):
            return None
        cards = self._chat_reviews()
        if not cards:
            return None
        if any(i.get("status") == "open" for i in cards):
            return None
        item = max(cards, key=lambda i: i.get("created", 0))
        kind, revision = item["kind"], item.get("revision")
        if item.get("status") != "expired" or not revision:
            return None
        update = review.active_update(self.root, state) or {}
        if kind == "prototype":
            if (revision != review.prototype_revision(self.root)
                    or revision in (state.get("prototype_approved"), state.get("prototype_needs_changes"),
                                    update.get("baseline_prototype_revision"))):
                return None
        elif kind == "plan":
            if review.plan_execution_started(state):
                return None
            plan = review.implementation_plan(self.root)
            if (not plan or revision != plan["revision"]
                    or revision in (state.get("plan_approved"), state.get("plan_needs_changes"))
                    or item.get("requirements") != state.get("requirements_approved")
                    or review.requirements_revision(self.root) != state.get("requirements_approved")):
                return None
        else:
            if (revision != review.requirements_revision(self.root)
                    or revision in (state.get("requirements_approved"), update.get("baseline_requirements_revision"))):
                return None
            if review.visual_project(self.root, state):
                prototype = review.prototype_revision(self.root)
                if not prototype or prototype != state.get("prototype_approved") or prototype != item.get("prototype"):
                    return None
        return item

    def _chat_reviews(self) -> list[dict]:
        state = self.store.state()
        return [i for i in self.store.inbox() if i.get("kind") in {"prototype", "requirements", "plan"}
                and (i.get("chat_id") == state.get("chat_id") if i.get("chat_id")
                     else not state.get("chat_started_at") or i.get("created", 0) > state["chat_started_at"])]

    def reopen_review(self, item_id: str) -> str:
        """Restore review controls without asking a model to recreate them."""
        with self._cond:
            if self._stop or self._busy or self.helpers() or self.store.state().get("queue"):
                raise RuntimeError("Finish or stop the current work before reopening the review.")
            item = self.recoverable_review()
            if item is None or item["id"] != item_id:
                raise RuntimeError("This review is no longer current. Ask Appling to share the latest draft.")
            self.store.update_state(paused=False)
            fields = {k: item[k] for k in ("question", "choices", "revision", "prototype", "requirements", "path") if k in item}
            if item["kind"] == "requirements":
                draft = (self.root / "requirements.md").read_text(encoding="utf-8")
                if draft not in fields.get("question", ""):
                    fields["question"] = fields.get("question", "Review these requirements.") + "\n\n---\n\n" + draft
            return self._open_review_decision(item["kind"], **fields)

    def _open_review_decision(self, kind: str, **fields) -> str:
        def resume(value):
            if value is not None:
                self.submit(f"Owner's {kind} review decision:\n\n{value}")

        return self._open_inbox(kind, resume, turn=None, **fields)

    def _offer_requirements_review(self) -> None:
        """Do not leave an approved prototype stranded without its next action."""
        with self._cond:
            state = self.store.state()
            if (self._stop or self._busy or state.get("paused") or state.get("queue")
                    or not state.get("requirements_review") or self.helpers()
                    or self.store.inbox(status="open")):
                return
            prototype = review.prototype_revision(self.root)
            if not prototype or prototype != state.get("prototype_approved"):
                return
            revision = review.requirements_revision(self.root)
            update = review.active_update(self.root, state) or {}
            if (not revision or revision in (state.get("requirements_approved"),
                                            update.get("baseline_requirements_revision"))):
                return
            # Keep existing reviews and requests for changes authoritative.
            # Expired current cards already have the explicit recovery action.
            if any(i.get("kind") == "requirements" and i.get("revision") == revision for i in self._chat_reviews()):
                return
            try:
                draft = (self.root / "requirements.md").read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                return
            self._open_review_decision(
                "requirements", revision=revision, prototype=prototype,
                choices=list(review.REQUIREMENTS_CHOICES),
                question=("Your prototype is approved. Review the requirements below, then choose "
                          "Approve requirements or Request changes. Planning and development wait "
                          "for your separate requirements approval.\n\n---\n\n" + draft),
            )

    def _approval_progress(self, offset: int) -> bool:
        events, _ = self.store.read_events(offset)
        return any(e["type"] == "helper" and e.get("event") == "start" for e in events)

    def _offer_plan_review(self) -> None:
        with self._cond:
            state = self.store.state()
            if (self._stop or self._busy or state.get("paused") or state.get("queue") or self.helpers()
                    or self.store.inbox(status="open") or not state.get("plan_review_required")
                    or state.get("requirements_review")):
                return
            if review.plan_execution_started(state):
                return
            requirements = review.requirements_revision(self.root)
            if not requirements or requirements != state.get("requirements_approved"):
                return
            if review.visual_project(self.root, state) and review.prototype_revision(self.root) != state.get("prototype_approved"):
                return
            plan = review.implementation_plan(self.root)
            if (not plan or plan["revision"] in (state.get("plan_approved"), state.get("plan_needs_changes"))
                    or any(i.get("kind") == "plan" and i.get("revision") == plan["revision"]
                           and i.get("requirements") == requirements for i in self._chat_reviews())):
                return
            self._open_review_decision(
                "plan", choices=list(review.PLAN_CHOICES), revision=plan["revision"], requirements=requirements,
                path=plan["path"], question="Review this implementation plan before development starts.\n\n" + plan["text"],
            )

    def _continue_approved_work(self, turn: dict) -> None:
        """One bounded handoff when the model acknowledges approval then stops."""
        with self._cond:
            state = self.store.state()
            if self._stop or state.get("paused"):
                return
            pending = state.get("approval_followup")
            if not pending:
                if (turn.get("kind") == "approval_continue" and not self.helpers()
                        and not self.store.inbox(status="open") and not state.get("queue")
                        and not self._approval_progress(state.get("turn_start_offset", 0))):
                    self.store.append_event(
                        "problem", kind="workflow_stalled",
                        text="The AI ended its reply without starting the next step. No work is running. "
                             "Send ‘Continue to planning’ to retry, or change the AI in Settings.",
                    )
                return
            revision = review.requirements_revision(self.root)
            if (pending["revision"] != state.get("requirements_approved")
                    or pending["revision"] != revision or self._approval_progress(pending["offset"])):
                self.store.update_state(approval_followup=None)
                return
            if self.helpers() or self.store.inbox(status="open") or state.get("queue"):
                return
            if review.visual_project(self.root, state):
                prototype = review.prototype_revision(self.root)
                if not prototype or prototype != state.get("prototype_approved"):
                    self.store.update_state(approval_followup=None)
                    return
            update = review.active_update(self.root, state)
            needs_change_review = update and not review.change_review_ready(review.change_report(self.root, update, revision))
            step = "Change Management review before planning" if needs_change_review else "task planning"
            if pending.get("after") == "plan":
                plan = review.implementation_plan(self.root)
                if not plan or plan["revision"] != state.get("plan_approved"):
                    self.store.update_state(approval_followup=None)
                    return
                step = "the development agent's first approved implementation task"
            self.submit(
                f"{agents.APPROVAL_CONTINUE}\nThe owner has approved the current requirements and any required "
                f"prototype. Continue the authorized workflow now with {step}. Read requirements.md and the "
                "Project Brain, then use delegate_task to start the next permitted agent task. Include unresolved "
                "technical compatibility checks in that task. Do not end with only an approval acknowledgement "
                "or a statement that work is next. If genuinely blocked, use clarify to ask the specific question. "
                "Respect the selected team and all subsequent review gates. Do not redo completed approvals.",
                kind="approval_continue", display=f"Requirements approved — continuing with {step}.",
            )

    def start_update(self, branch: str | None) -> dict:
        from lyra_lite.templates import get_template

        with self._cond:
            if self._stop:
                raise RuntimeError("This project has been closed.")
            state = self.store.state()
            ledger = read_map(self.root)
            if review.active_update(self.root, state, ledger):
                raise RuntimeError("An update is already in progress.")
            if not review.built_project(self.root, ledger):
                raise RuntimeError("This project has no completed build to update yet.")
            if self._busy or self.helpers() or state.get("queue"):
                raise RuntimeError("Wait for Appling and its agents to finish, or press Stop and retry.")
            revision = review.next_revision(ledger, state)
            baseline_dir = self.store.dir / "updates" / f"v{revision}"
            baseline_requirements = None
            try:
                original = (self.root / "requirements.md").read_text(encoding="utf-8")
            except FileNotFoundError:
                pass
            else:
                baseline_requirements = (baseline_dir / "requirements.md").relative_to(self.root).as_posix()
                _atomic_write_text(self.root / baseline_requirements, original)
            update = {
                "revision": revision,
                "branch": branch,
                "baseline_requirements": baseline_requirements,
                "baseline_requirements_revision": review.requirements_revision(self.root),
                "baseline_prototype_revision": review.prototype_revision(self.root),
            }
            if branch is not None:
                review.create_update_branch(self.root, branch)
            chat_id = self.new_chat()
            team = agents.normalise_team([*(state.get("team") or []), "change-manager"])
            template = get_template(state["template"]) if state.get("template") else None
            self.store.update_state(update=update, team=team, paused=False, watchdog={},
                                    requirements_review=True, requirements_approved=None,
                                    prototype_approved=None, prototype_needs_changes=None,
                                    plan_execution=None, plan_approved=None, plan_requirements=None,
                                    plan_needs_changes=None, plan_review_required=False,
                                    turn_start_offset=self.store.events_size())
            self.submit(agents.setup_message(self.root, team, state.get("models"), "",
                                             state.get("profile"), state.get("project_kind"), template,
                                             state.get("platforms"), update=update),
                        kind="setup", display=f"Started version {revision} requirements")
            return {"chat_id": chat_id, "update": update}

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
            "project_kind": state.get("project_kind"),
            "template": state.get("template"),
            "models": state.get("models") or {},
            "watchdog": state.get("watchdog") or {},
            "has_engine": self._engine is not None,
            "rules_hash": state.get("rules_hash") or "",
            "queue": state.get("queue") or [],
            "turn": state.get("turn"),
            "turn_start_offset": int(state.get("turn_start_offset") or 0),
            "chat_id": state.get("chat_id"),
            "engine": effective_engine(state),
            "engine_locked": bool(state.get("engine_locked")),
            "engine_override": bool(state.get("engine_override")),
            "inbox": self.store.inbox(status="open"),
            "helpers": self.helpers(),
            "events_size": self.store.events_size(),
            "started_at": self.started_at,
            "last_completed_turn": state.get("last_completed_turn"),
            "provider_statuses": state.get("provider_statuses") or {},
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

    def close_for_archive(self) -> None:
        with self._cond:
            if self._busy or self.helpers():
                raise RuntimeError("Stop Appling and its agents before deleting this project.")
            self.store.update_state(paused=True)
            self._stop = True
            self._cond.notify_all()
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            raise RuntimeError("Appling is still finishing this project. Try again shortly.")
        self._drop_engine()
        with self._memory_lock:
            pass  # Wait for any project index write before moving the folder.

    def set_keep_going(self, on: bool) -> None:
        with self._cond:
            if self._stop:
                return
            self.store.update_state(keep_going=bool(on))
            self.store.append_event("setting", name="keep_going", value=bool(on))

    def request_reload(self) -> None:
        """Appling-wide settings changed: rebuild the engine before the next turn
        (a running turn finishes on the settings it started with)."""
        self._reload_pending = True

    def reload_engine(self) -> None:
        """Rebuild the engine (new rules) at the next turn; refuses while busy."""
        with self._cond:
            if self._stop:
                raise RuntimeError("This project has been closed.")
            if self._busy or self.helpers():
                raise RuntimeError("Appling is busy; try again when it's idle")
            self._drop_engine()
        self.store.append_event("rules_applied")

    def status_tick(self, settings: dict | None = None, now: float | None = None) -> str | None:
        # Coordinate with Stop/new-chat so an old note cannot land in a new chat.
        with self._cond:
            if self._stop:
                return None
            return self._status_updates.tick(self.snapshot(), settings, now)

    def watchdog_tick(self, settings: dict | None = None, now: float | None = None) -> str:
        """Nudge an idle project with unfinished work. Returns the reason."""
        now = time.time() if now is None else now
        cfg = {**watchdog.DEFAULTS, **(settings or {})}
        with self._cond:
            if self._stop:
                return "project closed"
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
                        text="Appling stopped nudging itself: the last nudges made no progress.",
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
        with self._cond:
            item = self.store.add_inbox(kind, **fields)
            self._waiters[item["id"]] = on_answer
            public = {k: v for k, v in item.items() if k != "answer"}
            self.store.append_event("inbox", item=public)
            stopped = self._stop or self.store.state().get("paused")
        if stopped:
            self._close_inbox(item["id"], "expired")
        elif kind == "question":
            # A message can arrive just before clarify opens its card (for
            # example while leaving prototype review). Deliver it as the
            # answer instead of trapping it behind the turn that needs it.
            with self._cond:
                state = self.store.state()
                queue = state.get("queue") or []
                turn = state.get("turn") or {}
                pending = [q for q in queue if q.get("kind") == "user"
                           and q.get("queued", 0) >= turn.get("started", 0)]
                if (pending and not self._stop and not state.get("paused")
                        and item["id"] in self._waiters
                        and sum(i.get("kind") in {"question", "prototype", "requirements"}
                                for i in self.store.inbox(status="open")) == 1):
                    answer = "\n\n".join(q["text"] for q in pending)
                    if self.answer(item["id"], answer):
                        consumed = {q["id"] for q in pending}
                        self.store.update_state(queue=[q for q in queue if q["id"] not in consumed])
                        self.store.append_event("queue_consumed", ids=sorted(consumed), inbox=item["id"])
        return item["id"]

    def _close_inbox(self, item_id: str, status: str) -> None:
        with self._cond:
            waiter = self._waiters.pop(item_id, None)
            item = self.store.inbox_item(item_id)
            if item and item.get("status") == "open":
                self.store.close_inbox(item_id, status)
                self.store.append_event("inbox_closed", id=item_id, status=status)
        if waiter is not None:
            try:
                waiter("deny" if item and item.get("kind") == "approval" else None)
            except Exception:
                logger.warning("lyra-lite: inbox expiry handler failed", exc_info=True)

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
                    start = starts.pop(str(e.get("turn")))
                    entries.append({"role": "user", "content": start["text"], "ts": start.get("ts")})
                    if e.get("reply"):
                        entries.append({"role": "assistant", "content": e["reply"], "ts": e.get("ts")})
        else:
            entries = [
                {"role": m["role"], "content": m.get("content")}
                for m in self.store.messages()
                if m.get("role") in {"user", "assistant"} and m.get("content")
            ]
        self.store.write_transcript(entries)

    def _recover(self) -> None:
        """Make the files consistent after a crash or restart."""
        review.reconcile_requirements_approval(self.store)
        review.reconcile_plan_execution(self.store)
        if not self.store.has_transcript():
            self._rebuild_transcript()
        state = self.store.state()
        if any(i.get("kind") == "question" and i.get("status") in {"open", "expired"}
               and review.requests_plan_approval(i.get("question", ""), i.get("choices"))
               and (i.get("chat_id") == state.get("chat_id") if i.get("chat_id")
                    else i.get("created", 0) > (state.get("chat_started_at") or 0))
               for i in self.store.inbox()):
            self.store.update_state(plan_review_required=True)
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
            recovered_at = round(time.time(), 3)
            self.store.record_turn_start(turn)
            self.store.append_transcript([
                {"role": "assistant", "content": RESTART_NOTE, "ts": recovered_at},
            ])
            self.store.append_event("turn_end", turn=turn.get("id"), status="lost_on_restart",
                                    reply=RESTART_NOTE)
            checkpoint(self.root, role="lyra", status="interrupted",
                       exit_reason="restart", goal=user_text[:200])
        self.store.update_state(running=False, turn=None)
        self._offer_requirements_review()
        self._offer_plan_review()

    # -- worker ----------------------------------------------------------

    def _drop_engine(self) -> None:
        self._expire_turn_inbox(None)
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
                    self._busy or self.store.state().get("paused")
                    or not (self.store.state().get("queue") or [])
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
                # _finish_turn is the one place that releases busy; a crash
                # never got there. Release only if no other turn took over.
                with self._cond:
                    if (self.store.state().get("turn") or {}).get("id") == turn["id"]:
                        self._busy = False
                        self.store.update_state(running=False, turn=None)
                        self._cond.notify_all()
                self.store.append_event("turn_end", turn=turn["id"], status="crashed")

    def _run_turn(self, turn: dict) -> None:
        turn_id = turn["id"]
        self.store.append_event("turn_start", turn=turn_id, kind=turn["kind"], text=turn["text"],
                                display=turn.get("display"))
        self.store.record_turn_start(turn)
        hooks = self._hooks
        hooks.turn_id = turn_id
        state = self.store.state()
        if state.get("project_kind") in ("website", "slides", "video"):
            try:
                from lyra_lite.templates import ensure_website_kit

                ensure_website_kit(self.root, state.get("template"))
            except Exception:
                logger.warning("lyra-lite: website kit copy failed", exc_info=True)
        engine = self._engine_for_chat()
        history = self.store.messages()
        engine_text = turn["text"] + self._focus_for(turn["kind"])
        try:
            result: TurnResult = engine.run_turn(engine_text, history, hooks)
        finally:
            hooks.turn_id = None
        self._finish_turn(turn, result)

    def _finish_turn(self, turn: dict, result: TurnResult) -> None:
        turn_id = turn["id"]
        # The engine's working conversation is saved even when it shrank:
        # context compression replaces old turns with a summary on purpose.
        # The owner's full chat lives in the append-only transcript.
        now = round(time.time(), 3)
        self.store.record_turn_start(turn)
        entries = []
        if result.reply:
            entries.append({"role": "assistant", "content": result.reply, "ts": now})
        self.store.append_transcript(entries)
        # Hermes can fail after a tool has already started a background job.
        # Its returned conversation includes that dispatch and must survive
        # the error so the next turn can continue it.
        keep_hermes_progress = getattr(self._engine, "name", None) == "hermes"
        if result.messages and (not result.error or keep_hermes_progress):
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
        # Idle before announcing the end, so anyone reacting to turn_end
        # (the screen, a watchdog, a test) sees a finished project.
        with self._cond:
            self._busy = False
            self.store.update_state(running=False, turn=None, last_completed_turn=turn_id)
            if not result.error and not result.interrupted and result.completed:
                self._offer_requirements_review()
                self._offer_plan_review()
                self._continue_approved_work(turn)
            self._cond.notify_all()
        self.store.append_event(
            "turn_end", turn=turn_id, status=status, reply=result.reply,
            error=result.error, usage=result.usage, checkpoint=sha,
        )
        threading.Thread(target=self._refresh_memory, name="lyra-memory-index", daemon=True).start()

    def _refresh_memory(self) -> None:
        try:
            from lyra_lite.memory import ProjectMemory

            with self._memory_lock:
                if not self._stop:
                    ProjectMemory(self.root).refresh()
        except Exception:
            logger.warning("lyra-lite: project memory index failed", exc_info=True)

    FOCUS_REMIND_EVERY = 8

    def _focus_for(self, kind: str) -> str:
        """The project-focus note, sent when the state changed or as a periodic reminder."""
        if kind in {"setup", "team"}:
            return ""
        try:
            import hashlib

            from lyra_lite.focus import focus_note

            update = review.active_update(self.root, self.store.state()) or {}
            note = focus_note(self.root, open_inbox=len(self.store.inbox(status="open")),
                              update_revision=update.get("revision"))
        except Exception:
            logger.debug("focus note failed", exc_info=True)
            return ""
        state = self.store.state()
        if state.get("project_kind") == "website":
            note = (note or "[Project focus]") + "\n" + WEBSITE_FOCUS
        if not note:
            return ""
        digest = hashlib.sha1(note.encode("utf-8")).hexdigest()[:12]
        since = int(state.get("focus_turns") or 0)
        if digest == state.get("focus_hash") and since < self.FOCUS_REMIND_EVERY:
            self.store.update_state(focus_turns=since + 1)
            return ""
        self.store.update_state(focus_hash=digest, focus_turns=0)
        return "\n\n" + note
