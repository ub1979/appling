export type BlockState = "planned" | "building" | "tested" | "blocked" | "later" | "merged" | "failed";

export interface BlockRow {
  id: string;
  name: string;
  purpose: string;
  status: BlockState | string;
  label: string;
  reason?: string | null;
  library?: string | null;
  depends_on: string[];
  runtime: string;
  agent: boolean;
}

export interface BlocksStatus {
  exists: boolean;
  phase: string;
  blocks: BlockRow[];
  body?: string;
  approved?: boolean;
}

const DONE = new Set(["tested", "merged"]);

/** Plain one-line summary of the blocks for the owner. */
export function blocksHeadline(status: BlocksStatus): string {
  if (!status.exists || !status.blocks.length) return "";
  const list = status.blocks;
  const count = (fn: (b: BlockRow) => boolean) => list.filter(fn).length;
  const done = count(b => DONE.has(b.status));
  const building = count(b => b.status === "building" || b.status === "failed");
  const waiting = count(b => b.status === "blocked");
  const later = count(b => b.status === "later");
  if (!status.approved && status.phase === "blocks_review") return `${list.length} blocks planned. Review the block plan to start building.`;
  const parts = [`${done} of ${list.length - later} blocks done`];
  if (building) parts.push(`${building} being built`);
  if (waiting) parts.push(building ? `${waiting} stuck (you'll be asked when the others finish)` : `${waiting} need${waiting === 1 ? "s" : ""} your decision`);
  if (later) parts.push(`${later} left for later`);
  return parts.join(" · ");
}

export function blockLine(row: BlockRow, othersBuilding = false): string {
  const from = row.library ? ` · from library ${row.library}` : "";
  if (row.status === "blocked")
    return othersBuilding
      ? `Stuck · Appling will ask you what to do when the blocks still building finish${row.reason ? ` (${row.reason.slice(0, 160)})` : ""}`
      : `Needs your decision${row.reason ? `: ${row.reason.slice(0, 200)}` : ""}`;
  return `${row.label}${row.agent ? " · agent working" : ""}${from}`;
}

/** Map a stage's controller state to what each team member is doing. */
export interface MapRow { name: string; state: string; role?: string; stage?: string }

export function agentStatus(role: string, rows: MapRow[], running: boolean): { line: string; working: boolean } {
  const mine = rows.filter(r => r.role === role);
  if (!mine.length) return { line: "Helps when needed", working: false };
  const active = mine.find(r => r.state === "running" || r.state === "owner" || r.state === "blocked");
  if (active) {
    if (active.state === "owner") return { line: "Waiting on you", working: false };
    if (active.state === "blocked") return { line: "Paused", working: false };
    return { line: running ? `Working · ${active.name}` : `Next · ${active.name}`, working: running };
  }
  if (mine.every(r => r.state === "done")) return { line: "Done ✓", working: false };
  return { line: "Not started yet", working: false };
}
