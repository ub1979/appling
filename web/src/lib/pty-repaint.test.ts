import { describe, expect, it } from "vitest";
import { ptyRepaintFrames } from "./pty-repaint";

describe("ptyRepaintFrames", () => {
  it("changes the size and ends on the real size, so an idle TUI repaints", () => {
    const frames = ptyRepaintFrames(120, 40);
    expect(frames).toHaveLength(2);
    expect(frames[0]).not.toBe(frames[1]);
    expect(frames[frames.length - 1]).toBe("\x1b[RESIZE:120;40]");
  });

  it("never asks for a zero-row terminal", () => {
    expect(ptyRepaintFrames(80, 1)[0]).toBe("\x1b[RESIZE:80;1]");
    expect(ptyRepaintFrames(80, 0)[1]).toBe("\x1b[RESIZE:80;2]");
  });
});
