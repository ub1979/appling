"""Which tools Claude Code may use without asking the owner.

Safety matches the Hermes engine: file edits inside the project are allowed,
shell commands that Hermes' danger check flags go to the owner's inbox.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from lyra_lite.engines.claude.common import ALWAYS_OK, _preview

logger = logging.getLogger(__name__)

APPROVAL_TIMEOUT_S = 30 * 60


class PermissionsMixin:
    """ClaudeEngine's can_use_tool callback; needs ``_hooks``, ``session_key``
    and ``_session_allowed``."""

    async def _can_use_tool(self, tool_name: str, tool_input: dict, context):
        from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

        if tool_name in ALWAYS_OK:
            return PermissionResultAllow()
        command = str(tool_input.get("command") or "") if tool_name == "Bash" else ""
        pattern = tool_name
        description = f"Claude wants to use {tool_name}"
        if tool_name == "Bash":
            from tools.approval import detect_dangerous_command, detect_hardline_command, is_approved

            hard, hard_desc = detect_hardline_command(command)[:2]
            if hard:
                return PermissionResultDeny(message=f"BLOCKED: {hard_desc}. Never run this.")
            dangerous, pattern_key, desc = detect_dangerous_command(command)
            if not dangerous:
                return PermissionResultAllow()
            pattern = str(pattern_key)
            description = str(desc)
            if pattern in self._session_allowed or is_approved(self.session_key, pattern):
                return PermissionResultAllow()
        elif pattern in self._session_allowed:
            return PermissionResultAllow()

        hooks = self._hooks
        if hooks is None:
            return PermissionResultDeny(message="No owner is available to approve this.")
        loop = asyncio.get_running_loop()
        answer: asyncio.Future = loop.create_future()

        def _on_answer(value: Any) -> None:
            loop.call_soon_threadsafe(lambda: answer.done() or answer.set_result(value))

        item_id = hooks.ask("approval", _on_answer,
                            command=command or _preview(tool_input, 500),
                            description=description,
                            choices=["once", "session", "always", "deny"])
        try:
            choice = str(await asyncio.wait_for(answer, APPROVAL_TIMEOUT_S) or "deny")
        except asyncio.TimeoutError:
            hooks.expire(item_id)
            choice = "deny"
        if choice == "deny":
            return PermissionResultDeny(
                message="BLOCKED: the owner did not allow this. Do not retry it or work around it.")
        if choice in {"session", "always"}:
            self._session_allowed.add(pattern)
        if choice == "always" and tool_name == "Bash":
            # approve_permanent can't fail and save_permanent_allowlist logs
            # its own write errors; only the import itself can.
            try:
                from tools.approval import _permanent_approved, approve_permanent, save_permanent_allowlist
            except ImportError:
                logger.warning("could not save permanent approval", exc_info=True)
            else:
                approve_permanent(pattern)
                save_permanent_allowlist(_permanent_approved)
        return PermissionResultAllow()
