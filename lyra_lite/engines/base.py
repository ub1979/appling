"""The pipe between Lyra Lite and an agent engine.

An engine runs one turn at a time and reports everything through
:class:`TurnHooks`. It never talks to the UI, HTTP, or files directly, so any
engine (Hermes, the Claude Agent SDK, a CLI agent) plugs in the same way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


@dataclass
class TurnResult:
    reply: str
    messages: list[dict]
    completed: bool = True
    interrupted: bool = False
    error: str | None = None
    usage: dict = field(default_factory=dict)


class TurnHooks(Protocol):
    def emit(self, type_: str, **data: Any) -> None:
        """Record one activity event (delta, tool, helper, status, ...)."""

    def ask(
        self,
        kind: str,
        on_answer: Callable[[Any], None],
        **fields: Any,
    ) -> str:
        """Open an owner inbox item; *on_answer* runs when it is answered.

        Returns the item id. Non-blocking: engines that need a blocking
        answer wait on their own event inside *on_answer*.
        """

    def expire(self, item_id: str) -> None:
        """Close an inbox item that no longer needs an answer."""


class Engine(Protocol):
    name: str

    def run_turn(self, text: str, history: list[dict], hooks: TurnHooks) -> TurnResult:
        ...

    def interrupt(self) -> None:
        ...

    def close(self) -> None:
        ...
