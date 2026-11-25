import { describe, expect, it } from "vitest";
import { agentStatus, blockLine, blocksHeadline, type BlocksStatus } from "./blocks-view";

const base: BlocksStatus = {
  exists: true, phase: "blocks_build", approved: true, blocks: [
    { id: "notifier", name: "Telegram notifier", purpose: "", status: "tested", label: "Tested", depends_on: [], runtime: "in-process", agent: false },
    { id: "poster", name: "Social poster", purpose: "", status: "blocked", label: "Needs a decision", reason: "needs the real site", depends_on: [], runtime: "in-process", agent: false },
    { id: "speech", name: "Speech", purpose: "", status: "building", label: "Building", depends_on: [], runtime: "service", agent: true },
    { id: "meet", name: "Meeting bot", purpose: "", status: "later", label: "Left for later", depends_on: [], runtime: "in-process", agent: false },
  ],
};

describe("blocks view", () => {
  it("summarises blocks in plain words", () => {
    expect(blocksHeadline(base)).toBe("1 of 3 blocks done · 1 being built · 1 stuck (you'll be asked when the others finish) · 1 left for later");
    expect(blocksHeadline({ ...base, blocks: base.blocks.filter(b => b.status !== "building") })).toBe("1 of 2 blocks done · 1 needs your decision · 1 left for later");
    // A block the main builder is finishing step by step is still being built, not waiting on the owner.
    const stepByStep = base.blocks.map(b => b.id === "poster" ? { ...b, status: "serial", label: "Being built step by step" } : b);
    expect(blocksHeadline({ ...base, blocks: stepByStep })).toBe("1 of 3 blocks done · 2 being built · 1 left for later");
    expect(blockLine(stepByStep[1])).toBe("Being built step by step");
    expect(blocksHeadline({ ...base, approved: false, phase: "blocks_review" })).toBe("4 blocks planned. Review the block plan to start building.");
  });

  it("explains blocked blocks and library origin", () => {
    expect(blockLine(base.blocks[1])).toBe("Needs your decision: needs the real site");
    expect(blockLine(base.blocks[1], true)).toContain("Appling will ask you what to do when the blocks still building finish");
    expect(blockLine({ ...base.blocks[0], library: "notifier@v1" })).toBe("Tested · from library notifier@v1");
    expect(blockLine(base.blocks[2])).toBe("Building · agent working");
  });

  it("derives each agent's status from the controller map, not chat text", () => {
    const rows = [
      { name: "Requirements", state: "done", role: "req-engineer" },
      { name: "Building blocks", state: "running", role: "sw-developer" },
      { name: "Merging into the app", state: "pending", role: "sw-developer" },
      { name: "Quality assurance", state: "pending", role: "qa-engineer" },
    ];
    expect(agentStatus("req-engineer", rows, true)).toEqual({ line: "Done ✓", working: false });
    expect(agentStatus("sw-developer", rows, true)).toEqual({ line: "Working · Building blocks", working: true });
    expect(agentStatus("qa-engineer", rows, true).line).toBe("Not started yet");
    expect(agentStatus("ux-writer", rows, true).line).toBe("Helps when needed");
    expect(agentStatus("sw-developer", [{ name: "Block plan", state: "owner", role: "sw-developer" }], false).line).toBe("Waiting on you");
  });
});
