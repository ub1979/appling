"""Token use, read from the project's activity file.

Lyra's own turns record counter deltas on ``turn_end``; each finished helper
records its totals on its ``helper`` complete event. "input" is fresh
(uncached) input; the full prompt is input + cache_read + cache_write.
"""

from __future__ import annotations

from lyra_lite.agents import LABELS, agent_for_goal
from lyra_lite.store import ProjectStore

KEYS = ("api_calls", "input", "cache_read", "cache_write", "output", "reasoning")


def _blank() -> dict:
    return {k: 0 for k in KEYS} | {"cost_usd": 0.0}


def _add(total: dict, usage: dict) -> None:
    for k in KEYS:
        try:
            total[k] += int(usage.get(k) or 0)
        except (TypeError, ValueError):
            pass
    try:
        total["cost_usd"] += float(usage.get("cost_usd") or 0)
    except (TypeError, ValueError):
        pass


def _finish(total: dict) -> dict:
    prompt = total["input"] + total["cache_read"] + total["cache_write"]
    total["prompt"] = prompt
    total["cached_pct"] = round(100 * total["cache_read"] / prompt) if prompt else 0
    total["cost_usd"] = round(total["cost_usd"], 4)
    return total


def summarise_usage(store: ProjectStore) -> dict:
    events, _ = store.read_events(0)
    lyra, agents, by_agent = _blank(), _blank(), {}
    for e in events:
        if e.get("type") == "turn_end" and isinstance(e.get("usage"), dict):
            _add(lyra, e["usage"])
        elif e.get("type") == "helper" and e.get("event") == "complete" and isinstance(e.get("usage"), dict):
            _add(agents, e["usage"])
            agent = agent_for_goal(str(e.get("goal") or "")) or "other"
            _add(by_agent.setdefault(agent, _blank()), e["usage"])
    total = _blank()
    _add(total, lyra)
    _add(total, agents)
    return {
        "lyra": _finish(lyra),
        "agents": _finish(agents),
        "total": _finish(total),
        "by_agent": [
            {"id": k, "label": LABELS.get(k, "Other agents"), **_finish(v)}
            for k, v in sorted(by_agent.items(), key=lambda kv: -(kv[1]["input"] + kv[1]["cache_read"]))
        ],
    }
