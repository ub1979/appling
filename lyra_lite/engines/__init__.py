"""Engine adapters. Every engine reports through the same TurnHooks."""

from lyra_lite.engines.base import Engine, TurnHooks, TurnResult

__all__ = ["Engine", "TurnHooks", "TurnResult", "make_engine"]


def make_engine(name: str, **kwargs) -> Engine:
    if name == "hermes":
        from lyra_lite.engines.hermes import HermesEngine

        return HermesEngine(**kwargs)
    raise ValueError(f"unknown engine: {name}")
