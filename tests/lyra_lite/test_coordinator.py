from types import SimpleNamespace

import pytest

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


@pytest.mark.parametrize("threshold", [0.75, 0.85])
@pytest.mark.parametrize("cap", [None, 60_000])
def test_real_compressor_tail_tracks_capped_threshold(threshold, cap):
    from agent.context_compressor import ContextCompressor

    compressor = ContextCompressor(
        model="test-model", config_context_length=272_000,
        threshold_percent=threshold, threshold_tokens_cap=cap, quiet_mode=True,
    )
    ordinary = ContextCompressor(
        model="test-model", config_context_length=272_000,
        threshold_percent=threshold, quiet_mode=True,
    )
    agent = SimpleNamespace(context_compressor=compressor, enabled_toolsets=[], tools=[])
    make_coordinator(agent)
    assert compressor.threshold_tokens == min(cap or COMPRESSION_CAP_TOKENS, COMPRESSION_CAP_TOKENS)
    assert compressor.tail_token_budget == int(compressor.threshold_tokens * compressor.summary_target_ratio)
    assert ordinary.threshold_tokens > compressor.threshold_tokens
    assert ordinary.tail_token_budget == int(ordinary.threshold_tokens * ordinary.summary_target_ratio)

    # Applying the coordinator limits again is harmless. A later model switch
    # must keep both the cap and the derived budget calibrated.
    make_coordinator(agent)
    for context_length in (32_000, 272_000):
        compressor.update_model("switched-test-model", context_length)
        assert compressor.threshold_tokens <= min(cap or COMPRESSION_CAP_TOKENS, COMPRESSION_CAP_TOKENS)
        assert compressor.tail_token_budget == int(compressor.threshold_tokens * compressor.summary_target_ratio)
