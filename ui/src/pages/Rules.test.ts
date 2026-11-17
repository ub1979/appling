import { afterEach, describe, expect, it, vi } from "vitest";
import { api, type ProjectDetail } from "../api";
import { applyUpdatedRules } from "./Studio";

afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

describe("applying updated rules", () => {
  it("waits for active work to stop before replacing the engine", async () => {
    vi.useFakeTimers();
    const stop = vi.spyOn(api, "stop").mockResolvedValue({ ok: true });
    const project = vi.spyOn(api, "project")
      .mockResolvedValueOnce({ running: true, helpers: [] } as unknown as ProjectDetail)
      .mockResolvedValueOnce({ running: false, helpers: [{}] } as unknown as ProjectDetail)
      .mockResolvedValue({ running: false, helpers: [] } as unknown as ProjectDetail);
    const apply = vi.spyOn(api, "applyRules").mockResolvedValue({ ok: true });
    const pending = applyUpdatedRules("project", true);
    await vi.advanceTimersByTimeAsync(0);
    expect(stop).toHaveBeenCalledWith("project");
    expect(apply).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(500);
    expect(apply).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(500);
    await pending;
    expect(project).toHaveBeenCalledTimes(3);
    expect(apply).toHaveBeenCalledWith("project");
  });
  it("applies immediately when idle", async () => {
    const stop = vi.spyOn(api, "stop");
    const apply = vi.spyOn(api, "applyRules").mockResolvedValue({ ok: true });
    await applyUpdatedRules("project", false);
    expect(stop).not.toHaveBeenCalled();
    expect(apply).toHaveBeenCalledWith("project");
  });
});
