import { describe, expect, it } from "vitest";
import { composerContext, questionTarget } from "./composer-context";
import type { InboxItem } from "../live";

const card = (kind: string): InboxItem => ({ id: kind, kind, created: 1 });
describe("composer routing hints", () => {
  it("explains that the main composer answers the waiting question", () => {
    const context = composerContext([card("question")], true);
    expect(context.placeholder).toContain("Answer");
    expect(context.hint).toContain("your answer");
    expect(context.hint).toContain("Picked parts");
    expect(context.placeholder).not.toContain("reads this next");
  });
  it.each(["prototype", "requirements"])("makes %s comments an explicit request for changes", (kind) => {
    const context = composerContext([card(kind)], true);
    expect(context.hint).toContain("Sending requests changes");
    expect(context.hint).toContain("approval button");
  });
  it.each(["approval", "secret"])("keeps %s decisions in the card", (kind) => {
    expect(composerContext([card(kind)], true).hint).toContain("Use the cards above");
  });
  it("requires an explicit target when workers ask concurrent questions", () => {
    const inbox = [{ ...card("question"), id: "frontend" }, { ...card("question"), id: "backend" }];
    expect(questionTarget(inbox, "")).toBeUndefined();
    expect(questionTarget(inbox, "backend")).toBe("backend");
    expect(questionTarget(inbox, "already-answered")).toBeUndefined();
    expect(composerContext(inbox, true).hint).toContain("only to that worker");
    expect(composerContext(inbox, true).hint).not.toContain("cards above");
  });
  it("routes the remaining question without carrying an old worker selection", () => {
    expect(questionTarget([{ ...card("question"), id: "remaining" }, card("approval")], "old")).toBe("remaining");
    expect(questionTarget([card("approval")], "old")).toBeUndefined();
  });
});
