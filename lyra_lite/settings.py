"""Appling settings for Hermes models, effort and owner preferences."""

from __future__ import annotations

from threading import Lock
from typing import Any

ENGINES = ("hermes",)


def _section() -> dict:
    from hermes_cli.config import load_config

    section = (load_config() or {}).get("lyra_lite") or {}
    return section if isinstance(section, dict) else {}


def save_section(changes: dict) -> None:
    from hermes_cli.config import save_config

    merged = {**_section(), **changes}
    save_config({"lyra_lite": merged}, merge_existing=True)


def default_engine() -> str:
    return "hermes"


def migrate_engine_settings() -> None:
    """Retire the old adapter settings, keeping a private recovery copy.

    Remember the previous default only to identify unopened legacy projects.
    New projects always have an explicit Hermes engine.
    """
    from hermes_cli.config import get_config_path, read_raw_config, save_config
    from lyra_lite.store import _backup_once

    config = read_raw_config()
    section = config.get("lyra_lite") or {}
    if not isinstance(section, dict):
        return
    if section.get("engine") != "claude" and "claude" not in section:
        return
    path = get_config_path()
    _backup_once(path.parent / "lyra-lite" / "migrations" / "claude-to-hermes" / "config.yaml", path.read_bytes())
    section = dict(section)
    if section.get("engine") == "claude":
        section["legacy_engine_default"] = "claude"
    section.pop("claude", None)
    section["engine"] = "hermes"
    config["lyra_lite"] = section
    save_config(config)


# Nothing chosen means DEFAULT_EFFORT; providers have different defaults.
EFFORTS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_EFFORT = "high"


ABOUT_ME_LIMIT = 2000


def about_me() -> str:
    """What the owner wrote about themselves — the only memory shared across projects."""
    return str(_section().get("about_me") or "").strip()[:ABOUT_ME_LIMIT]


def hermes_model() -> dict:
    from hermes_cli.config import load_config

    model = (load_config() or {}).get("model") or {}
    if isinstance(model, dict):
        return {"provider": str(model.get("provider") or ""), "model": str(model.get("default") or "")}
    return {"provider": "", "model": str(model)}


def model_options(refresh: bool = False) -> dict:
    """Linked providers plus models served by Ollama on this computer."""
    from hermes_cli.inventory import build_model_options_payload, load_picker_context

    payload = build_model_options_payload(
        load_picker_context(), explicit_only=False, include_unconfigured=False,
        discover_local_ollama=True, refresh=refresh,
    )
    providers = []
    for p in payload.get("providers") or []:
        models = [str(m) for m in (p.get("models") or [])]
        if not models or p.get("slug") == "moa":
            continue
        providers.append({"slug": p.get("slug"), "name": p.get("name") or p.get("slug"),
                          "models": models, "current": bool(p.get("is_current"))})
    return {"providers": providers, "provider": payload.get("provider"), "model": payload.get("model")}


def hermes_effort() -> dict:
    """Hermes' thinking effort: what is saved (``agent.reasoning_effort``) and
    what the current model actually gets, since a per-model override wins."""
    from hermes_cli.config import load_config
    from hermes_constants import resolve_reasoning_config

    cfg = load_config() or {}
    agent = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
    raw = agent.get("reasoning_effort")
    saved = "off" if raw is False else str(raw or "").strip().lower()
    if saved in {"none", "false", "disabled"}:
        saved = "off"
    if saved not in (*EFFORTS, "off"):
        saved = ""
    resolved = resolve_reasoning_config(cfg, hermes_model()["model"])
    if resolved is None:
        effective = DEFAULT_EFFORT
    elif resolved.get("enabled") is False:
        effective = "off"
    else:
        effective = str(resolved.get("effort") or "")
    return {"effort": saved, "effective": effective, "overridden": effective != (saved or DEFAULT_EFFORT)}


def set_hermes_effort(effort: str) -> dict:
    """Save Hermes' global thinking effort ("" = Appling's default, "off" = no thinking)."""
    from hermes_cli.config import save_config

    if effort not in ("", "off", *EFFORTS):
        raise ValueError(f"Unknown effort: {effort}")
    save_config({"agent": {"reasoning_effort": "none" if effort == "off" else effort}}, merge_existing=True)
    return hermes_effort()


def set_hermes_model(provider: str, model: str, confirm: bool = False) -> dict[str, Any]:
    """Save Hermes' main model. Warns once before an expensive model."""
    if not confirm:
        try:
            from hermes_cli.model_cost_guard import expensive_model_warning

            warning = expensive_model_warning(model, provider=provider)
        except Exception:
            warning = None
        if warning is not None:
            return {"ok": False, "confirm_required": True, "message": warning.message}
    from hermes_cli.web_server import _apply_model_assignment_sync

    _apply_model_assignment_sync("main", provider, model, "", "", "")
    return {"ok": True, **hermes_model()}


def effective_engine(state: dict) -> str:
    """All Appling projects use Hermes; ProjectStore handles legacy state."""
    return "hermes"


CODEX_DEFAULT = {"provider": "openai-codex", "model": "gpt-6.1-sol"}
CLAUDE_DEVELOPMENT = {"provider": "anthropic", "model": "claude-opus-5-5", "effort": "high"}
CLAUDE_DOCUMENTS = {"provider": "anthropic", "model": "claude-sonnet-5"}
LUNA_DOCUMENTS = {"provider": "openai-codex", "model": "gpt-6-luna"}

_AGENT_DEFAULTS = {
    "sw-developer": CLAUDE_DEVELOPMENT,
    "website-builder": CLAUDE_DEVELOPMENT,
    "oop-restructurer": CLAUDE_DEVELOPMENT,
    "debugger": CLAUDE_DEVELOPMENT,
    "tech-writer": CLAUDE_DOCUMENTS,
    "req-engineer": CLAUDE_DOCUMENTS,
    "task-planner": CLAUDE_DOCUMENTS,
    "proj-manager": CLAUDE_DOCUMENTS,
    "context-save": CLAUDE_DOCUMENTS,
    "deck-builder": CLAUDE_DOCUMENTS,
    "ux-writer": CLAUDE_DOCUMENTS,
    "spec": CLAUDE_DOCUMENTS,
}


def agent_model_overrides() -> dict:
    selections = _section().get("agent_models")
    return selections if isinstance(selections, dict) else {}


def agent_model_settings() -> list[dict]:
    from lyra_lite.agents import AGENTS

    saved = agent_model_overrides()
    return [
        {"id": agent_id, "label": label, "default": _AGENT_DEFAULTS.get(agent_id),
         "selection": saved.get(agent_id)}
        for agent_id, label, _ in AGENTS
    ]


_agent_model_lock = Lock()


def save_agent_model(agent_id: str, selection: Any) -> None:
    from hermes_cli.config import read_raw_config, save_config
    from lyra_lite.agents import LABELS

    if agent_id not in LABELS:
        raise ValueError("Unknown agent.")

    if selection is not None:
        if not isinstance(selection, dict):
            raise ValueError("Choose a provider and a model.")
        provider = str(selection.get("provider") or "").strip()
        model = str(selection.get("model") or "").strip()
        effort = str(selection.get("effort") or "").strip()
        if not provider or not model or len(provider) > 120 or len(model) > 500:
            raise ValueError("Choose a provider and a model.")
        if effort not in ("", "off", *EFFORTS):
            raise ValueError("Unknown effort level.")
        selection = {"provider": provider, "model": model, "effort": effort}

    with _agent_model_lock:
        config = read_raw_config()
        section = _section()
        saved = dict(section.get("agent_models") or {})
        if selection is None:
            saved.pop(agent_id, None)
        else:
            saved[agent_id] = selection
        # Replace this map so resetting actually removes the key.
        config["lyra_lite"] = {**section, "agent_models": saved}
        save_config(config)


def model_runtime(selection: dict) -> dict:
    from hermes_cli.runtime_provider import resolve_runtime_provider
    from hermes_constants import parse_reasoning_effort

    provider, model = selection["provider"], selection["model"]
    try:
        runtime = resolve_runtime_provider(requested=provider, target_model=model)
    except (ValueError, RuntimeError) as exc:
        raise ValueError(
            f"Could not use {model} on {provider}. Link the provider or change the agent model in Settings."
        ) from exc
    if not runtime.get("api_key") or not runtime.get("provider"):
        raise ValueError(f"Link {provider} or change the model for this agent in Settings.")
    effort = selection.get("effort") or ""
    return {
        **runtime, "model": model,
        "provider": provider if runtime["provider"] == "custom" else runtime["provider"],
        "reasoning": parse_reasoning_effort("none" if effort == "off" else effort),
    }


def resolve_agent_model(agent_id: str | None, preferences: dict, legacy: dict) -> dict | None:
    if agent_id is None:
        return None
    if preferences.get(agent_id):
        return model_runtime(preferences[agent_id])
    if isinstance(legacy.get(agent_id), str) and legacy[agent_id]:
        return {"model": legacy[agent_id]}
    default = _AGENT_DEFAULTS.get(agent_id)
    if default is None:
        return None
    alternate = CODEX_DEFAULT if default is CLAUDE_DEVELOPMENT else LUNA_DOCUMENTS
    for selection in (default, {**default, "provider": "claude-cli"}, alternate):
        try:
            return model_runtime(selection)
        except ValueError:
            continue
    return None
