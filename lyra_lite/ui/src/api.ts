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
  engine: string;
  team: string[];
  updated: number;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  kind: "chat" | "system" | "auto";
}

export interface QueueItem {
  id: string;
  text: string;
  kind: string;
  display?: string;
}

export interface ProjectDetail {
  id: string;
  name: string;
  root: string;
  running: boolean;
  paused: boolean;
  keep_going: boolean;
  engine: string;
  engine_override: boolean;
  claude: { model?: string; base_url?: string };
  team: string[];
  style: string;
  profile: BuildProfile | null;
  models: Record<string, string>;
  rules_outdated: boolean;
  watchdog: { gave_up?: boolean; count?: number };
  queue: QueueItem[];
  turn: { id: string; text: string; kind: string; display?: string } | null;
  turn_start_offset: number;
  inbox: InboxItem[];
  helpers: { id: string; goal: string; started: number | null }[];
  messages: ChatMessage[];
}

export interface AiSettings {
  engine: string;
  hermes: { provider: string; model: string };
  claude: { model: string; base_url: string; route: string; has_token: boolean };
  anthropic_key: boolean;
}

export interface ModelOptions {
  providers: { slug: string; name: string; models: string[]; current: boolean }[];
  provider: string | null;
  model: string | null;
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
  markdown?: string;
}

export interface FolderListing {
  path: string;
  parent: string | null;
  folders: string[];
}

export interface Agent {
  id: string;
  label: string;
  description: string;
  required: boolean;
}

export interface StartStyle {
  id: string;
  name: string;
  description: string;
  accent: string;
  team: string[];
}

export interface Catalog {
  agents: Agent[];
  styles: StartStyle[];
  default_root: string;
}

export type BuildProfile = "personal" | "reusable" | "production";

export interface NewProject {
  path: string;
  create: boolean;
  team: string[];
  style: string;
  brief: string;
  profile: BuildProfile;
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
  projects: () => call<{ projects: ProjectSummary[]; default_root: string; version?: string }>("GET", "/api/projects"),
  catalog: () => call<Catalog>("GET", "/api/catalog"),
  addProject: (body: NewProject) => call<ProjectDetail>("POST", "/api/projects", body),
  project: (id: string) => call<ProjectDetail>("GET", `/api/projects/${id}`),
  usage: (id: string) => call<unknown>("GET", `/api/projects/${id}/usage`),
  preview: (id: string) => call<{ available: boolean; url: string | null }>("GET", `/api/projects/${id}/preview`),
  map: (id: string) => call<ProjectMap>("GET", `/api/projects/${id}/map`),
  send: (id: string, text: string) => call("POST", `/api/projects/${id}/messages`, { text }),
  answer: (id: string, item: string, answer: string) => call("POST", `/api/projects/${id}/inbox/${item}`, { answer }),
  team: (id: string, team: string[]) => call("POST", `/api/projects/${id}/team`, { team }),
  settings: (id: string, body: Record<string, unknown>) => call("POST", `/api/projects/${id}/settings`, body),
  settingsGet: () => call<AiSettings>("GET", "/api/settings"),
  settingsSave: (body: Record<string, unknown>) => call<AiSettings>("POST", "/api/settings", body),
  modelOptions: (refresh = false) => call<ModelOptions>("GET", `/api/settings/models${refresh ? "?refresh=true" : ""}`),
  modelSave: (provider: string, model: string, confirm: boolean) =>
    call<{ ok: boolean; confirm_required?: boolean; message?: string }>("POST", "/api/settings/model", { provider, model, confirm }),
  claudeCli: () => call<{ found: boolean; logged_in: boolean; method?: string; plan?: string }>("GET", "/api/settings/claude-cli"),
  engines: () => call<{ engines: { id: string; label: string }[]; anthropic_key: boolean }>("GET", "/api/engines"),
  applyRules: (id: string) => call("POST", `/api/projects/${id}/apply-rules`),
  stop: (id: string) => call("POST", `/api/projects/${id}/stop`),
  newChat: (id: string) => call("POST", `/api/projects/${id}/new-chat`),
  folders: (path?: string) =>
    call<FolderListing>("GET", `/api/folders${path ? `?path=${encodeURIComponent(path)}` : ""}`),
};

export function streamUrl(id: string, offset: number): string {
  return `/api/projects/${id}/stream?offset=${offset}&token=${encodeURIComponent(token())}`;
}

export const avatarUrl = (id: string): string => `/avatars/${id}.webp`;
