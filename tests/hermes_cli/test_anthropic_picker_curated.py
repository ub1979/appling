"""Regression tests for the Anthropic model-picker dropping curated aliases.

Bug — newly-routed curated aliases vanished on a native Anthropic setup
    ``provider_model_ids("anthropic")`` returned the live ``/v1/models`` dump
    verbatim whenever Anthropic credentials were configured. Anthropic's API
    lags behind freshly-routed aliases (e.g. ``claude-fable-5``, which is
    reachable on Anthropic before the models endpoint enumerates it), so the
    curated entry disappeared from the picker. The picker now merges the
    curated ``_PROVIDER_MODELS["anthropic"]`` list with the live catalog,
    deduped.

Bug — new releases were buried under the previous generation
    The merge used to put curated entries first and append live-only models,
    so Opus/Sonnet/Haiku 5.5 landed below claude-sonnet-4-20250514. The merged
    list is now ordered newest version first, whichever source it came from.
"""

from unittest.mock import patch

from hermes_cli import models as M


def test_anthropic_curated_alias_survives_when_live_omits_it():
    """A curated alias missing from /v1/models still surfaces (first)."""
    curated = M._PROVIDER_MODELS["anthropic"]
    assert "claude-fable-5" in curated  # sanity: the alias is curated
    assert "claude-sonnet-5" in curated  # newest Sonnet alias is curated

    # Live catalog the API would actually return — no fable-5.
    live = ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]
    with patch.object(M, "_fetch_anthropic_models", return_value=live):
        result = M.provider_model_ids("anthropic")

    assert "claude-fable-5" in result
    assert "claude-sonnet-5" in result
    assert set(curated) <= set(result)


def test_anthropic_merge_dedupes_overlap_and_keeps_live_only():
    """Models in both lists appear once; live-only models are kept."""
    live = [
        "claude-opus-4-8",          # overlaps curated
        "claude-sonnet-4-6",        # overlaps curated
        "claude-future-9-99",       # live-only, not curated
    ]
    with patch.object(M, "_fetch_anthropic_models", return_value=live):
        result = M.provider_model_ids("anthropic")

    # No duplicates introduced by the merge.
    assert result.count("claude-opus-4-8") == 1
    # Live-only entry is preserved (discovery still works for unknown models).
    assert "claude-future-9-99" in result
    # A release newer than anything curated leads the list instead of trailing it.
    assert result[0] == "claude-future-9-99"


def test_anthropic_falls_back_to_curated_when_live_unavailable():
    """No creds / live failure -> curated list verbatim (alias still present)."""
    with patch.object(M, "_fetch_anthropic_models", return_value=None):
        result = M.provider_model_ids("anthropic")

    assert result == list(M._PROVIDER_MODELS["anthropic"])
    assert "claude-fable-5" in result


def test_merged_catalog_lists_newer_versions_first():
    """Every model sorts ahead of any model with a lower version number."""
    live = ["claude-sonnet-4-20250514", "claude-opus-4-5-20251101", "claude-haiku-9-1",
            "claude-opus-9-1", "claude-opus-4-8"]
    with patch.object(M, "_fetch_anthropic_models", return_value=live):
        result = M.provider_model_ids("anthropic")

    versions = [M._claude_newest_first_key(m)[:3] for m in result]
    assert versions == sorted(versions)
    # Same version: bigger tier first; a date suffix is not a minor version.
    assert result.index("claude-opus-9-1") < result.index("claude-haiku-9-1")
    assert result.index("claude-opus-4-5-20251101") < result.index("claude-sonnet-4-20250514")


def test_claude_cli_picker_uses_live_catalog():
    """The Claude Code CLI row surfaces models the signed-in account can reach."""
    live = ["claude-opus-9-1", "claude-sonnet-4-6"]
    with patch.object(M, "_fetch_anthropic_models", return_value=live):
        result = M.provider_model_ids("claude-cli")

    assert result[0] == "claude-opus-9-1"
    assert set(M._PROVIDER_MODELS["claude-cli"]) <= set(result)


def test_claude_cli_falls_back_to_curated_when_live_unavailable():
    with patch.object(M, "_fetch_anthropic_models", return_value=None):
        assert M.provider_model_ids("claude-cli") == list(M._PROVIDER_MODELS["claude-cli"])
