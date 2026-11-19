import { describe, expect, it } from "vitest";
import type { AcceptanceStatus } from "../api";
import { headline, openSetup, rows, setupNeededNow } from "./acceptance-view";

const base: AcceptanceStatus = {
  phase: "implementation_verified", derived: false, outcome: "pending_owner",
  criteria: [
    { id: "AC-FR-1-1", requirement: "FR-1", description: "Shows 42", release: "1", live: false, prerequisites: [] },
    { id: "AC-FR-2-1", requirement: "FR-2", description: "Posts", release: "1", live: true, prerequisites: ["P-login"] },
    { id: "AC-FR-3-1", requirement: "FR-3", description: "Later", release: "later", live: false, prerequisites: [] },
  ],
  prerequisites: [{ id: "P-login", kind: "account", description: "Sign in", needed_at: "verification", done: false }],
  results: {
    "AC-FR-1-1": { status: "passed" },
    "AC-FR-2-1": { status: "pending_owner", owner: "you", next_action: "Sign in" },
  },
};

describe("acceptance view", () => {
  it("shows only release-1 criteria with owners and next actions", () => {
    const list = rows(base);
    expect(list.map(r => r.id)).toEqual(["AC-FR-1-1", "AC-FR-2-1"]);
    expect(list[1]).toMatchObject({ status: "pending_owner", owner: "You", next: "Sign in", live: true });
  });

  it("never calls implementation-verified work delivered", () => {
    expect(headline(base)).toContain("live acceptance pending");
    expect(headline(base)).toContain("Not delivered");
    expect(openSetup(base).map(p => p.id)).toEqual(["P-login"]);
    expect(setupNeededNow(base)).toBe(true);
  });

  it("counts unverified and stale results instead of hiding them", () => {
    const changed = { ...base, phase: "qa", results: { "AC-FR-1-1": { status: "not_run" as const, stale: true } } };
    expect(headline(changed)).toBe("0 of 2 passed · 2 not verified");
    expect(rows(changed)[0].stale).toBe(true);
  });

  it("reports delivery only when every criterion passed", () => {
    const done = { ...base, phase: "delivered", results: { "AC-FR-1-1": { status: "passed" as const }, "AC-FR-2-1": { status: "passed" as const } } };
    expect(headline(done)).toBe("Delivered: all 2 criteria passed.");
  });

  it("says plainly that nothing is needed before QA has run", () => {
    const fresh = { ...base, phase: "build", results: {} };
    expect(headline(fresh)).toBe("2 checks, not run yet. Independent QA runs them after coding finishes. Nothing is needed from you now.");
    expect(setupNeededNow(fresh)).toBe(false);
  });
});
