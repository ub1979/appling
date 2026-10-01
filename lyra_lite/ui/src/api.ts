import type { InboxItem } from "./live";

declare global {
  interface Window {
    __LYRA_TOKEN__?: string;
  }
}

export const token = (): string => window.__LYRA_TOKEN__ ?? "";

export interface ProjectSummary {
  id: string;
  name: string;
  root: string;
  running: boolean;
  inbox: number;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  kind: "chat" | "system" | "auto";
}

export interface ProjectDetail {
  id: string;
  name: string;
  root: string;
  running: boolean;
  paused: boolean;
  keep_going: boolean;
  rules_outdated: boolean;
  watchdog: { gave_up?: boolean; count?: number };
  queue: { id: string; text: string; kind: string }[];
  turn: { id: string; text: string; kind: string } | null;
  turn_start_offset: number;
  inbox: InboxItem[];
  helpers: { id: string; goal: string; started: number | null }[];
  messages: ChatMessage[];
}

export interface MapPhase {
  name: string;
  status: string;
  state: "done" | "running" | "owner" | "blocked" | "pending";
  note: string;
}

export interface ProjectMap {
  exists: boolean;
  phases: MapPhase[];
  current_phase: string | null;
  updated: string | null;
}

export interface FolderListing {
  path: string;
  parent: string | null;
  folders: string[];
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: { "content-type": "application/json", "x-lyra-token": token() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { detail?: string }).detail ?? `Request failed (${res.status})`);
  return data as T;
}

export const api = {
  projects: () => call<{ projects: ProjectSummary[]; default_root: string }>("GET", "/api/projects"),
  addProject: (path: string, create: boolean) => call<ProjectDetail>("POST", "/api/projects", { path, create }),
  project: (id: string) => call<ProjectDetail>("GET", `/api/projects/${id}`),
  map: (id: string) => call<ProjectMap>("GET", `/api/projects/${id}/map`),
  send: (id: string, text: string) => call("POST", `/api/projects/${id}/messages`, { text }),
  answer: (id: string, item: string, answer: string) => call("POST", `/api/projects/${id}/inbox/${item}`, { answer }),
  settings: (id: string, body: Record<string, unknown>) => call("POST", `/api/projects/${id}/settings`, body),
  applyRules: (id: string) => call("POST", `/api/projects/${id}/apply-rules`),
  stop: (id: string) => call("POST", `/api/projects/${id}/stop`),
  newChat: (id: string) => call("POST", `/api/projects/${id}/new-chat`),
  folders: (path?: string) =>
    call<FolderListing>("GET", `/api/folders${path ? `?path=${encodeURIComponent(path)}` : ""}`),
};

export function streamUrl(id: string, offset: number): string {
  return `/api/projects/${id}/stream?offset=${offset}&token=${encodeURIComponent(token())}`;
}
