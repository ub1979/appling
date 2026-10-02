"""Appling-wide AI settings: which engine, which model.

- The Hermes model is Hermes' own main model in ``config.yaml`` — the same
  setting the Studio's model page writes — chosen from the providers the
  owner has linked (Codex, Ollama, Anthropic, Copilot, …).
- The default engine and the Claude Code engine's model/address live under
  ``lyra_lite:`` in ``config.yaml``.
- A project follows these defaults unless the owner picked an engine for that
  project specifically.
"""

from __future__ import annotations

from typing import Any

ENGINES = ("hermes", "claude")


def _section() -> dict:
    from hermes_cli.config import load_config

    section = (load_config() or {}).get("lyra_lite") or {}
    return section if isinstance(section, dict) else {}


def save_section(changes: dict) -> None:
    from hermes_cli.config import save_config

    merged = {**_section(), **changes}
    save_config({"lyra_lite": merged}, merge_existing=True)


def default_engine() -> str:
    engine = str(_section().get("engine") or "hermes")
    return engine if engine in ENGINES else "hermes"


def claude_defaults() -> dict:
    claude = _section().get("claude") or {}
    return {k: str(v) for k, v in claude.items() if k in {"model", "base_url", "auth_token", "route"} and v} \
        if isinstance(claude, dict) else {}


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
    """Linked providers and their models, as the Studio's picker lists them."""
    from hermes_cli.inventory import build_model_options_payload, load_picker_context

    payload = build_model_options_payload(load_picker_context(), explicit_only=False,
                                          include_unconfigured=False, refresh=refresh)
    providers = []
    for p in payload.get("providers") or []:
        models = [str(m) for m in (p.get("models") or [])]
        if not models or p.get("slug") == "moa":
            continue
        providers.append({"slug": p.get("slug"), "name": p.get("name") or p.get("slug"),
                          "models": models, "current": bool(p.get("is_current"))})
    return {"providers": providers, "provider": payload.get("provider"), "model": payload.get("model")}


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
    """The engine a project runs on: its own choice, else Appling's default."""
    if state.get("engine_override") and state.get("engine") in ENGINES:
        return str(state["engine"])
    return default_engine()


def effective_claude(state: dict) -> dict:
    project = state.get("claude") or {}
    merged = dict(claude_defaults())
    if state.get("engine_override") and isinstance(project, dict):
        merged.update({k: v for k, v in project.items() if v})
    return merged
