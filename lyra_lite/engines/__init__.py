"""Engine adapters. Every engine reports through the same TurnHooks."""

from lyra_lite.engines.base import Engine, TurnHooks, TurnResult

__all__ = ["Engine", "TurnHooks", "TurnResult", "make_engine"]


ENGINES = {
    "hermes": "Hermes — any linked subscription (Codex, Ollama, Copilot, Claude, …)",
    "claude": "Claude Code — Anthropic API key, or an Anthropic-compatible address such as Ollama",
}


def make_engine(name: str, *, store=None, settings: dict | None = None, **kwargs) -> Engine:
    if name == "hermes":
        from lyra_lite.engines.hermes import HermesEngine

        return HermesEngine(**kwargs)
    if name == "claude":
        from lyra_lite.engines.claude import ClaudeEngine

        return ClaudeEngine(store=store, settings=settings, **kwargs)
    raise ValueError(f"unknown engine: {name}")
