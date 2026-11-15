"""Codex-only Appling settings. Credentials remain owned by Codex CLI."""
from __future__ import annotations

import threading
import time
from typing import Any

from lyra_lite.config import load_config, save_config

ENGINES = ("codex",)
EFFORTS = ("low", "medium", "high", "xhigh")
DEFAULT_EFFORT = "medium"
ABOUT_ME_LIMIT = 2000
CODEX_DEFAULT = {"provider": "codex", "model": "gpt-6.1-sol"}
_lock = threading.RLock()
_catalog = None
_catalog_at = 0


def _section() -> dict:
    return load_config()


def save_section(changes: dict) -> None:
    save_config(changes)


def default_engine() -> str:
    return "codex"


def effective_engine(state: dict) -> str:
    return "codex"


def migrate_engine_settings() -> None:
    # No reads or writes to ~/.hermes. Opening an old project is a separate,
    # paused, backed-up ProjectStore migration.
    pass


def about_me() -> str:
    return str(_section().get("about_me") or "").strip()[:ABOUT_ME_LIMIT]


def codex_model() -> dict:
    return {"provider": "codex", "model": str(_section().get("model") or CODEX_DEFAULT["model"])}


def codex_effort() -> dict:
    effort = str(_section().get("effort") or "")
    return {"effort": effort, "effective": effort or DEFAULT_EFFORT, "overridden": False}


def _selection(value: Any) -> dict:
    if not isinstance(value, dict) or value.get("provider") != "codex":
        raise ValueError("Choose a Codex model.")
    model = str(value.get("model") or "").strip()
    effort = str(value.get("effort") or "").strip()
    if not model or len(model) > 200 or any(c.isspace() for c in model):
        raise ValueError("Choose a valid Codex model ID.")
    if effort not in ("", *EFFORTS):
        raise ValueError("Choose a supported Codex effort.")
    return {"provider": "codex", "model": model, "effort": effort}


def set_codex_model(provider: str, model: str, confirm: bool = False) -> dict:
    value = _selection({"provider": provider, "model": model})
    save_config({"model": value["model"]})
    return {"ok": True, **codex_model()}


def set_codex_effort(effort: str) -> dict:
    _selection({**codex_model(), "effort": effort})
    save_config({"effort": effort})
    return codex_effort()


def model_options(refresh: bool = False) -> dict:
    global _catalog, _catalog_at
    from lyra_lite.engines.codex_rpc import CodexRPC
    from lyra_lite.config import app_home

    with _lock:
        if not refresh and _catalog is not None and time.monotonic() - _catalog_at < 120:
            return {**_catalog, **codex_model()}
        home = app_home()
        home.mkdir(parents=True, exist_ok=True, mode=0o700)
        rpc = CodexRPC(cwd=str(home))
        try:
            account = rpc.request("account/read", {})
            models, cursor = [], None
            while True:
                page = rpc.request("model/list", {"limit": 100, **({"cursor": cursor} if cursor else {})})
                models.extend(str(m.get("model") or m.get("id")) for m in page.get("data", []) if m.get("model") or m.get("id"))
                cursor = page.get("nextCursor")
                if not cursor:
                    break
            _catalog = {"providers": [{"slug": "codex", "name": "Codex", "models": list(dict.fromkeys(models)), "current": True}],
                        "authenticated": bool(account.get("account"))}
            _catalog_at = time.monotonic()
            return {**_catalog, **codex_model()}
        finally:
            rpc.close()


def agent_model_overrides() -> dict:
    choices = _section().get("agent_models")
    return choices if isinstance(choices, dict) else {}


def agent_model_settings() -> list[dict]:
    from lyra_lite.agents import AGENTS
    saved = agent_model_overrides()
    return [{"id": i, "label": label, "default": None, "selection": saved.get(i)} for i, label, _ in AGENTS if i != "req-engineer"]


def save_agent_model(agent_id: str, selection: Any) -> None:
    from lyra_lite.agents import LABELS
    if agent_id not in LABELS:
        raise ValueError("Unknown agent.")
    value = _selection(selection) if selection is not None else None
    with _lock:
        choices = dict(agent_model_overrides())
        if value is None:
            choices.pop(agent_id, None)
        else:
            choices[agent_id] = value
        save_config({"agent_models": choices})


def resolve_agent_model(agent_id: str | None, preferences: dict, legacy: dict) -> dict:
    value = preferences.get(agent_id) or codex_model()
    return {**_selection(value), "effort": value.get("effort") or codex_effort()["effective"]}
