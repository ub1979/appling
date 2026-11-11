"""Hermes as an Appling Lite engine.

Builds ``run_agent.AIAgent`` directly — no TUI, no PTY, no JSON-RPC — using
the same provider/model resolution as the Studio, so every linked
subscription (Codex, Ollama, Copilot, Claude, OpenRouter, custom endpoints)
keeps working unchanged.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from lyra_lite.engines.base import TurnHooks, TurnResult
from lyra_lite.settings import DEFAULT_EFFORT

logger = logging.getLogger(__name__)


def appling_reasoning(configured: dict | None) -> dict:
    """Hermes' saved effort (including "off"), else Appling's default — never
    each model's own default, which ranges from no thinking to medium."""
    return configured if configured is not None else {"enabled": True, "effort": DEFAULT_EFFORT}

# The platform tag shapes the system prompt ("graphical chat surface, markdown
# renders") and puts approvals on the gateway round-trip path.
PLATFORM = "desktop"
SHARED_MEMORY_TOOLSETS = {"memory", "session_search"}
CLARIFY_TIMEOUT_S = 30 * 60
_PREVIEW_CHARS = 600

# session_key -> engine, so process-global Hermes callbacks (secret capture)
# can find the engine whose turn is asking.
_ACTIVE: dict[str, "HermesEngine"] = {}
_ACTIVE_LOCK = threading.Lock()


def enable_gateway_approvals() -> None:
    """Route risky-command approvals to the owner's inbox, never auto-approve.

    Outside a recognised gateway/ask context Hermes treats a run as an
    unattended script and lets flagged commands through. Appling always has
    an owner to ask, so mark the whole process as an asking gateway; a turn
    whose context is somehow lost then gets "approval required", not a pass.
    """
    os.environ["HERMES_GATEWAY_SESSION"] = "1"
    os.environ["HERMES_EXEC_ASK"] = "1"


def _preview(value: Any, limit: int = _PREVIEW_CHARS) -> str:
    text = value if isinstance(value, str) else repr(value)
    try:
        from agent.redact import redact_sensitive_text

        text = redact_sensitive_text(text)
    except Exception:
        pass
    return text if len(text) <= limit else text[: limit - 1] + "…"


_COUNTERS = {
    "api_calls": "session_api_calls",
    "input": "session_input_tokens",          # fresh (uncached) input
    "cache_read": "session_cache_read_tokens",
    "cache_write": "session_cache_write_tokens",
    "output": "session_output_tokens",
    "reasoning": "session_reasoning_tokens",
}


def _counters(agent) -> dict:
    return {k: int(getattr(agent, attr, 0) or 0) for k, attr in _COUNTERS.items()}


def _helper_usage(kwargs: dict) -> dict:
    """Token use a finished helper reports (its input figure is the full prompt)."""
    prompt = int(kwargs.get("input_tokens") or 0)
    cache_read = int(kwargs.get("cache_read_tokens") or 0)
    cache_write = int(kwargs.get("cache_write_tokens") or 0)
    return {
        "api_calls": int(kwargs.get("api_calls") or 0),
        "input": max(0, prompt - cache_read - cache_write),
        "cache_read": cache_read,
        "cache_write": cache_write,
        "output": int(kwargs.get("output_tokens") or 0),
        "reasoning": int(kwargs.get("reasoning_tokens") or 0),
    }


def _helper_fields(kwargs: dict) -> dict:
    keep = (
        "goal", "task_count", "task_index", "subagent_id", "parent_id",
        "status", "duration_seconds", "model", "tool_count", "api_calls",
    )
    out = {k: kwargs[k] for k in keep if kwargs.get(k) not in (None, "")}
    if kwargs.get("summary"):
        out["summary"] = _preview(kwargs["summary"], 1200)
    return out


class HermesEngine:
    name = "hermes"

    def __init__(
        self,
        *,
        workspace: str,
        session_key: str,
        system_prompt: str = "",
        skills: list[str] | None = None,
        store=None,
    ):
        self.workspace = workspace
        self.session_key = session_key
        self.system_prompt = system_prompt
        self.skills = list(skills or [])
        self.store = store
        from lyra_lite.delegation import DelegationGuard

        self._delegations = DelegationGuard(session_key)
        self._agent = None
        self._hooks: TurnHooks | None = None
        self._lock = threading.Lock()

    # -- construction ----------------------------------------------------

    def _build_agent(self):
        import tui_gateway.server as gw
        from run_agent import AIAgent

        guard = self._delegations
        engine = self

        class ProjectAgent(AIAgent):
            def _dispatch_delegate_task(self, function_args: dict) -> str:
                if engine.store is None:
                    return guard.dispatch(function_args, super()._dispatch_delegate_task)
                from lyra_lite.delegation import dispatch_project_tasks

                return guard.dispatch(function_args, lambda args: dispatch_project_tasks(engine.store, self, args))

        cfg = gw._load_cfg()
        model, requested_provider = gw._resolve_startup_runtime()
        runtime = None
        if self.store is not None and not cfg.get("model") and not requested_provider and not (
            os.environ.get("HERMES_MODEL") or os.environ.get("HERMES_INFERENCE_MODEL")
        ):
            from lyra_lite.settings import CODEX_DEFAULT, model_runtime

            try:
                runtime = model_runtime(CODEX_DEFAULT)
                model = runtime["model"]
            except ValueError:
                pass
        if runtime is None:
            resolution = gw._resolve_runtime_with_fallback(
                {"requested": requested_provider, "target_model": model or None}
            )
            runtime = resolution.runtime
            if resolution.used_fallback and resolution.selected_model:
                model = resolution.selected_model

        prompt = self.system_prompt
        if self.skills:
            from agent.skill_commands import build_preloaded_skills_prompt

            skills_prompt, _loaded, missing = build_preloaded_skills_prompt(
                self.skills, task_id=self.session_key
            )
            if missing:
                logger.warning("lyra-lite: skills not found: %s", ", ".join(missing))
            prompt = "\n\n".join(p for p in (prompt, skills_prompt) if p)

        routing = gw._load_provider_routing()
        # Project memory replaces Hermes' shared memory here: Lyra Lite gets
        # project_recall instead, and never loads or writes the notes that
        # Hermes shares across every project (or searches other chats).
        from lyra_lite.recall_tool import TOOLSET, register, remember_workspace

        register()
        remember_workspace(self.session_key, self.workspace)
        toolsets = gw._load_enabled_toolsets()
        if toolsets is not None:
            toolsets = [t for t in toolsets if t not in SHARED_MEMORY_TOOLSETS] + [TOOLSET]
        agent = ProjectAgent(
            model=model,
            max_iterations=gw._cfg_max_turns(cfg, 90),
            provider=runtime.get("provider"),
            base_url=runtime.get("base_url"),
            api_key=runtime.get("api_key"),
            api_mode=runtime.get("api_mode"),
            acp_command=runtime.get("command"),
            acp_args=runtime.get("args"),
            credential_pool=runtime.get("credential_pool"),
            quiet_mode=True,
            verbose_logging=False,
            reasoning_config=appling_reasoning(gw._load_reasoning_config(str(model or ""))),
            service_tier=gw._load_service_tier(),
            enabled_toolsets=toolsets,
            skip_memory=True,
            providers_allowed=routing.get("only"),
            providers_ignored=routing.get("ignore"),
            providers_order=routing.get("order"),
            provider_sort=routing.get("sort"),
            provider_require_parameters=routing.get("require_parameters", False),
            provider_data_collection=routing.get("data_collection"),
            platform=PLATFORM,
            session_id=self.session_key,
            session_db=None,
            ephemeral_system_prompt=prompt or None,
            fallback_model=gw._load_fallback_model(),
            tool_start_callback=self._on_tool_start,
            tool_complete_callback=self._on_tool_complete,
            tool_progress_callback=self._on_progress,
            status_callback=self._on_status,
            clarify_callback=self._on_clarify,
        )
        agent.interim_assistant_callback = self._on_interim
        from lyra_lite.coordinator import make_coordinator

        make_coordinator(agent)
        return agent

    # -- callbacks (run on agent threads) --------------------------------

    def _emit(self, type_: str, **data: Any) -> None:
        hooks = self._hooks
        if hooks is not None:
            try:
                hooks.emit(type_, **data)
            except Exception:
                logger.debug("lyra-lite emit failed", exc_info=True)

    def _on_tool_start(self, tc_id, name, args) -> None:
        if self.store is not None and name == "skill_view":
            from lyra_lite.delegation import _object

            if str(_object(args).get("name") or "").split(":")[-1] == "req-engineer":
                self.store.update_state(requirements_review=True, requirements_started=True)
        self._emit("tool", phase="start", id=str(tc_id or ""), name=str(name),
                   args=_preview(args, 300))

    def _on_tool_complete(self, tc_id, name, args, result) -> None:
        self._emit("tool", phase="done", id=str(tc_id or ""), name=str(name),
                   result=_preview(result, 300))

    def _provider_status(self, text, *, subagent_id="main", goal="") -> None:
        from lyra_lite.delegation import _object

        status = _object(text)
        if not status.get("state"):
            return
        payload = {key: status.get(key) for key in (
            "state", "provider", "model", "reason", "retry_at", "attempt", "max_attempts"
        )}
        payload.update(id=subagent_id, goal=goal)
        if self.store is not None:
            with self.store._lock:
                if self.store.state().get("paused") and status["state"] != "recovered":
                    return
                statuses = dict(self.store.state().get("provider_statuses") or {})
                if status["state"] == "recovered":
                    if subagent_id not in statuses:
                        return
                    statuses.pop(subagent_id, None)
                else:
                    statuses[subagent_id] = payload
                self.store.update_state(provider_statuses=statuses)
        self._emit("provider_status", **payload)

    def _on_progress(self, event_type, name=None, preview=None, args=None, **kwargs) -> None:
        event_type = str(event_type or "")
        if not event_type.startswith("subagent.") or event_type == "subagent.text":
            return
        if event_type == "subagent.provider_status":
            self._provider_status(preview, subagent_id=str(kwargs.get("subagent_id") or "agent"),
                                  goal=str(kwargs.get("goal") or ""))
            return
        fields = _helper_fields(kwargs)
        if event_type == "subagent.start" and self.store is not None:
            # A replacement task supersedes a previous failure for the same goal.
            for old_id, old in list((self.store.state().get("provider_statuses") or {}).items()):
                if old.get("goal") == kwargs.get("goal"):
                    self._provider_status({"state": "recovered"}, subagent_id=old_id)
        if preview and event_type in {"subagent.tool", "subagent.start", "subagent.spawn_requested"}:
            fields["preview"] = _preview(preview, 200)
        if name and event_type == "subagent.tool":
            fields["tool"] = str(name)
        if event_type == "subagent.complete":
            fields["usage"] = _helper_usage(kwargs)
        self._emit("helper", event=event_type.removeprefix("subagent."), **fields)

    def _on_status(self, kind, text=None) -> None:
        if kind == "provider_status":
            self._provider_status(text)
            return
        self._emit("status", kind=str(kind), text=None if text is None else str(text))

    def _on_interim(self, text: str, *, already_streamed: bool = False) -> None:
        self._emit("interim", text=str(text), already_streamed=bool(already_streamed))

    def _on_clarify(self, question: str, choices) -> str:
        if self.store is not None:
            from lyra_lite import review

            state = self.store.state()
            root = self.store.root
            update = review.active_update(root, state) or {}
            if list(choices or []) == list(review.PROTOTYPE_CHOICES):
                revision = review.prototype_revision(root)
                if not revision or revision in (update.get("baseline_prototype_revision"),
                                                 state.get("prototype_needs_changes")):
                    return ("The prototype needs work before review. Create or revise prototypes/index.html "
                            "and its clickable flows, then call this checkpoint again.")
                self.store.update_state(requirements_review=True, requirements_started=True)
                return self._ask_blocking(
                    "prototype", question=str(question), choices=list(review.PROTOTYPE_CHOICES),
                    revision=revision, timeout=None,
                    on_timeout="Prototype review is still pending. Wait for the owner's decision.",
                )
            if list(choices or []) == list(review.REQUIREMENTS_CHOICES):
                revision = review.requirements_revision(root)
                if not revision or revision == update.get("baseline_requirements_revision"):
                    return "Write the new requirements draft before asking for approval."
                prototype = None
                if review.visual_project(root, state):
                    prototype = review.prototype_revision(root)
                    if not prototype or prototype != state.get("prototype_approved"):
                        return "The owner must open and approve the current clickable prototype first."
                self.store.update_state(requirements_review=True, requirements_started=True)
                return self._ask_blocking(
                    "requirements", question=str(question), choices=list(review.REQUIREMENTS_CHOICES),
                    revision=revision, prototype=prototype, timeout=None,
                    on_timeout="Requirements approval is still pending. Wait for the owner.",
                )
        return self._ask_blocking(
            "question",
            question=str(question),
            choices=list(choices or []),
            timeout=CLARIFY_TIMEOUT_S,
            on_timeout="The owner has not answered yet. Continue with safe defaults, "
            "or end your reply with the question so they can answer later.",
        )

    def _ask_blocking(self, kind: str, *, timeout: float | None, on_timeout: str, **fields) -> str:
        hooks = self._hooks
        if hooks is None:
            return on_timeout
        done = threading.Event()
        box: dict[str, Any] = {}

        def _answer(value: Any) -> None:
            box["value"] = value
            done.set()

        item_id = hooks.ask(kind, _answer, **fields)
        if not done.wait(timeout):
            hooks.expire(item_id)
            return on_timeout
        value = box.get("value")
        return "" if value is None else str(value)

    def _on_secret(self, env_var, prompt, metadata=None) -> dict:
        value = self._ask_blocking(
            "secret",
            env_var=str(env_var),
            question=str(prompt),
            timeout=CLARIFY_TIMEOUT_S,
            on_timeout="",
        )
        if not value:
            return {"success": True, "stored_as": env_var, "validated": False,
                    "skipped": True, "message": "skipped"}
        from hermes_cli.config import save_env_value_secure

        return {**save_env_value_secure(env_var, value), "skipped": False, "message": "ok"}

    def _on_approval(self, data: dict):
        """Open a card for this wait and return its completion cleanup."""
        hooks = self._hooks
        if hooks is None:
            return
        key = self.session_key
        request_id = data["request_id"]

        def _answer(choice: Any) -> None:
            from tools.approval import resolve_gateway_approval

            choice = str(choice or "deny")
            if choice not in {"once", "session", "always", "deny"}:
                choice = "deny"
            resolve_gateway_approval(key, choice, request_id=request_id)

        item_id = hooks.ask(
            "approval",
            _answer,
            command=str(data.get("command") or ""),
            description=str(data.get("description") or ""),
            choices=["once", "session", "always", "deny"],
        )
        return lambda: hooks.expire(item_id)

    # -- turn ------------------------------------------------------------

    def run_turn(self, text: str, history: list[dict], hooks: TurnHooks) -> TurnResult:
        from gateway.session_context import clear_session_vars, set_session_vars
        from tools.approval import (
            register_gateway_notify,
            reset_current_session_key,
            set_current_session_key,
        )
        from tools.skills_tool import set_secret_capture_callback
        from tools.terminal_tool import (
            register_task_env_overrides,
            set_sudo_password_callback,
        )

        enable_gateway_approvals()
        key = self.session_key
        self._hooks = hooks
        with _ACTIVE_LOCK:
            _ACTIVE[key] = self
        approval_token = set_current_session_key(key)
        session_tokens = set_session_vars(
            session_key=key,
            session_id=key,
            platform=PLATFORM,
            source=PLATFORM,
            cwd=self.workspace,
            ui_session_id=key,
        )
        try:
            register_task_env_overrides(key, {"cwd": self.workspace})
            register_gateway_notify(key, self._on_approval)
            set_sudo_password_callback(lambda: None)
            set_secret_capture_callback(_dispatch_secret)
            with self._lock:
                if self._agent is None:
                    self._agent = self._build_agent()
                agent = self._agent
            from lyra_lite.coordinator import withhold_shell

            withhold_shell(agent)  # no-op unless something rebuilt the tool list
            # A Stop pressed between turns must not cancel this new turn.
            try:
                agent.clear_interrupt()
            except Exception:
                pass

            def _stream(delta):
                if isinstance(delta, str) and delta:
                    hooks.emit("delta", text=delta)

            before = _counters(agent)

            self._delegations.restore(history)
            result = agent.run_conversation(
                text + self._delegations.reminder(),
                conversation_history=list(history),
                stream_callback=_stream,
                task_id=key,
            )
        except Exception as exc:
            logger.exception("lyra-lite: hermes turn failed")
            return TurnResult(reply="", messages=list(history), completed=False,
                              error=f"{type(exc).__name__}: {exc}")
        finally:
            # The approval route and self._hooks stay in place: background
            # helpers started this turn keep reporting and asking after it.
            try:
                clear_session_vars(session_tokens)
            except Exception:
                pass
            reset_current_session_key(approval_token)

        result = result if isinstance(result, dict) else {}
        messages = result.get("messages")
        after = _counters(agent)
        usage = {k: max(0, after[k] - before.get(k, 0)) for k in after}
        if not usage["api_calls"] and result.get("api_calls"):
            usage["api_calls"] = int(result["api_calls"])
        return TurnResult(
            reply=str(result.get("final_response") or ""),
            messages=messages if isinstance(messages, list) else list(history),
            completed=bool(result.get("completed", True)),
            interrupted=bool(result.get("interrupted", False)),
            error=str(result["error"]) if result.get("error") else None,
            usage=usage,
        )

    def interrupt(self) -> None:
        agent = self._agent
        if agent is not None:
            try:
                agent.interrupt()
            except Exception:
                logger.debug("lyra-lite interrupt failed", exc_info=True)

    def stop_helpers(self) -> int:
        from tools.async_delegation import interrupt_for_session

        return interrupt_for_session(session_key=self.session_key, reason="owner_stop")

    def helpers(self) -> list[dict]:
        """Background helpers this chat started that are still running."""
        from tools.async_delegation import list_async_delegations

        out = []
        for rec in list_async_delegations():
            if rec.get("session_key") != self.session_key or rec.get("status") != "running":
                continue
            out.append({
                "id": str(rec.get("delegation_id") or ""),
                "goal": _preview(rec.get("goal") or "", 300),
                "started": rec.get("dispatched_at"),
            })
        return out

    def close(self) -> None:
        self.interrupt()
        try:
            from tools.approval import unregister_gateway_notify

            unregister_gateway_notify(self.session_key)
        except Exception:
            pass
        with _ACTIVE_LOCK:
            if _ACTIVE.get(self.session_key) is self:
                _ACTIVE.pop(self.session_key, None)
        self._hooks = None
        agent, self._agent = self._agent, None
        if agent is not None:
            try:
                agent.close()
            except Exception:
                pass


def _dispatch_secret(env_var, prompt, metadata=None):
    from tools.approval import get_current_session_key

    key = get_current_session_key(default="")
    with _ACTIVE_LOCK:
        engine = _ACTIVE.get(key)
        if engine is None and len(_ACTIVE) == 1:
            engine = next(iter(_ACTIVE.values()))
    if engine is None:
        return {"success": False, "skipped": True, "message": "no active Appling turn"}
    return engine._on_secret(env_var, prompt, metadata)
