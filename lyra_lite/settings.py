"""Appling settings for Hermes models, effort and owner preferences."""

from __future__ import annotations

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
