"""Turn handling: which turn each message from the Claude program belongs to.

One reader receives everything the Claude program sends. Every turn that
starts must end — Appling's own (it has a future the runner waits on) and the
ones the Claude program starts itself to read a helper's report — or Appling
stays "busy" for good.
"""

from __future__ import annotations

import asyncio
import logging

from lyra_lite.engines.claude.common import TOOL_NAMES, _preview, _result_text
from lyra_lite.engines.claude.helpers import REPORT_PREFIX
from lyra_lite.engines.claude.routes import claude_route

logger = logging.getLogger(__name__)


class _Turn:
    """One Claude Code turn as it streams in — Appling's own (it has a future),
    or one the Claude program started itself to read a helper's report."""

    def __init__(self, hooks, prompt: str = "", future=None):
        self.hooks = hooks
        self.prompt = prompt
        self.future = future
        self.external: dict | None = None  # the runner's turn for a report turn
        self.merged = False   # a report turn while Appling's own turn is waiting
        self.ignored = False  # a report turn while the owner has Appling stopped
        self.carry = ""       # replies of report turns merged into this one
        self.streamed_any = False
        self.need_gap = False
        self.texts: list[str] = []
        self.tool_names: dict[str, str] = {}

    def emit(self, type_: str, **data) -> None:
        if not self.ignored and self.hooks is not None:
            self.hooks.emit(type_, **data)


class TurnsMixin:
    """ClaudeEngine's turn state machine: ``_current``, ``_pending``,
    ``_starting``, ``_carry`` and ``_interrupted``."""

    STOP_GRACE = 15.0  # seconds the Claude program gets to answer a Stop

    # -- the one reader ----------------------------------------------------

    async def _read(self, client) -> None:
        """Everything the Claude program sends, for as long as it runs: Appling's
        turns, turns it starts itself for helper reports, and helper activity
        between turns."""
        try:
            async for msg in client.receive_messages():
                try:
                    self._route(msg)
                # Last resort: one message we can't handle must not stop the
                # reader, or no later turn could ever end.
                except Exception:
                    logger.exception("lyra-lite: could not handle a Claude message")
        except asyncio.CancelledError:
            raise
        # Last resort: the stream can end in an SDK error, bad JSON or a broken
        # pipe; whichever it is, the finally below ends every waiting turn.
        except Exception:
            logger.warning("lyra-lite: the Claude program stopped", exc_info=True)
        finally:
            if self._client is client:
                self._client = None
            waiting = [t for t in [self._current, *self._pending] if t is not None]
            self._current, self._pending, self._starting = None, [], False
            self._agents.clear()  # its background helpers died with it
            self._task_ids.clear()
            for turn in waiting:
                if turn.external is not None:
                    end = getattr(self._hooks, "end_external_turn", None)
                    if end is not None:
                        # Last resort: a runner hook that fails for one turn
                        # must not leave the turns after it waiting forever.
                        try:
                            end(turn.external, reply=turn.carry,
                                error="The Claude program stopped before finishing this report.")
                        except Exception:
                            logger.exception("lyra-lite: could not end a report turn")
                if turn.future is not None and not turn.future.done():
                    turn.future.set_result((turn.carry, {}, "The Claude program stopped; send the message again.",
                                            False))

    def _route(self, msg) -> None:
        from claude_agent_sdk import (
            AssistantMessage, ResultMessage, StreamEvent, SystemMessage, TaskNotificationMessage,
            TaskStartedMessage, UserMessage,
        )

        # Task messages are SystemMessages too: check them first.
        if isinstance(msg, TaskStartedMessage):
            self._helper_started(msg)
            return
        if isinstance(msg, TaskNotificationMessage):
            self._helper_notified(msg)
            return
        if isinstance(msg, SystemMessage):
            if msg.subtype == "init":
                self._starting = True
            return
        if not isinstance(msg, (StreamEvent, AssistantMessage, UserMessage, ResultMessage)):
            # Rate-limit notices and the like come between turns too (a
            # helper's model call); they never start one, or nothing ends it.
            return
        parent = getattr(msg, "parent_tool_use_id", None)
        if parent:
            self._helper_activity(parent, msg)
            return
        if self._starting:
            # Appling's own messages are echoed first (replay-user-messages);
            # a turn without that echo is one Claude started for a report.
            echoed = isinstance(msg, UserMessage) and isinstance(msg.content, str)
            if self._current is not None:
                # A new turn began before the last one's result: close the
                # last one, or Appling stays busy with it for good.
                self._abandon(self._current)
            self._current = self._open_turn(msg.content if echoed else None)
            self._starting = False
            if echoed:
                return
        if self._current is None:
            self._current = self._open_turn(None)
        turn = self._current
        if isinstance(msg, StreamEvent):
            self._stream(turn, msg)
            return
        if isinstance(msg, AssistantMessage):
            self._assistant(turn, msg)
        elif isinstance(msg, UserMessage):
            self._tool_results(turn, msg)
        elif isinstance(msg, ResultMessage):
            self._current = None
            try:
                self._finish(turn, msg)
            # Last resort: the turn is already detached from _current, so if
            # finishing fails (a store write, a runner hook) end it anyway.
            except Exception:
                logger.exception("lyra-lite: could not finish a Claude turn")
                self._abandon(turn, error="Appling could not finish this reply; send the message again.")

    def _open_turn(self, first: str | None) -> _Turn:
        """Which turn is starting: Appling's next waiting message, or a report
        turn the Claude program began on its own."""
        if first is not None and not first.lstrip().startswith(REPORT_PREFIX) and self._pending:
            return self._pending.pop(0)
        if first is None and self._pending and not self._reports:
            return self._pending.pop(0)  # no echo and no report waiting: still ours
        turn = _Turn(self._hooks)
        if first:
            goal, summary = self._report_parts(first)
        else:
            goal, summary = self._reports.pop(0) if self._reports else ("", "")
        begin = getattr(self._hooks, "begin_external_turn", None)
        # "[…" marks a report in the chat, like Hermes' helper reports.
        title = f"[A helper finished: {goal or 'background task'}]"
        started = begin("helper_done", f"{title}\n\n{summary}".strip(), title[:300]) if begin else None
        if started is False:
            turn.ignored = True  # the owner pressed Stop: don't act on reports
            client = self._client
            if client is not None:
                asyncio.get_running_loop().create_task(client.interrupt())
        elif started:
            turn.external = started
        else:
            turn.merged = True
        return turn

    def _stream(self, turn: _Turn, msg) -> None:
        event = msg.event or {}
        if event.get("type") == "message_start" and turn.streamed_any:
            turn.need_gap = True
        delta = event.get("delta") or {}
        if event.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
            piece = str(delta.get("text") or "")
            if piece:
                if turn.need_gap:
                    turn.emit("delta", text="\n\n")
                    turn.need_gap = False
                turn.emit("delta", text=piece)
                turn.streamed_any = True

    def _assistant(self, turn: _Turn, msg) -> None:
        from claude_agent_sdk import TextBlock, ToolUseBlock

        for block in msg.content:
            if isinstance(block, ToolUseBlock):
                turn.tool_names[block.id] = block.name
                if not self._helper_called(turn, block):
                    turn.emit("tool", phase="start", id=block.id, name=TOOL_NAMES.get(block.name, block.name),
                              args=_preview(block.input))
            elif isinstance(block, TextBlock):
                turn.texts.append(block.text)

    def _tool_results(self, turn: _Turn, msg) -> None:
        from claude_agent_sdk import ToolResultBlock

        if isinstance(msg.content, str):
            return  # a helper report folded into this turn; its helper event came already
        for block in msg.content:
            if not isinstance(block, ToolResultBlock):
                continue
            name = turn.tool_names.get(block.tool_use_id, "")
            self._helper_result(block)
            turn.emit("tool", phase="done", id=block.tool_use_id, name=TOOL_NAMES.get(name, name),
                      result=_preview(_result_text(block.content)))

    def _finish(self, turn: _Turn, msg) -> None:
        raw = msg.usage or {}
        usage = {
            "api_calls": int(msg.num_turns or 0),
            "input": int(raw.get("input_tokens") or 0),
            "cache_read": int(raw.get("cache_read_input_tokens") or 0),
            "cache_write": int(raw.get("cache_creation_input_tokens") or 0),
            "output": int(raw.get("output_tokens") or 0),
            "duration_ms": msg.duration_ms,
        }
        # On the owner's plan this figure is only what the API would have
        # charged, not a bill — don't show it as a cost.
        if msg.total_cost_usd is not None and claude_route(self.settings) != "subscription":
            usage["cost_usd"] = msg.total_cost_usd
        interrupted = self._interrupted and turn.future is not None
        error = None
        if msg.is_error and not interrupted and not turn.ignored:
            # The CLI's own words ("You've hit your session limit · resets …").
            error = str(msg.result or "").strip() or f"Claude engine: {msg.subtype}"
        if self.store is not None and msg.session_id:
            state = self.store.state()
            self.store.update_state(claude_session=msg.session_id, claude_chat=state.get("chat_id"))
        reply = (msg.result or (turn.texts[-1] if turn.texts else "")).strip()
        if reply and not turn.streamed_any and not msg.is_error:
            turn.emit("delta", text=reply)
        if turn.future is not None:
            if turn.carry:
                reply = f"{turn.carry}\n\n{reply}".strip()
            if not turn.future.done():
                turn.future.set_result((reply, usage, error, interrupted))
        elif turn.external is not None:
            end = getattr(self._hooks, "end_external_turn", None)
            if end is not None:
                end(turn.external, reply=reply, usage=usage, error=error)
        elif turn.merged and reply:
            if self._pending:
                self._pending[0].carry = f"{self._pending[0].carry}\n\n{reply}".strip()
            else:
                self._carry = f"{self._carry}\n\n{reply}".strip()

    def _abandon(self, turn: _Turn, error: str | None = None) -> None:
        """End a turn the Claude program will send no result for, with what
        it said so far."""
        reply = (turn.texts[-1] if turn.texts else "").strip()
        if turn.future is not None:
            if not turn.future.done():
                turn.future.set_result((f"{turn.carry}\n\n{reply}".strip(), {}, error, self._interrupted))
        elif turn.external is not None:
            end = getattr(self._hooks, "end_external_turn", None)
            if end is not None:
                end(turn.external, reply=f"{turn.carry}\n\n{reply}".strip(), error=error)
        elif turn.merged and reply:
            self._carry = f"{self._carry}\n\n{reply}".strip()

    def _stop_turn(self) -> None:
        """Stop pressed: a report turn has nobody waiting on it, so end it now
        rather than trust the Claude program to answer the interrupt. Appling's
        own turn gets a short grace to end properly, then is ended anyway."""
        turn = self._current
        if turn is None and self._pending:
            turn = self._pending[0]  # sent, but the Claude program never began it
        if turn is None:
            return
        if turn.future is None:
            self._current = None
            turn.ignored = True
            self._abandon(turn)
        else:
            asyncio.get_running_loop().call_later(self.STOP_GRACE, self._end_if_still_open, turn)

    def _end_if_still_open(self, turn: _Turn) -> None:
        if turn.future is None or turn.future.done():
            return
        if self._current is turn:
            self._current = None
        if turn in self._pending:
            self._pending.remove(turn)
        self._abandon(turn)

    @staticmethod
    def _seed(history: list[dict]) -> str:
        lines = []
        for m in history[-30:]:
            content = m.get("content")
            if m.get("role") in {"user", "assistant"} and isinstance(content, str) and content.strip():
                lines.append(f"{m['role'].upper()}: {content.strip()[:2000]}")
        convo = "\n\n".join(lines)[-12000:]
        return ("(This project's conversation so far, from before this engine took over:)\n\n"
                f"{convo}\n\n(The owner's new message:)\n\n")
