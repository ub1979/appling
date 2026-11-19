import type { AcceptanceStatus, CriterionStatus } from "../api";

export const STATUS_LABEL: Record<CriterionStatus, string> = {
  passed: "Passed",
  failed: "Failed",
  pending_owner: "Waiting on you",
  not_run: "Not verified",
};

export interface AcceptanceRow {
  id: string;
  requirement: string;
  description: string;
  live: boolean;
  status: CriterionStatus;
  stale: boolean;
  next: string;
  owner: string;
}

export function rows(status: AcceptanceStatus): AcceptanceRow[] {
  return status.criteria.filter(c => c.release === "1").map(c => {
    const r = status.results[c.id];
    return {
      id: c.id, requirement: c.requirement, description: c.description, live: c.live,
      status: r?.status ?? "not_run", stale: Boolean(r?.stale),
      next: r?.next_action ?? "", owner: r?.owner === "you" ? "You" : r?.owner === "builder" ? "Builder" : "",
    };
  });
}

/** One-line headline. Delivery is never claimed while anything is pending or unverified. */
export function headline(status: AcceptanceStatus): string {
  const list = rows(status);
  if (!list.length) return "No acceptance criteria yet.";
  const count = (s: CriterionStatus) => list.filter(r => r.status === s).length;
  if (status.phase === "implementation_verified" && count("pending_owner"))
    return `Implementation verified; live acceptance pending (${count("pending_owner")} waiting on you). Not delivered yet.`;
  if (status.phase === "delivered" && count("passed") === list.length) return `Delivered: all ${list.length} criteria passed.`;
  const parts = [`${count("passed")} of ${list.length} passed`];
  if (count("failed")) parts.push(`${count("failed")} failed`);
  if (count("pending_owner")) parts.push(`${count("pending_owner")} waiting on you`);
  if (count("not_run")) parts.push(`${count("not_run")} not verified`);
  return parts.join(" · ");
}

export function openSetup(status: AcceptanceStatus) {
  return status.prerequisites.filter(p => !p.done);
}
