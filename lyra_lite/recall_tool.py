"""``project_recall`` for the Hermes engine.

Registered by APP IT into its own toolset (``lyra_memory``), so the tool
exists only in APP IT — never in the classic Studio or other Hermes
chats. Delegated agents inherit the toolset and can recall too.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from lyra_lite.memory import RECALL_DESCRIPTION, ProjectMemory, format_results

TOOLSET = "lyra_memory"
_workspaces: dict[str, str] = {}
_lock = threading.Lock()
_registered = False


def remember_workspace(session_key: str, workspace: str) -> None:
    with _lock:
        _workspaces[session_key] = workspace


def _project_root(task_id: str | None) -> Path | None:
    try:
        from agent.runtime_cwd import resolve_agent_cwd

        here = Path(resolve_agent_cwd()).resolve()
        for folder in (here, *here.parents):
            if (folder / ".lyra").is_dir():
                return folder
    except Exception:
        pass
    with _lock:
        if task_id and task_id in _workspaces:
            return Path(_workspaces[task_id])
        if len(set(_workspaces.values())) == 1:
            return Path(next(iter(_workspaces.values())))
    return None


def _handler(args: dict, **kwargs) -> str:
    query = str((args or {}).get("query") or "").strip()
    if not query:
        return json.dumps({"error": "Give a few words to search for."})
    root = _project_root(kwargs.get("task_id"))
    if root is None:
        return json.dumps({"error": "No APP IT project is open here."})
    limit = int((args or {}).get("limit") or 6)
    results = ProjectMemory(root).search(query, limit=max(1, min(limit, 10)))
    return json.dumps({"result": format_results(query, results)}, ensure_ascii=False)


SCHEMA = {
    "name": "project_recall",
    "description": RECALL_DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Words to look for, e.g. 'CSV export format'."},
            "limit": {"type": "integer", "description": "How many results (1–10, default 6)."},
        },
        "required": ["query"],
    },
}


def register() -> None:
    global _registered
    if _registered:
        return
    from tools.registry import registry

    registry.register(name="project_recall", toolset=TOOLSET, schema=SCHEMA, handler=_handler,
                      description="Search this project's memory", emoji="🧠")
    _registered = True
