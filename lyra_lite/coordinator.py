"""Keep Lyra (the coordinator) light.

Lyra talks with the owner and hands work to agents; the agents build, test
and commit. On the calculator build Lyra made 128 model calls and her
conversation grew from 21k to 88k tokens per call because she ran tests and
read raw output herself. Three limits stop that, applied to Lyra's agent only:

- no shell (terminal / process / code execution) in Lyra's own tool list,
  while her enabled toolsets stay complete so delegated agents keep them;
- a small tool-output budget, so one large result cannot flood her context;
- earlier summary compression (about 100k tokens).
"""

from __future__ import annotations

from typing import Any

WITHHELD_TOOLS = frozenset({"terminal", "process", "read_terminal", "close_terminal", "execute_code"})
RESULT_CHARS = 8_000
TURN_CHARS = 32_000
COMPRESSION_CAP_TOKENS = 100_000


def coordinator_budget(base):
    from tools.budget_config import BudgetConfig

    return BudgetConfig(
        default_result_size=min(base.default_result_size, RESULT_CHARS),
        turn_budget=min(base.turn_budget, TURN_CHARS),
        preview_size=min(base.preview_size, RESULT_CHARS),
        tool_overrides=dict(base.tool_overrides),
    )


def withhold_shell(agent: Any) -> None:
    """Drop shell tools from this agent's own schema (idempotent, cache-safe:
    the list only changes the first time, before any request)."""
    tools = list(getattr(agent, "tools", None) or [])
    kept = [t for t in tools if t.get("function", {}).get("name") not in WITHHELD_TOOLS]
    if len(kept) != len(tools):
        agent.tools = kept
        agent.valid_tool_names = {t["function"]["name"] for t in kept}


def make_coordinator(agent: Any) -> None:
    # Pin the toolsets first: with "all tools" (None) Hermes derives a
    # child's toolsets from the parent's tool names, which would strip the
    # shell from development agents too.
    if getattr(agent, "enabled_toolsets", None) is None:
        import model_tools

        agent.enabled_toolsets = sorted({
            ts for name in getattr(agent, "valid_tool_names", set())
            if (ts := model_tools.get_toolset_for_tool(name)) is not None
        })
    # The between-turns MCP refresh rebuilds the tool list from toolsets and
    # would hand the shell back; Lyra has no use for late MCP tools.
    agent._skip_mcp_refresh = True
    withhold_shell(agent)
    agent.tool_budget_override = coordinator_budget
    compressor = getattr(agent, "context_compressor", None)
    if compressor is not None and hasattr(compressor, "threshold_tokens_cap"):
        cap = getattr(compressor, "threshold_tokens_cap", None)
        compressor.threshold_tokens_cap = min(cap, COMPRESSION_CAP_TOKENS) if cap else COMPRESSION_CAP_TOKENS
        apply = getattr(compressor, "_apply_threshold_tokens_cap", None)
        if callable(apply):
            apply()
