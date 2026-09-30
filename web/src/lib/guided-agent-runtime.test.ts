import { describe, expect, it } from "vitest";
import {
  formatGuidedTokens,
  guidedEventMayRelabel,
  guidedUsageTotal,
  markGuidedWorkerStopping,
  normalizeGuidedUsage,
  updateGuidedWorkers,
} from "./guided-agent-runtime";

describe("guided agent runtime", () => {
  it("normalizes parent usage without combining cached and fresh input", () => {
    const usage = normalizeGuidedUsage({
      model: "gpt-5.6-sol",
      input: 1200,
      cache_read: 9000,
      output: 300,
      reasoning: 40,
      calls: 3,
    });

    expect(usage).toMatchObject({
      model: "gpt-5.6-sol",
      input: 1200,
      cacheRead: 9000,
      output: 300,
      calls: 3,
    });
    expect(guidedUsageTotal(usage)).toBe(10_540);
  });

  it("updates one live worker from heartbeat through completion", () => {
    const running = updateGuidedWorkers(
      [],
      "subagent.progress",
      {
        subagent_id: "sa-1",
        display_label: "Development",
        model: "claude-opus-4-6",
        input_tokens: 40_000,
        cache_read_tokens: 120_000,
        api_calls: 5,
      },
      1000,
    );
    const completed = updateGuidedWorkers(
      running,
      "subagent.complete",
      {
        subagent_id: "sa-1",
        status: "completed",
        output_tokens: 2500,
        api_calls: 7,
      },
      2000,
    );

    expect(completed[0]).toMatchObject({
      id: "sa-1",
      label: "Development",
      model: "claude-opus-4-6",
      input: 40_000,
      cacheRead: 120_000,
      output: 2500,
      calls: 7,
      status: "completed",
    });
  });

  it("marks active workers as stopping without hiding them", () => {
    const workers = updateGuidedWorkers(
      [],
      "subagent.start",
      { subagent_id: "sa-2", task_index: 1 },
      1000,
    );
    expect(markGuidedWorkerStopping(workers)[0].status).toBe("stopping");
  });

  it("formats compact token counts", () => {
    expect(formatGuidedTokens(950)).toBe("950");
    expect(formatGuidedTokens(12_500)).toBe("12.5K");
    expect(formatGuidedTokens(2_550_000)).toBe("2.55M");
  });

  it("names a helper from its brief, not from each step or from Lyra's own tools", () => {
    for (const type of ["subagent.spawn_requested", "subagent.start"]) {
      expect(guidedEventMayRelabel(type)).toBe(true);
    }
    // Lyra's own tool calls stay Lyra's, even when they touch requirements.md.
    for (const type of ["tool.start", "subagent.tool", "subagent.progress", "subagent.thinking", "tool.progress"]) {
      expect(guidedEventMayRelabel(type)).toBe(false);
    }
  });

  it("keeps a worker's label when a later event carries none", () => {
    const started = updateGuidedWorkers(
      [],
      "subagent.start",
      { subagent_id: "a", goal: "Build it", display_label: "Development" },
      1,
    );
    const progressed = updateGuidedWorkers(
      started,
      "subagent.progress",
      { subagent_id: "a", text: "running pytest", display_label: undefined },
      2,
    );
    expect(progressed[0].label).toBe("Development");
  });
});
