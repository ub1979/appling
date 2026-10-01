// Turns the project's event feed (.lyra/events.jsonl over SSE) into what the
// screen shows. Pure, so it can be tested without a browser.

export interface InboxItem {
  id: string;
  kind: "approval" | "question" | "secret" | string;
  created: number;
  question?: string;
  command?: string;
  description?: string;
  choices?: string[];
  env_var?: string;
}

export interface ActivityItem {
  key: string;
  ts: number;
  text: string;
  detail?: string;
  tone: "work" | "helper" | "done" | "problem";
}

export interface Helper {
  id: string;
  goal: string;
  running: boolean;
  status?: string;
  lastTool?: string;
}

export interface LiveTurn {
  id: string;
  text: string;
  kind: string;
  reply: string;
}

export interface LiveState {
  turn: LiveTurn | null;
  queued: { id: string; text: string; kind: string }[];
  inbox: InboxItem[];
  activity: ActivityItem[];
  helpers: Record<string, Helper>;
  turnsEnded: number;
  helperChanges: number;
  paused: boolean;
  lastProblem: string | null;
}

export interface LyraEvent {
  ts: number;
  type: string;
  [key: string]: unknown;
}

export const emptyLive = (): LiveState => ({
  turn: null,
  queued: [],
  inbox: [],
  activity: [],
  helpers: {},
  turnsEnded: 0,
  helperChanges: 0,
  paused: false,
  lastProblem: null,
});

const TOOL_WORDS: Record<string, string> = {
  terminal: "Ran a command",
  execute_code: "Ran a script",
  read_file: "Read a file",
  write_file: "Wrote a file",
  patch: "Edited a file",
  search_files: "Searched the project",
  delegate_task: "Handed work to an agent",
  skill_view: "Checked its instructions",
  skills_list: "Checked its instructions",
  web_search: "Searched the web",
  web_extract: "Read a web page",
  clarify: "Asked you a question",
  todo: "Updated its to-do list",
  browser_navigate: "Opened a page in the browser",
  vision_analyze: "Looked at an image",
};

export function toolWords(name: string): string {
  return TOOL_WORDS[name] ?? `Used ${name.replace(/_/g, " ")}`;
}

const MAX_ACTIVITY = 200;

function addActivity(state: LiveState, item: ActivityItem): ActivityItem[] {
  const next = [...state.activity, item];
  return next.length > MAX_ACTIVITY ? next.slice(-MAX_ACTIVITY) : next;
}

const str = (v: unknown): string => (typeof v === "string" ? v : "");

export function applyEvent(state: LiveState, evt: LyraEvent): LiveState {
  switch (evt.type) {
    case "queued": {
      const item = evt.item as { id: string; text: string; kind?: string };
      if (state.queued.some((q) => q.id === item.id)) return state;
      return { ...state, queued: [...state.queued, { id: item.id, text: item.text, kind: item.kind ?? "user" }] };
    }
    case "turn_start": {
      const id = str(evt.turn);
      return {
        ...state,
        queued: state.queued.filter((q) => q.id !== id),
        turn: { id, text: str(evt.display) || str(evt.text), kind: str(evt.kind) || "user", reply: "" },
        lastProblem: null,
      };
    }
    case "delta":
      if (!state.turn) return state;
      return { ...state, turn: { ...state.turn, reply: state.turn.reply + str(evt.text) } };
    case "tool": {
      if (evt.phase !== "start") return state;
      return {
        ...state,
        activity: addActivity(state, {
          key: `${evt.turn}-${evt.id}-${evt.ts}`,
          ts: evt.ts,
          text: toolWords(str(evt.name)),
          detail: str(evt.args),
          tone: "work",
        }),
      };
    }
    case "helper":
      return applyHelper(state, evt);
    case "inbox": {
      const item = evt.item as InboxItem;
      if (state.inbox.some((i) => i.id === item.id)) return state;
      return { ...state, inbox: [...state.inbox, item] };
    }
    case "problem":
      return { ...state, lastProblem: str(evt.text) || "Something went wrong." };
    case "watchdog":
      return {
        ...state,
        activity: addActivity(state, {
          key: `wd-${evt.ts}`,
          ts: evt.ts,
          text: evt.action === "gave_up" ? "Stopped nudging itself (no progress)" : "Kept going on its own",
          detail: str(evt.text),
          tone: evt.action === "gave_up" ? "problem" : "helper",
        }),
      };
    case "stop_requested":
      return { ...state, paused: true, queued: evt.cleared_queue ? [] : state.queued };
    case "resumed":
      return { ...state, paused: false, queued: [] };
    case "inbox_closed":
      return { ...state, inbox: state.inbox.filter((i) => i.id !== evt.id) };
    case "turn_end": {
      const status = str(evt.status);
      const problem =
        status === "error" || status === "crashed"
          ? str(evt.error) || "Lyra hit a problem and stopped this reply."
          : null;
      let next = state;
      const cost = (evt.usage as { cost_usd?: number } | undefined)?.cost_usd;
      if (typeof cost === "number" && cost >= 0.005) {
        next = { ...next, activity: addActivity(next, { key: `cost-${evt.ts}`, ts: evt.ts, text: `This step cost $${cost.toFixed(2)}`, tone: "work" }) };
      }
      if (evt.checkpoint) {
        next = { ...next, activity: addActivity(next, { key: `ckpt-${evt.ts}`, ts: evt.ts, text: "Saved the work to the project history", tone: "done" }) };
      }
      return { ...next, turn: null, turnsEnded: state.turnsEnded + 1, lastProblem: problem };
    }
    default:
      return state;
  }
}

function applyHelper(state: LiveState, evt: LyraEvent): LiveState {
  const id = str(evt.subagent_id) || `${str(evt.goal)}-${String(evt.task_index ?? 0)}`;
  const prev = state.helpers[id];
  const goal = str(evt.goal) || prev?.goal || "A piece of the work";
  const kind = str(evt.event);
  let helper: Helper = prev ?? { id, goal, running: true };
  let activity = state.activity;
  if (kind === "reported") {
    return {
      ...state,
      helperChanges: state.helperChanges + 1,
      activity: addActivity(state, { key: `h-rep-${id}-${evt.ts}`, ts: evt.ts, text: "An agent's report arrived", detail: goal, tone: "helper" }),
    };
  }
  if (kind === "start" || kind === "spawn_requested") {
    helper = { ...helper, goal, running: true };
    if (!prev) {
      activity = addActivity(state, { key: `h-${id}-${evt.ts}`, ts: evt.ts, text: "An agent started", detail: goal, tone: "helper" });
    }
  } else if (kind === "tool") {
    helper = { ...helper, lastTool: toolWords(str(evt.tool)) };
  } else if (kind === "complete") {
    const status = str(evt.status) || "done";
    helper = { ...helper, running: false, status };
    activity = addActivity(state, {
      key: `h-${id}-end-${evt.ts}`,
      ts: evt.ts,
      text: status === "completed" || status === "done" ? "An agent finished" : `An agent stopped (${status})`,
      detail: goal,
      tone: status === "completed" || status === "done" ? "done" : "problem",
    });
  } else {
    return state;
  }
  const changed = kind === "tool" ? 0 : 1;
  return { ...state, helpers: { ...state.helpers, [id]: helper }, activity, helperChanges: state.helperChanges + changed };
}

export function activeHelpers(state: LiveState): Helper[] {
  return Object.values(state.helpers).filter((h) => h.running);
}
