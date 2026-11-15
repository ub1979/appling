"""Owner-visible activity summaries; never part of the model conversation."""

from __future__ import annotations

import math
import time

from lyra_lite.agents import LABELS, agent_for_goal


class StatusUpdates:
    def __init__(self, store):
        self.store = store
        self.offset = store.events_size()
        self.chat_id = store.state().get("chat_id")
        self.last_report = None
        self.last_activity = None
        self.last_heartbeat = None
        self.workers = {}

    def tick(self, snapshot: dict, settings: dict | None = None, now: float | None = None) -> str | None:
        now = time.time() if now is None else now
        settings = settings if isinstance(settings, dict) else {}
        events, self.offset = self.store.read_events(self.offset)
        if snapshot.get("chat_id") != self.chat_id:
            self.chat_id = snapshot.get("chat_id")
            self.last_report = self.last_activity = None
            self.last_heartbeat = None
            self.workers.clear()
            events = []
        for event in events:
            if event["type"] == "tool" and event.get("phase") == "start":
                self.last_activity = (event["ts"], event.get("name"))
            elif event["type"] == "helper" and event.get("event") == "tool":
                self.last_activity = (event["ts"], event.get("tool"))
            if event["type"] == "helper":
                sid = event.get("subagent_id")
                kind = event.get("event")
                if kind == "start" and sid:
                    self.workers[sid] = {"parent_id": event.get("parent_id"), "returned": False}
                elif kind == "complete" and sid in self.workers:
                    self.workers[sid]["returned"] = True
                elif kind == "progress":
                    self.last_heartbeat = event["ts"]
        helpers = snapshot.get("helpers") or []
        if (settings.get("enabled") is False or snapshot.get("paused") or snapshot.get("inbox")
                or not (snapshot.get("running") or helpers)):
            self.last_report = now
            self.last_activity = None
            self.last_heartbeat = None
            self.workers.clear()
            return None
        try:
            interval = float(settings.get("interval_seconds", 300))
            if not math.isfinite(interval) or interval <= 0:
                interval = 300.0
        except (TypeError, ValueError):
            interval = 300.0
        if self.last_report is None:
            starts = [h["started"] for h in helpers if isinstance(h.get("started"), (int, float))]
            started = (snapshot.get("turn") or {}).get("started")
            if isinstance(started, (int, float)):
                starts.append(started)
            self.last_report = min(now, min(starts, default=now))
        if now - self.last_report < interval:
            return None
        names = list(dict.fromkeys(LABELS.get(agent_for_goal(h.get("goal", "")), "Project") for h in helpers))
        who = ", ".join(names) + (" agents" if len(names) > 1 else " agent") if names else "Appling"
        verb = "are" if len(names) > 1 else "is"
        text = f"Status update: {who} {verb} still assigned to the work."
        if len(helpers) > 1:
            text += f" {len(helpers)} workers are currently assigned."
        # Count the current lead's descendants, not finished waves from earlier
        # leads. Returned results are not a claim of successful integration.
        parents = {sid for sid, row in self.workers.items() if not row["returned"]}
        nested = [row for row in self.workers.values() if row["parent_id"] in parents]
        active = sum(not row["returned"] for row in nested)
        if active:
            text += f" The lead is waiting for {active} subagent{'s' if active != 1 else ''}; {len(nested) - active} returned results."
        elif nested:
            text += f" All {len(nested)} subagents have returned results; the lead is handling the next step."
        statuses = snapshot.get("provider_statuses") or {}
        if statuses:
            text += f" Reported AI connection issue: {len(statuses)} agent{'s' if len(statuses) != 1 else ''} waiting on an AI connection."
        if self.last_activity:
            timestamp, tool = self.last_activity
            action = {"write_file": "writing a file", "patch": "editing a file", "terminal": "running a command",
                      "read_file": "reading a file", "search_files": "searching project files",
                      "delegate_task": "assigning work to agents"}.get(tool, "using a tool")
            age = max(0, int(now - timestamp))
            text += f" Latest activity: {action}, {age // 60}m {age % 60}s ago."
            if age >= interval:
                text += " No new tool activity has been recorded since then."
        else:
            text += " No new tool activity has been recorded in this status window."
        if self.last_heartbeat is not None:
            age = max(0, int(now - self.last_heartbeat))
            text += f" Last agent heartbeat: {age // 60}m {age % 60}s ago."
        # Display history only: never submit a turn or change cached model history.
        self.store.append_transcript([{"role": "assistant", "kind": "status", "content": text, "ts": now}])
        self.last_report = now
        self.store.append_event("status_update", text=text)
        return text
