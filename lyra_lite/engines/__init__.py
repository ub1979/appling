"""Engine adapters. Every engine reports through the same TurnHooks."""

from lyra_lite.engines.base import Engine, TurnHooks, TurnResult

__all__ = ["Engine", "TurnHooks", "TurnResult", "make_engine"]


ENGINES = {
    "codex": "Codex — native coding engine",
}


def make_engine(name: str, **kwargs) -> Engine:
    if name == "codex":
        from lyra_lite.engines.codex import CodexEngine

        return CodexEngine(**kwargs)
    raise ValueError(f"unknown engine: {name}")
