import type { InboxItem, ProviderStatus } from "./live";

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
  active?: boolean;
  role: "user" | "assistant";
  content: string;
  kind: "chat" | "system" | "auto" | "question" | "answer" | "status" | "progress";
}

export interface QueueItem {
  id: string;
  text: string;
  kind: string;
  display?: string;
}

export interface ProjectDetail {
  phase?: string;
  execution_mode?: "direct" | "planned" | "blocks";
  id: string;
  name: string;
  root: string;
  running: boolean;
  paused: boolean;
  keep_going: boolean;
  engine: string;
  engine_override: boolean;
  engine_locked: boolean;
  team: string[];
  style: string;
  profile: BuildProfile | null;
  models: Record<string, string>;
  rules_outdated: boolean;
  chat_id: string;
  active_update: { revision: number; branch: string | null } | null;
  update_available: boolean;
  next_revision: number;
  review_pending: boolean;
  requirements_started: boolean;
  watchdog: { gave_up?: boolean; count?: number };
  queue: QueueItem[];
  turn: { id: string; text: string; kind: string; display?: string } | null;
  turn_start_offset: number;
  started_at: number;
  last_completed_turn?: string;
  provider_statuses?: Record<string, ProviderStatus>;
  inbox: InboxItem[];
  review_recovery?: InboxItem | null;
  helpers: { id: string; role?: string; goal: string; started: number | null }[];
  task_workers?: TaskWorker[];
  tasks?: { id: string; status: string }[];
  messages: ChatMessage[];
}

export interface TaskWorker {
  id: string;
  task_id: string;
  role: string;
  status: "pending" | "running" | "completed" | "blocked" | "integrating" | "integrated" | "conflict" | "interrupted" | "retained";
  workspace: string;
  goal: string;
  error?: string | null;
  result?: { summary?: string; blockers?: { kind: string; detail: string; requires_tasks?: string[] }[] } | null;
}

export interface ModelSelection {
  provider: string;
  model: string;
  effort?: string;
}

export interface AgentModelSetting {
  id: string;
  label: string;
  default: ModelSelection | null;
  selection: ModelSelection | null;
}

export interface AiConnection {
  engine: string;
  label: string;
  base_url?: string;
  api_key_env?: string;
  models?: string[];
}

export interface AiSettings {
  connections: Record<string, AiConnection>;
  installed: { id: string; label: string; installed: boolean }[];
  parallel_work: { max_workers: number; maximum: number; default: number; active: number; agents_per_project?: number; agents_maximum?: number };
  engine: string;
  hermes: { provider: string; model: string };
  hermes_effort: { effort: string; effective: string; overridden: boolean };
  about_me: string;
  agent_models: AgentModelSetting[];
}

export interface ModelOptions {
  providers: { slug: string; name: string; models: string[]; current: boolean; default_model?: string | null; status?: { state: string; message: string; source: string } }[];
  provider: string | null;
  model: string | null;
}

export interface ConnectionTestResult {
  ok: boolean;
  state: string;
  message: string;
  model: string;
  latency_ms: number;
}

export type PhoneChannel = "telegram" | "whatsapp";

export interface PhoneConnection {
  enabled: boolean;
  configured: boolean;
  connected: boolean;
  paired: boolean;
  message: string;
  bot_username?: string;
  token_env?: string;
  pairing_code?: string;
  pairing_url?: string;
  qr?: string;
  expires_at?: number;
}

export interface PhoneSettings {
  telegram: PhoneConnection;
  whatsapp: PhoneConnection;
}

export interface PhoneAction {
  action: "configure" | "pair" | "disconnect" | "test";
  enabled?: boolean;
  bot_token?: string;
  token_env?: string;
}

export interface MapPhase {
  name: string;
  status: string;
  state: "done" | "running" | "owner" | "blocked" | "pending";
  note: string;
  role?: string;
  stage?: string;
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
export type ProjectKind = "app" | "website" | "slides" | "video";

export interface Template {
  id: string;
  kind: ProjectKind;
  name: string;
  tagline: string;
  best_for: string;
  palette: string[];
  has_demo: boolean;
  demo_url: string | null;
  thumb_url?: string | null;
  own: boolean;
}

export interface NewProject {
  path: string;
  create: boolean;
  team: string[];
  style: string;
  brief: string;
  profile: BuildProfile;
  kind: ProjectKind;
  template: string | null;
  platforms?: Platform[];
  decide_for_me?: boolean;
}

export type Platform = "web" | "phone" | "computer";
export interface AppPreview { kind: "web" | "expo"; url: string; revision?: string }
export type ReviewAnswer = string | { choice: string; revision?: string; feedback?: string };

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: { "content-type": "application/json", "x-lyra-token": token() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 401) {
    markStale();
    throw new Error(STALE_MESSAGE);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { detail?: string }).detail ?? `Request failed (${res.status})`);
  return data as T;
}

/** A restart gives Appling a new access key; an open tab keeps the old one and every request is refused. */
export const STALE_EVENT = "appling:stale";
export const STALE_MESSAGE = "Appling was restarted, so this tab is out of date. Reload it to continue. Nothing you clicked here was sent.";
function markStale() {
  if (typeof window !== "undefined" && typeof window.dispatchEvent === "function") window.dispatchEvent(new Event(STALE_EVENT));
}

/** Upload one file into the project's assets/uploads/, reporting progress (0–1). */
export function uploadFile(id: string, file: File, onProgress: (p: number) => void): Promise<{ path: string; size: number }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", `/api/projects/${id}/files?name=${encodeURIComponent(file.name)}`);
    xhr.setRequestHeader("x-lyra-token", token());
    xhr.setRequestHeader("content-type", "application/octet-stream");
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      let data: { path?: string; size?: number; detail?: string } = {};
      try { data = JSON.parse(xhr.responseText); } catch { /* not JSON */ }
      if (xhr.status === 401) { markStale(); reject(new Error(STALE_MESSAGE)); return; }
      if (xhr.status >= 200 && xhr.status < 300 && data.path) resolve({ path: data.path, size: data.size ?? file.size });
      else reject(new Error(data.detail ?? `Upload failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("Upload failed — is Appling still running?"));
    xhr.send(file);
  });
}

export type CriterionStatus = "passed" | "failed" | "pending_owner" | "not_run";

export interface AcceptanceCriterion {
  id: string;
  requirement: string;
  description: string;
  release: "1" | "later";
  live: boolean;
  prerequisites: string[];
}

export interface AcceptanceResult {
  status: CriterionStatus;
  requirement?: string;
  evidence?: string | null;
  next_action?: string | null;
  owner?: "you" | "builder" | null;
  detail?: string | null;
  stale?: boolean;
}

export interface Prerequisite {
  id: string;
  kind: string;
  description: string;
  needed_at: "build" | "verification";
  done: boolean;
}

export interface AcceptanceStatus {
  phase: string;
  derived: boolean;
  criteria: AcceptanceCriterion[];
  prerequisites: Prerequisite[];
  results: Record<string, AcceptanceResult>;
  outcome: CriterionStatus;
}

export const api = {
  projects: () => call<{ projects: ProjectSummary[]; default_root: string; version?: string }>("GET", "/api/projects"),
  catalog: () => call<Catalog>("GET", "/api/catalog"),
  addProject: (body: NewProject) => call<ProjectDetail>("POST", "/api/projects", body),
  deleteProject: (id: string) => call<{ archived_to: string }>("DELETE", `/api/projects/${id}`),
  project: (id: string) => call<ProjectDetail>("GET", `/api/projects/${id}`),
  startUpdate: (id: string, branch: string | null) =>
    call<{ chat_id: string }>("POST", `/api/projects/${id}/update`, { branch }),
  usage: (id: string) => call<unknown>("GET", `/api/projects/${id}/usage`),
  preview: (id: string) => call<{ available: boolean; build: boolean; prototype?: string }>("GET", `/api/projects/${id}/preview`),
  openApp: (id: string) => call<AppPreview>("POST", `/api/projects/${id}/preview/open`),
  openPrototype: (id: string) => call<AppPreview>("POST", `/api/projects/${id}/preview/prototype`),
  map: (id: string) => call<ProjectMap>("GET", `/api/projects/${id}/map`),
  blocks: (id: string) => call<import("./components/blocks-view").BlocksStatus>("GET", `/api/projects/${id}/blocks`),
  acceptance: (id: string) => call<AcceptanceStatus>("GET", `/api/projects/${id}/acceptance`),
  prerequisite: (id: string, item: string, done: boolean) =>
    call<{ ok: boolean }>("POST", `/api/projects/${id}/prerequisites/${encodeURIComponent(item)}`, { done }),
  send: (id: string, text: string) => call("POST", `/api/projects/${id}/messages`, { text }),
  answer: (id: string, item: string, answer: ReviewAnswer) => call("POST", `/api/projects/${id}/inbox/${item}`, { answer }),
  reopenReview: (id: string, item: string) => call("POST", `/api/projects/${id}/review/reopen`, { item_id: item }),
  team: (id: string, team: string[]) => call("POST", `/api/projects/${id}/team`, { team }),
  settings: (id: string, body: Record<string, unknown>) => call("POST", `/api/projects/${id}/settings`, body),
  settingsGet: () => call<AiSettings>("GET", "/api/settings"),
  settingsSave: (body: Record<string, unknown>) => call<AiSettings>("POST", "/api/settings", body),
  phoneSettings: () => call<PhoneSettings>("GET", "/api/settings/phone"),
  phoneAction: (channel: PhoneChannel, body: PhoneAction) => call<PhoneSettings>("POST", `/api/settings/phone/${channel}`, body),
  agentModelSave: (id: string, selection: ModelSelection | null) =>
    call<AiSettings>("POST", `/api/settings/agents/${id}`, { selection }),
  effortSave: (effort: string) => call<AiSettings["hermes_effort"]>("POST", "/api/settings/effort", { effort }),
  modelOptions: (refresh = false) => call<ModelOptions>("GET", `/api/settings/models${refresh ? "?refresh=true" : ""}`),
  testConnection: (provider: string, model: string) => call<ConnectionTestResult>("POST", `/api/settings/connections/${encodeURIComponent(provider)}/test`, { model }),
  modelSave: (provider: string, model: string, confirm: boolean) =>
    call<{ ok: boolean; confirm_required?: boolean; message?: string }>("POST", "/api/settings/model", { provider, model, confirm }),
  templates: (kind: ProjectKind) => call<{ templates: Template[] }>("GET", `/api/templates?kind=${kind}`),
  addTemplate: (body: { name: string; kind: ProjectKind; tagline: string; spec: string }) =>
    call<Template>("POST", "/api/templates", body),
  deleteTemplate: (id: string) => call("DELETE", `/api/templates/${id}`),
  engines: () => call<{ engines: { id: string; label: string }[] }>("GET", "/api/engines"),
  applyRules: (id: string) => call("POST", `/api/projects/${id}/apply-rules`),
  stop: (id: string) => call("POST", `/api/projects/${id}/stop`),
  newChat: (id: string) => call("POST", `/api/projects/${id}/new-chat`),
  folders: (path?: string) =>
    call<FolderListing>("GET", `/api/folders${path ? `?path=${encodeURIComponent(path)}` : ""}`),
  pickFolder: (start: string, title: string) =>
    call<{ path: string | null }>("POST", "/api/folders/pick", { start, title }),
};

export function streamUrl(id: string, offset: number): string {
  return `/api/projects/${id}/stream?offset=${offset}&token=${encodeURIComponent(token())}`;
}

export const avatarUrl = (id: string): string => `/avatars/${id}.webp`;
