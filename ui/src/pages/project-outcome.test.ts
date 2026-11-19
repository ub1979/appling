import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { ProjectDetail, TaskWorker } from "../api";
import { BlockedWork, currentBlockedWorkers, projectIsDelivered } from "./project-outcome";

const project = (patch: Partial<ProjectDetail> = {}) => ({ phase: "build", running: false,
  paused: true, review_pending: false, inbox: [], queue: [], turn: null,
  tasks: [{ id: "ui", status: "pending" }], task_workers: [], ...patch });
const worker = (patch: Partial<TaskWorker> = {}): TaskWorker => ({ id: "w1", task_id: "ui",
  role: "sw-developer", status: "blocked", goal: "Build UI", workspace: "/tmp/retained",
  error: "Host route is missing", ...patch });

describe("controller delivery authority", () => {
  it.each(["requirements", "plan_review", "build", "qa", "security"])("never announces %s as delivered", phase => {
    expect(projectIsDelivered(project({ phase, paused: false, tasks: [{ id: "ui", status: "done" }] }))).toBe(false);
  });
  it("announces only the idle delivered controller state", () => {
    const delivered = project({ phase: "delivered", paused: false, tasks: [{ id: "ui", status: "done" }] });
    expect(projectIsDelivered(delivered)).toBe(true);
    for (const patch of [{ running: true }, { paused: true }, { review_pending: true },
      { tasks: [{ id: "ui", status: "pending" }] }, { queue: [{ id: "q", text: "fix", kind: "user" }] },
      { turn: { id: "t", text: "fix", kind: "user" } }, { inbox: [{ id: "i", kind: "approval", created: 1 }] }]) {
      expect(projectIsDelivered({ ...delivered, ...patch })).toBe(false);
    }
  });
});

describe("retained blockers", () => {
  it("shows a specific blocker after a fresh load without event history", () => {
    const workers = currentBlockedWorkers(project({ task_workers: [worker()] }));
    const html = renderToStaticMarkup(createElement(BlockedWork, { workers, running: false }));
    expect(html).toContain("Work needs attention");
    expect(html).toContain("Host route is missing");
    expect(html).toContain("checkpoints are saved");
    expect(html).not.toContain("Other eligible work continues");
  });
  it("distinguishes ongoing parallel work and escapes reported text", () => {
    const html = renderToStaticMarkup(createElement(BlockedWork, { running: true,
      workers: [worker({ error: "<script>unsafe</script>", result: { blockers: [
        { kind: "integration", detail: "Missing route", requires_tasks: ["host"] }] } })] }));
    expect(html).toContain("Other eligible work continues");
    expect(html).toContain("Requires host");
    expect(html).not.toContain("<script>");
  });
  it("does not carry old attempts or removed tasks into a new plan", () => {
    expect(currentBlockedWorkers(project({ task_workers: [worker(), worker({ id: "w2", status: "integrated" })] }))).toEqual([]);
    expect(currentBlockedWorkers(project({ tasks: [], task_workers: [worker()] }))).toEqual([]);
    expect(currentBlockedWorkers(project({ tasks: [{ id: "ui", status: "done" }], task_workers: [worker()] }))).toEqual([]);
    expect(currentBlockedWorkers(project({ phase: "plan_review", task_workers: [worker()] }))).toEqual([]);
  });
  it("keeps the blocked UI usable when a model returns malformed optional diagnostics", () => {
    const malformed = JSON.parse('{"summary":{},"blockers":[null,{"kind":5},{"kind":"integration","detail":"Missing route","requires_tasks":{}}]}');
    const html = renderToStaticMarkup(createElement(BlockedWork, { running: false,
      workers: [worker({ error: null, result: malformed })] }));
    expect(html).toContain("Missing route");
    expect(html).toContain("Inspect the retained worker handoff");
  });
});
