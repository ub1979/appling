/**
 * Resize frames sent when the chat socket opens.
 *
 * A refresh reattaches to the same keep-alive TUI and replays only the tail of
 * its output (a 1 MB ring buffer). After a long session that tail starts
 * mid-frame, so the rebuilt screen can lack the composer prompt — and resizing
 * to the size the PTY already has sends no SIGWINCH, so an idle TUI never
 * repaints and Send stayed disabled behind "Lyra is still starting".
 * Stepping one row down and back forces a full repaint at the real size.
 */
export function ptyResizeFrame(cols: number, rows: number): string {
  return `\x1b[RESIZE:${cols};${rows}]`;
}

export function ptyRepaintFrames(cols: number, rows: number): string[] {
  const height = Math.max(2, rows);
  return [ptyResizeFrame(cols, height - 1), ptyResizeFrame(cols, height)];
}
