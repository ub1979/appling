"""Which model route the Claude Code program runs on, and with which credentials.

subscription — the owner's own `claude` program and its sign-in (their Claude plan).
ollama       — Ollama's Anthropic-compatible address on this computer.
api          — an Anthropic API key (pay per use).
custom       — another Anthropic-compatible address and token.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

DEFAULT_MODEL = "claude-opus-5-5"
OLLAMA_URL = "http://localhost:11434"
ROUTES = ("subscription", "ollama", "api", "custom")


def claude_route(settings: dict) -> str:
    route = str(settings.get("route") or "")
    if route in ROUTES:
        return route
    return "custom" if settings.get("base_url") else "subscription"


NO_EFFORT_MODELS = ("claude-3", "haiku-4", "sonnet-4-5", "sonnet-4-2025", "opus-4-2025", "opus-4-1")


def claude_effort(settings: dict) -> str | None:
    """The --effort to give the Claude program: the owner's choice, else Appling's default.

    Only Anthropic's own models take an effort level; an Ollama or custom
    address gets none, since those servers may reject the field.
    """
    from lyra_lite.settings import DEFAULT_EFFORT, EFFORTS

    if claude_route(settings) not in ("subscription", "api"):
        return None
    effort = str(settings.get("effort") or "")
    if effort in EFFORTS:
        return effort
    # Older models take no effort level; the default isn't forced on them.
    model = str(settings.get("model") or "").lower()
    if any(old in model for old in NO_EFFORT_MODELS):
        return None
    return DEFAULT_EFFORT


def claude_model(settings: dict) -> str | None:
    # On the owner's plan, no model means the Claude program's own default.
    return str(settings.get("model") or "") or (
        None if claude_route(settings) == "subscription" else DEFAULT_MODEL)


def find_claude_cli() -> str | None:
    found = shutil.which("claude")
    if found:
        return found
    for candidate in (Path.home() / ".local" / "bin" / "claude", Path("/opt/homebrew/bin/claude")):
        if candidate.exists():
            return str(candidate)
    return None


def claude_cli_path(settings: dict) -> str | None:
    """The owner's own `claude` program on their plan; the SDK's bundled one otherwise."""
    return find_claude_cli() if claude_route(settings) == "subscription" else None


def claude_cli_status() -> dict:
    """Is the owner's Claude program installed and signed in to a plan?"""
    path = find_claude_cli()
    if not path:
        return {"found": False, "logged_in": False}
    env = {k: v for k, v in os.environ.items()
           if k not in {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"}}
    try:
        out = subprocess.run([path, "auth", "status", "--json"], capture_output=True, text=True,
                             timeout=20, env=env).stdout
        data = json.loads(out or "{}")
    # The program can't start, hangs past the timeout, or prints something
    # other than JSON (an older version without --json).
    except (OSError, subprocess.SubprocessError, ValueError):
        return {"found": True, "logged_in": False}
    return {"found": True, "logged_in": bool(data.get("loggedIn")),
            "method": data.get("authMethod"), "plan": data.get("subscriptionType")}


def claude_env(settings: dict) -> dict[str, str]:
    """Environment for the Claude Code program, by route.

    On the owner's plan, API keys are blanked so billing can't switch silently.
    """
    env = {"DISABLE_TELEMETRY": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
    route = claude_route(settings)
    if route == "subscription":
        if not find_claude_cli():
            raise RuntimeError(
                "Claude Code isn't installed on this Mac. Install it from "
                "https://claude.com/claude-code, sign in once with `claude`, then try again — "
                "or pick Ollama or an API key in AI settings.")
        env.update({"ANTHROPIC_API_KEY": "", "ANTHROPIC_AUTH_TOKEN": "", "ANTHROPIC_BASE_URL": ""})
        return env
    # Every other route uses Lyra's own Claude config folder, so the owner's
    # personal Claude sign-in is never used by accident.
    from hermes_constants import get_hermes_home

    config_dir = get_hermes_home() / "lyra-lite" / "claude-config"
    config_dir.mkdir(parents=True, exist_ok=True)
    env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    if route in {"ollama", "custom"}:
        base_url = str(settings.get("base_url") or "").strip() or (OLLAMA_URL if route == "ollama" else "")
        if not base_url:
            raise RuntimeError("Add the model address in AI settings.")
        env["ANTHROPIC_BASE_URL"] = base_url
        env["ANTHROPIC_AUTH_TOKEN"] = str(settings.get("auth_token") or "ollama")
        env["ANTHROPIC_API_KEY"] = ""
        return env
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "No Anthropic API key found (ANTHROPIC_API_KEY in ~/.hermes/.env). "
            "To use your Claude plan instead, choose 'Your Claude plan' in AI settings.")
    env["ANTHROPIC_API_KEY"] = key
    return env
