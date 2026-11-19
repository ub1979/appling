import { afterEach, expect, it, vi } from "vitest";
import { STATUS_INTERVAL, watchStatus } from "./build-status";

afterEach(() => vi.useRealTimers());
it("checks immediately and every five minutes, then stops when the page closes", async () => {
  vi.useFakeTimers(); const read = vi.fn().mockResolvedValue({ running: true }); const updated = vi.fn();
  const stop = watchStatus(read, updated, vi.fn());
  await vi.advanceTimersByTimeAsync(STATUS_INTERVAL - 1);
  expect(read).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(1);
  expect(read).toHaveBeenCalledTimes(2);
  expect(updated).toHaveBeenLastCalledWith({ running: true });
  stop(); await vi.advanceTimersByTimeAsync(STATUS_INTERVAL * 2);
  expect(read).toHaveBeenCalledTimes(2);
});
it("reports unavailable status rather than success and suppresses late replies after closing", async () => {
  vi.useFakeTimers(); const failed = vi.fn(); const updated = vi.fn();
  const stop = watchStatus(() => Promise.reject(new Error("offline")), updated, failed);
  await vi.advanceTimersByTimeAsync(1); expect(failed).toHaveBeenCalledOnce(); expect(updated).not.toHaveBeenCalled(); stop();
  let resolve!: (value: string) => void;
  const stopLate = watchStatus(() => new Promise<string>(r => { resolve = r; }), updated, failed);
  stopLate(); resolve("late"); await Promise.resolve(); expect(updated).not.toHaveBeenCalled();
});
