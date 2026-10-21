"""Tool tables and text helpers shared by the Claude engine's modules."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Claude Code tool names -> the names the Lyra screen already words nicely.
TOOL_NAMES = {
    "Bash": "terminal", "Read": "read_file", "Write": "write_file", "Edit": "patch",
    "MultiEdit": "patch", "NotebookEdit": "patch", "Glob": "search_files",
    "Grep": "search_files", "WebSearch": "web_search", "WebFetch": "web_extract",
    "TodoWrite": "todo", "Task": "delegate_task", "Agent": "delegate_task",
    "Skill": "skill_view",
}
AGENT_TOOLS = {"Task", "Agent"}
# Claude Code tools Lyra must not use: scheduling itself, background agent
# plumbing it can't observe, and worktree/workflow modes outside the project.
DISALLOWED = ["CronCreate", "CronDelete", "CronList", "ScheduleWakeup", "EnterWorktree",
              "ExitWorktree", "Workflow", "ReportFindings", "SendMessage", "ListAgents"]
RECALL_TOOL = "mcp__lyra__project_recall"
ALWAYS_OK = {"WebSearch", "WebFetch", "TodoWrite", "Read", "Glob", "Grep", "Skill", RECALL_TOOL}


def _preview(value: Any, limit: int = 300) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    try:
        from agent.redact import redact_sensitive_text
    except ImportError:
        redact_sensitive_text = None
    if redact_sensitive_text is not None:
        try:
            text = redact_sensitive_text(text)
        # Last resort: previews are built while a turn streams, and a failed
        # redaction must not abort that message and leave the turn open.
        except Exception:
            logger.debug("could not redact a preview", exc_info=True)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(c.get("text") or "") for c in content if isinstance(c, dict))
    return ""
