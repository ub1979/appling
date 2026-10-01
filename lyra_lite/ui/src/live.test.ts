import { describe, expect, it } from "vitest";
import { activeHelpers, applyEvent, emptyLive, type LyraEvent } from "./live";

const feed = (events: Partial<LyraEvent>[]) =>
  events.reduce((s, e, i) => applyEvent(s, { ts: i, type: "", ...e } as LyraEvent), emptyLive());

describe("applyEvent", () => {
  it("builds the streaming reply and clears it at turn end", () => {
    const mid = feed([
      { type: "queued", item: { id: "t1", text: "hi" } },
      { type: "turn_start", turn: "t1", text: "hi", kind: "user" },
      { type: "delta", turn: "t1", text: "Hel" },
      { type: "delta", turn: "t1", text: "lo" },
    ]);
    expect(mid.queued).toEqual([]);
    expect(mid.turn?.reply).toBe("Hello");
    const done = applyEvent(mid, { ts: 9, type: "turn_end", turn: "t1", status: "done", checkpoint: "abc" });
    expect(done.turn).toBeNull();
    expect(done.turnsEnded).toBe(1);
    expect(done.activity.at(-1)?.text).toMatch(/Saved/);
  });

  it("replaying the same events does not duplicate inbox items or queue entries", () => {
    const events: Partial<LyraEvent>[] = [
      { type: "queued", item: { id: "t2", text: "x" } },
      { type: "inbox", item: { id: "approval-1", kind: "approval", created: 1 } },
    ];
    const twice = feed([...events, ...events]);
    expect(twice.inbox).toHaveLength(1);
    expect(twice.queued).toHaveLength(1);
    expect(applyEvent(twice, { ts: 3, type: "inbox_closed", id: "approval-1" }).inbox).toHaveLength(0);
  });

  it("tracks helpers from start to finish", () => {
    const running = feed([
      { type: "helper", event: "start", subagent_id: "a", goal: "Build login" },
      { type: "helper", event: "tool", subagent_id: "a", tool: "write_file" },
    ]);
    expect(activeHelpers(running).map((h) => h.lastTool)).toEqual(["Wrote a file"]);
    const finished = applyEvent(running, { ts: 5, type: "helper", event: "complete", subagent_id: "a", status: "completed" });
    expect(activeHelpers(finished)).toHaveLength(0);
    expect(finished.activity.at(-1)?.tone).toBe("done");
  });

  it("reports a crashed turn as a problem", () => {
    const s = feed([
      { type: "turn_start", turn: "t", text: "go", kind: "user" },
      { type: "turn_end", turn: "t", status: "error", error: "provider down" },
    ]);
    expect(s.lastProblem).toBe("provider down");
  });
});
