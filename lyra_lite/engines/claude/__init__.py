"""Claude Code (via the Claude Agent SDK) as an Appling Lite engine.

The model is chosen separately from the engine: an Anthropic API key runs
Claude models; a custom Anthropic-compatible address (for example Ollama)
runs other models through the same engine. Appling never falls back to a
Claude subscription login — the CLI gets its own config folder.

Safety matches the Hermes engine: file edits inside the project are allowed,
shell commands that Hermes' danger check flags go to the owner's inbox.

Modules: ``routes`` (model routes and settings), ``turns`` (turn handling),
``helpers`` (the helper bridge), ``permissions``, ``playbooks`` (the builder
plugin and engine notes), ``common`` (tool tables, previews) and ``engine``.
Nothing here imports the SDK at load time, so routes work without it.
"""

from lyra_lite.engines.claude.common import (
    AGENT_TOOLS, ALWAYS_OK, DISALLOWED, RECALL_TOOL, TOOL_NAMES, _preview, _result_text,
)
from lyra_lite.engines.claude.engine import ClaudeEngine
from lyra_lite.engines.claude.helpers import REPORT_PREFIX, _background_agents
from lyra_lite.engines.claude.permissions import APPROVAL_TIMEOUT_S
from lyra_lite.engines.claude.playbooks import (
    DESIGN_SKILLS_ROOT, EXTRA_SKILLS, PLUGIN_NAME, REPO_ROOT, SKILLS_ROOT, _skill_index, _skill_name,
    builder_plugin_dir, engine_notes,
)
from lyra_lite.engines.claude.routes import (
    DEFAULT_MODEL, NO_EFFORT_MODELS, OLLAMA_URL, ROUTES, claude_cli_status, claude_effort, claude_env,
    claude_route, find_claude_cli,
)
from lyra_lite.engines.claude.turns import _Turn

__all__ = [
    "AGENT_TOOLS", "ALWAYS_OK", "APPROVAL_TIMEOUT_S", "DEFAULT_MODEL", "DESIGN_SKILLS_ROOT", "DISALLOWED",
    "EXTRA_SKILLS", "NO_EFFORT_MODELS", "OLLAMA_URL", "PLUGIN_NAME", "RECALL_TOOL", "REPORT_PREFIX",
    "REPO_ROOT", "ROUTES", "SKILLS_ROOT", "TOOL_NAMES", "ClaudeEngine", "_Turn", "_background_agents",
    "_preview", "_result_text", "builder_plugin_dir", "claude_cli_status", "claude_effort", "claude_env",
    "claude_route", "engine_notes", "find_claude_cli",
]
