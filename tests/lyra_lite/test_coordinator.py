from types import SimpleNamespace

from agent.tool_executor import _budget_for_agent
from lyra_lite.coordinator import COMPRESSION_CAP_TOKENS, RESULT_CHARS, TURN_CHARS, make_coordinator
from tools.budget_config import DEFAULT_BUDGET


def _tool(name):
    return {"type": "function", "function": {"name": name}}


def test_budget_override_applies_to_that_agent_only():
    plain = SimpleNamespace(context_compressor=None)
    assert _budget_for_agent(plain) == DEFAULT_BUDGET
    lyra = SimpleNamespace(context_compressor=None)
    make_coordinator(lyra)
    budget = _budget_for_agent(lyra)
    assert budget.default_result_size == RESULT_CHARS and budget.turn_budget == TURN_CHARS


def test_coordinator_loses_shell_but_keeps_toolsets_for_children():
    compressor = SimpleNamespace(threshold_tokens_cap=None, threshold_tokens=200_000, context_length=272_000,
                                 _apply_threshold_tokens_cap=lambda: None)
    agent = SimpleNamespace(
        tools=[_tool("terminal"), _tool("read_file"), _tool("delegate_task"), _tool("execute_code")],
        valid_tool_names={"terminal", "read_file", "delegate_task", "execute_code"},
        enabled_toolsets=["terminal", "file", "delegation", "code_execution"],
        context_compressor=compressor,
    )
    make_coordinator(agent)
    assert agent.valid_tool_names == {"read_file", "delegate_task"}
    assert [t["function"]["name"] for t in agent.tools] == ["read_file", "delegate_task"]
    assert "terminal" in agent.enabled_toolsets  # delegated agents still get it
    assert agent._skip_mcp_refresh is True
    assert compressor.threshold_tokens_cap == COMPRESSION_CAP_TOKENS


def test_all_tools_mode_is_pinned_before_the_shell_is_withheld():
    agent = SimpleNamespace(tools=[_tool("terminal"), _tool("read_file")],
                            valid_tool_names={"terminal", "read_file"}, enabled_toolsets=None,
                            context_compressor=None)
    make_coordinator(agent)
    assert agent.enabled_toolsets and "terminal" in agent.enabled_toolsets
    assert "terminal" not in agent.valid_tool_names
