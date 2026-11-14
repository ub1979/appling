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

    def tick(self, snapshot: dict, settings: dict | None = None, now: float | None = None) -> str | None:
        now = time.time() if now is None else now
        settings = settings if isinstance(settings, dict) else {}
        events, self.offset = self.store.read_events(self.offset)
        if snapshot.get("chat_id") != self.chat_id:
            self.chat_id = snapshot.get("chat_id")
            self.last_report = self.last_activity = None
            events = []
        for event in events:
            if event["type"] == "tool" and event.get("phase") == "start":
                self.last_activity = (event["ts"], event.get("name"))
            elif event["type"] == "helper" and event.get("event") == "tool":
                self.last_activity = (event["ts"], event.get("tool"))
        helpers = snapshot.get("helpers") or []
        if (settings.get("enabled") is False or snapshot.get("paused") or snapshot.get("inbox")
                or not (snapshot.get("running") or helpers)):
            self.last_report = now
            self.last_activity = None
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
        if snapshot.get("provider_statuses"):
            text = f"Status update: {who} {verb} waiting on an AI connection. Work is not finished."
        else:
            text = f"Status update: {who} {verb} still assigned to the work."
            if self.last_activity:
                timestamp, tool = self.last_activity
                action = {"write_file": "writing a file", "patch": "editing a file", "terminal": "running a command",
                          "read_file": "reading a file", "search_files": "searching project files",
                          "delegate_task": "assigning work to agents"}.get(tool, "using a tool")
                age = max(0, int(now - timestamp))
                text += f" Latest activity: {action}, {age // 60}m {age % 60}s ago."
                if age >= interval:
                    text += " No new tool activity has been recorded since then; it may be waiting for the AI."
            else:
                text += " No new tool activity has been recorded in this status window."
        # Display history only: never submit a turn or change cached model history.
        self.store.append_transcript([{"role": "assistant", "kind": "status", "content": text, "ts": now}])
        self.last_report = now
        self.store.append_event("status_update", text=text)
        return text
