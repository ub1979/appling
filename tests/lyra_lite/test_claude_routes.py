"""Which credentials the Claude Code program gets, per route."""

import pytest

from lyra_lite.engines import claude as claude_engine
from lyra_lite.engines.claude import ClaudeEngine, claude_route


def _engine(**settings):
    return ClaudeEngine(workspace="/tmp", session_key="k", settings=settings)


def test_route_defaults():
    assert claude_route({}) == "subscription"
    assert claude_route({"base_url": "http://x"}) == "custom"
    assert claude_route({"route": "ollama"}) == "ollama"


def test_plan_route_uses_own_sign_in_and_blanks_api_keys(monkeypatch):
    monkeypatch.setattr(claude_engine, "find_claude_cli", lambda: "/usr/local/bin/claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-be-used")
    env = _engine(route="subscription")._env()
    assert env["ANTHROPIC_API_KEY"] == "" and env["ANTHROPIC_BASE_URL"] == ""
    assert "CLAUDE_CONFIG_DIR" not in env  # the owner's own Claude sign-in


def test_plan_route_without_claude_program_explains(monkeypatch):
    monkeypatch.setattr(claude_engine, "find_claude_cli", lambda: None)
    with pytest.raises(RuntimeError, match="isn't installed"):
        _engine(route="subscription")._env()


def test_other_routes_never_touch_the_personal_sign_in(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ollama = _engine(route="ollama")._env()
    assert ollama["ANTHROPIC_BASE_URL"] == "http://localhost:11434" and "CLAUDE_CONFIG_DIR" in ollama
    with pytest.raises(RuntimeError, match="Your Claude plan"):
        _engine(route="api")._env()
