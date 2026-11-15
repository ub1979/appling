import { describe, expect, it } from "vitest";
import { DEFAULT_EFFORT, EFFORT_LEVELS, effortName } from "./effort";

describe("effort levels", () => {
  it("the default is one of the offered levels and never above high", () => {
    const ids = EFFORT_LEVELS.map((l) => l.id);
    expect(ids).toContain(DEFAULT_EFFORT);
    expect(ids.indexOf(DEFAULT_EFFORT)).toBeLessThanOrEqual(ids.indexOf("high"));
  });

  it("an unset choice reads as the default", () => {
    expect(effortName("")).toBe(DEFAULT_EFFORT);
    expect(effortName("xhigh")).toBe("extra high");
  });
});
