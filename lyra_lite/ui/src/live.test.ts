import { describe, expect, it } from "vitest";
import { activeHelpers, applyEvent, emptyLive, type LyraEvent } from "./live";

const feed = (events: Partial<LyraEvent>[]) =>
  events.reduce((s, e, i) => applyEvent(s, { ts: i, type: "", ...e } as LyraEvent), emptyLive());

describe("applyEvent", () => {
  it("moves completed commentary from streaming text to the saved conversation", () => {
    const state = feed([
      { type: "turn_start", turn: "t", text: "Build" },
      { type: "delta", text: "Here is the draft." },
      { type: "interim", text: "Here is the draft.", already_streamed: true },
    ]);
    expect(state.turn?.reply).toBe("");
    expect(state.conversationChanges).toBe(1);
    expect(applyEvent(state, { ts: 9, type: "delta", text: "Next step" }).turn?.reply).toBe("Next step");
  });
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

  it("signals a refresh whenever an agent starts, ends or reports", () => {
    const s = feed([
      { type: "helper", event: "start", subagent_id: "a", goal: "g" },
      { type: "helper", event: "tool", subagent_id: "a", tool: "patch" },
      { type: "helper", event: "reported", subagent_id: "d1", goal: "g", status: "completed" },
    ]);
    expect(s.helperChanges).toBe(2);
    expect(s.activity.at(-1)?.text).toMatch(/report arrived/);
  });

  it("reports a crashed turn as a problem", () => {
    const s = feed([
      { type: "turn_start", turn: "t", text: "go", kind: "user" },
      { type: "turn_end", turn: "t", status: "error", error: "provider down" },
    ]);
    expect(s.lastProblem).toBe("provider down");
  });

  it("does not bring back a problem from before Appling restarted", () => {
    const old = [
      { ts: 10, type: "turn_start", turn: "t", text: "go", kind: "user" },
      { ts: 11, type: "turn_end", turn: "t", status: "error", error: "provider down" },
      { ts: 12, type: "problem", text: "could not save" },
    ] as LyraEvent[];
    const replayed = old.reduce(applyEvent, emptyLive(50));
    expect(replayed.lastProblem).toBeNull();
    expect(replayed.turnsEnded).toBe(1);
    const fresh = applyEvent(replayed, { ts: 60, type: "turn_end", turn: "u", status: "crashed" });
    expect(fresh.lastProblem).toMatch(/hit a problem/);
  });
});

import { asksForApproval } from "./pages/Studio";

describe("asksForApproval", () => {
  it("shows the Approve button only when Appling asks for approval", () => {
    expect(asksForApproval("Here is the summary. Do you approve these requirements?")).toBe(true);
    expect(asksForApproval("Options: Approve / Change / Skip")).toBe(true);
    expect(asksForApproval("Your approval is already recorded, so I won't ask again.")).toBe(false);
    expect(asksForApproval("Approved—I have your go-ahead. The planning agent is still working.")).toBe(false);
    expect(asksForApproval("I approved the plan. Which colour do you prefer?")).toBe(false);
  });
});

import { teamProposalForText } from "./pages/Studio";

describe("conversation feedback", () => {
  it("retains the source and display text of queued agent reports", () => {
    const s = feed([{ type: "queued", item: { id: "report", kind: "helper_done", text: "[ASYNC DELEGATION BATCH COMPLETE]", display: "Requirements report" } }]);
    expect(s.queued[0].kind).toBe("helper_done");
    expect(s.queued[0].display).toBe("Requirements report");
  });

  it("refreshes the saved conversation after an inbox answer", () => {
    const s = feed([{ type: "inbox_closed", id: "question-1", status: "answered", answer: "PostgreSQL" }]);
    expect(s.answersChanged).toBe(1);
  });

  it("offers a team editor when the reply requests confirmation without a marker", () => {
    const agents = [
      { id: "req-engineer", label: "Requirements", description: "", required: true },
      { id: "ui-designer", label: "Design", description: "", required: false },
      { id: "qa-engineer", label: "Quality assurance", description: "", required: false },
    ];
    expect(teamProposalForText("Confirm the recommended team in the panel. Design and QA will help.", agents, ["req-engineer"]))
      .toEqual(["req-engineer", "ui-designer", "qa-engineer", "task-planner"]);
    expect(teamProposalForText("Your team was confirmed.", agents, [])).toBeNull();
  });
});

import { agentTaskDescription } from "./pages/Studio";

it("distinguishes discovery from a prototype creation task", () => {
  expect(agentTaskDescription("req-engineer: Provide an advisory review and prerequisite discovery. Summarize prototype requirements."))
    .toBe("Checking requirements and available tools");
  expect(agentTaskDescription("req-engineer: Support requirements by producing ONLY the interactive requirements prototype. Create prototypes/index.html."))
    .toBe("Creating and checking your clickable prototype");
});

it("labels the pre-approval walkthrough as prototype work", () => {
  expect(agentTaskDescription("req-engineer: Create ONLY the pre-approval clickable requirements walkthrough at prototypes/index.html."))
    .toBe("Creating and checking your clickable prototype");
});

it("removes only messages delivered to a waiting question from the queue", () => {
  const queued = feed([
    { type: "queued", item: { id: "feedback", text: "Inset the arrow" } },
    { type: "queued", item: { id: "report", text: "Agent handoff", kind: "helper_done" } },
  ]);
  const answered = applyEvent(queued, { type: "queue_consumed", ts: 4, ids: ["feedback"] });
  expect(answered.queued.map((q) => q.id)).toEqual(["report"]);
});
