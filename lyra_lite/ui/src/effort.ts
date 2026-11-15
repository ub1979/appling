// How hard the model thinks before answering.

export interface EffortLevel {
  id: string;
  label: string;
}

// What Appling uses when nothing is chosen (lyra_lite/settings.py DEFAULT_EFFORT).
export const DEFAULT_EFFORT = "medium";

export const EFFORT_LEVELS: EffortLevel[] = [
  { id: "low", label: "Low — fastest and cheapest, for small changes" },
  { id: "medium", label: "Medium — balanced" },
  { id: "high", label: "High — thinks more, good for most building" },
  { id: "xhigh", label: "Extra high — best for hard coding work" },
];

export const CODEX_EFFORT_LEVELS = EFFORT_LEVELS;

export const DEFAULT_EFFORT_LABEL = `Default — ${DEFAULT_EFFORT}`;

export function effortName(id: string): string {
  return id === "xhigh" ? "extra high" : id || DEFAULT_EFFORT;
}
