"""Which credentials the Claude Code program gets, per route."""

import pytest

from lyra_lite.engines.claude import routes as claude_routes
from lyra_lite.engines.claude import ClaudeEngine, claude_effort, claude_route
from lyra_lite.engines.hermes import appling_reasoning
from lyra_lite.settings import DEFAULT_EFFORT, EFFORTS


def _engine(**settings):
    return ClaudeEngine(workspace="/tmp", session_key="k", settings=settings)


def test_route_defaults():
    assert claude_route({}) == "subscription"
    assert claude_route({"base_url": "http://x"}) == "custom"
    assert claude_route({"route": "ollama"}) == "ollama"


def test_plan_route_uses_own_sign_in_and_blanks_api_keys(monkeypatch):
    monkeypatch.setattr(claude_routes, "find_claude_cli", lambda: "/usr/local/bin/claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-be-used")
    env = _engine(route="subscription")._env()
    assert env["ANTHROPIC_API_KEY"] == "" and env["ANTHROPIC_BASE_URL"] == ""
    assert "CLAUDE_CONFIG_DIR" not in env  # the owner's own Claude sign-in


def test_plan_route_without_claude_program_explains(monkeypatch):
    monkeypatch.setattr(claude_routes, "find_claude_cli", lambda: None)
    with pytest.raises(RuntimeError, match="isn't installed"):
        _engine(route="subscription")._env()


def test_other_routes_never_touch_the_personal_sign_in(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ollama = _engine(route="ollama")._env()
    assert ollama["ANTHROPIC_BASE_URL"] == "http://localhost:11434" and "CLAUDE_CONFIG_DIR" in ollama
    with pytest.raises(RuntimeError, match="Your Claude plan"):
        _engine(route="api")._env()


def test_effort_reaches_claude_only_on_anthropic_routes():
    assert claude_effort({"route": "subscription", "effort": "xhigh"}) == "xhigh"
    assert claude_effort({"route": "api", "effort": "low"}) == "low"
    # An Ollama or custom server may reject the field: it gets none.
    assert claude_effort({"route": "ollama", "effort": "high"}) is None
    assert claude_effort({"base_url": "http://x", "effort": "high"}) is None
    # Nothing chosen, or an unknown word: Appling's default, never above high.
    assert claude_effort({"route": "subscription"}) == DEFAULT_EFFORT
    assert claude_effort({"route": "subscription", "effort": "turbo"}) == DEFAULT_EFFORT
    assert EFFORTS.index(DEFAULT_EFFORT) <= EFFORTS.index("high")
    # Older models take no effort level: the default isn't forced on them.
    assert claude_effort({"route": "subscription", "model": "claude-haiku-4-5-20251001"}) is None
    assert claude_effort({"route": "subscription", "model": "claude-opus-5-5"}) == DEFAULT_EFFORT


def test_hermes_uses_appling_default_only_when_nothing_is_saved():
    assert appling_reasoning(None) == {"enabled": True, "effort": DEFAULT_EFFORT}
    assert appling_reasoning({"enabled": False}) == {"enabled": False}  # "off" stays off
    assert appling_reasoning({"enabled": True, "effort": "max"})["effort"] == "max"
