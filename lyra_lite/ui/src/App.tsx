import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, streamUrl, type ChatMessage, type FolderListing, type ProjectDetail, type ProjectSummary } from "./api";
import { activeHelpers, applyEvent, emptyLive, type InboxItem, type LiveState, type LyraEvent } from "./live";

const SELECTED_KEY = "lyra-lite:selected";

function remembered(): string | null {
  try {
    return window.localStorage.getItem(SELECTED_KEY);
  } catch {
    return null;
  }
}

function remember(id: string): void {
  try {
    window.localStorage.setItem(SELECTED_KEY, id);
  } catch {
    // Storage can be unavailable (private window); selection just isn't kept.
  }
}

export function App() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [defaultRoot, setDefaultRoot] = useState("");
  const [selected, setSelected] = useState<string | null>(remembered());
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await api.projects();
      setProjects(data.projects);
      setDefaultRoot(data.default_root);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const current = projects.find((p) => p.id === selected) ?? null;

  const choose = (id: string) => {
    setSelected(id);
    remember(id);
  };

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">Lyra</div>
        <button className="primary wide" onClick={() => setCreating(true)}>
          + New project
        </button>
        <nav className="projects">
          {projects.map((p) => (
            <button
              key={p.id}
              className={`project ${p.id === selected ? "active" : ""}`}
              onClick={() => choose(p.id)}
              title={p.root}
            >
              <span className="project-name">{p.name}</span>
              {p.inbox > 0 ? <span className="dot need">{p.inbox}</span> : p.running ? <span className="dot busy" /> : null}
            </button>
          ))}
          {projects.length === 0 && <p className="muted small">No projects yet.</p>}
        </nav>
        {error && <p className="problem small">Can't reach Lyra: {error}</p>}
      </aside>
      <main className="main">
        {current ? (
          <ProjectView key={current.id} id={current.id} onChange={() => void refresh()} />
        ) : (
          <div className="empty">
            <h1>Welcome to Lyra</h1>
            <p>Pick a project on the left, or start a new one.</p>
          </div>
        )}
      </main>
      {creating && (
        <NewProjectDialog
          startPath={defaultRoot}
          onClose={() => setCreating(false)}
          onCreated={(id) => {
            setCreating(false);
            choose(id);
            void refresh();
          }}
        />
      )}
    </div>
  );
}

interface ResetAction {
  type: "reset";
  detail: ProjectDetail;
}

function liveReducer(state: LiveState, action: LyraEvent | ResetAction): LiveState {
  if (action.type === "reset" && "detail" in action) {
    const { detail } = action as ResetAction;
    return { ...emptyLive(), inbox: detail.inbox, queued: detail.queue };
  }
  return applyEvent(state, action as LyraEvent);
}

function ProjectView({ id, onChange }: { id: string; onChange: () => void }) {
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [live, dispatch] = useReducer(liveReducer, undefined, emptyLive);
  const [problem, setProblem] = useState<string | null>(null);

  const load = useCallback(async () => {
    const data = await api.project(id);
    setDetail(data);
    return data;
  }, [id]);

  useEffect(() => {
    let source: EventSource | null = null;
    let cancelled = false;
    void load().then((data) => {
      if (cancelled) return;
      dispatch({ type: "reset", detail: data });
      source = new EventSource(streamUrl(id, data.turn_start_offset));
      source.onmessage = (msg) => {
        try {
          dispatch(JSON.parse(msg.data) as LyraEvent);
        } catch {
          // A malformed line is skipped; the next one still applies.
        }
      };
    });
    return () => {
      cancelled = true;
      source?.close();
    };
  }, [id, load]);

  useEffect(() => {
    if (live.turnsEnded > 0) {
      void load();
      onChange();
    }
  }, [live.turnsEnded, load, onChange]);

  const helpers = activeHelpers(live);
  const status = live.inbox.length
    ? { text: "Waiting for you", tone: "need" }
    : live.turn
      ? { text: "Working…", tone: "busy" }
      : helpers.length
        ? { text: `${helpers.length} agent${helpers.length > 1 ? "s" : ""} working`, tone: "busy" }
        : { text: "Ready", tone: "idle" };

  const run = async (action: () => Promise<unknown>) => {
    try {
      setProblem(null);
      await action();
    } catch (e) {
      setProblem(e instanceof Error ? e.message : String(e));
    }
  };

  if (!detail) return <div className="empty muted">Opening project…</div>;

  return (
    <div className="project-view">
      <section className="chat-col">
        <header className="bar">
          <div className="bar-title">
            <h2>{detail.name}</h2>
            <div className="muted small path"><bdi>{detail.root}</bdi></div>
          </div>
          <div className="bar-actions">
            <span className={`pill ${status.tone}`}>{status.text}</span>
            {(live.turn || live.queued.length > 0) && (
              <button onClick={() => void run(() => api.stop(id))}>Stop</button>
            )}
            <button
              className="ghost"
              disabled={!!live.turn}
              title="Start a fresh conversation. The project files stay as they are."
              onClick={() => void run(async () => {
                await api.newChat(id);
                await load();
              })}
            >
              New chat
            </button>
          </div>
        </header>
        <Chat messages={detail.messages} live={live} />
        {(problem || live.lastProblem) && <div className="problem banner">{problem ?? live.lastProblem}</div>}
        <Composer busy={!!live.turn} onSend={(text) => run(() => api.send(id, text))} />
      </section>
      <aside className="side-col">
        <Inbox items={live.inbox} onAnswer={(item, answer) => run(() => api.answer(id, item, answer))} />
        {helpers.length > 0 && (
          <section className="panel">
            <h3>Agents working</h3>
            {helpers.map((h) => (
              <div key={h.id} className="helper">
                <div>{h.goal}</div>
                {h.lastTool && <div className="muted small">{h.lastTool}</div>}
              </div>
            ))}
          </section>
        )}
        <section className="panel grow">
          <h3>Activity</h3>
          <Activity live={live} />
        </section>
      </aside>
    </div>
  );
}

function Chat({ messages, live }: { messages: ChatMessage[]; live: LiveState }) {
  const end = useRef<HTMLDivElement>(null);
  const turn = live.turn;
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages.length, turn?.reply.length, live.queued.length]);

  return (
    <div className="chat">
      {messages.length === 0 && !turn && (
        <p className="muted center">Say hello and tell Lyra what you'd like to build.</p>
      )}
      {messages.map((m, i) => (
        <Bubble key={i} role={m.role} kind={m.kind} text={m.content} />
      ))}
      {turn && turn.kind === "user" && <Bubble role="user" kind="chat" text={turn.text} />}
      {turn && turn.kind !== "user" && <Bubble role="user" kind="system" text={turn.text} />}
      {turn && <Bubble role="assistant" kind="chat" text={turn.reply} streaming />}
      {live.queued.map((q) => (
        <div key={q.id} className="queued">
          <Bubble role="user" kind={q.kind === "user" ? "chat" : "system"} text={q.text} />
          <div className="muted small right">Lyra will read this next</div>
        </div>
      ))}
      <div ref={end} />
    </div>
  );
}

function Bubble({ role, kind, text, streaming }: { role: string; kind: string; text: string; streaming?: boolean }) {
  if (kind === "system") {
    return (
      <details className="system-note">
        <summary>Agent report</summary>
        <pre>{text}</pre>
      </details>
    );
  }
  return (
    <div className={`bubble ${role}`}>
      {role === "assistant" ? (
        <>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
          {streaming && <span className="typing">●●●</span>}
        </>
      ) : (
        <p className="plain">{text}</p>
      )}
    </div>
  );
}

function Composer({ busy, onSend }: { busy: boolean; onSend: (text: string) => Promise<void> }) {
  const [text, setText] = useState("");
  const send = async () => {
    const value = text.trim();
    if (!value) return;
    setText("");
    await onSend(value);
  };
  return (
    <div className="composer">
      <textarea
        value={text}
        placeholder={busy ? "Lyra is working — you can still write; it reads this next." : "Message Lyra…"}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            void send();
          }
        }}
        rows={3}
      />
      <button className="primary" onClick={() => void send()} disabled={!text.trim()}>
        Send
      </button>
    </div>
  );
}

const APPROVAL_CHOICES: { value: string; label: string; tone?: string }[] = [
  { value: "once", label: "Allow once", tone: "primary" },
  { value: "session", label: "Allow for this chat" },
  { value: "always", label: "Always allow" },
  { value: "deny", label: "Don't allow", tone: "danger" },
];

function Inbox({ items, onAnswer }: { items: InboxItem[]; onAnswer: (id: string, answer: string) => Promise<void> }) {
  if (items.length === 0) return null;
  return (
    <section className="panel need">
      <h3>Needs you</h3>
      {items.map((item) => (
        <InboxCard key={item.id} item={item} onAnswer={(a) => onAnswer(item.id, a)} />
      ))}
    </section>
  );
}

function InboxCard({ item, onAnswer }: { item: InboxItem; onAnswer: (answer: string) => Promise<void> }) {
  const [text, setText] = useState("");
  if (item.kind === "approval") {
    return (
      <div className="card">
        <div className="card-title">Lyra wants to run a command</div>
        {item.description && <div className="small">Why it's flagged: {item.description}</div>}
        <pre className="command">{item.command}</pre>
        <div className="choices">
          {APPROVAL_CHOICES.map((c) => (
            <button key={c.value} className={c.tone ?? ""} onClick={() => void onAnswer(c.value)}>
              {c.label}
            </button>
          ))}
        </div>
      </div>
    );
  }
  const secret = item.kind === "secret";
  return (
    <div className="card">
      <div className="card-title">{secret ? "Lyra needs a key or password" : "Lyra has a question"}</div>
      <div className="question">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.question ?? ""}</ReactMarkdown>
      </div>
      {secret && item.env_var && <div className="muted small">Saved privately as {item.env_var}; it is not shown in the chat.</div>}
      {!!item.choices?.length && (
        <div className="choices">
          {item.choices.map((c) => (
            <button key={c} onClick={() => void onAnswer(c)}>
              {c}
            </button>
          ))}
        </div>
      )}
      <div className="answer-row">
        <input
          type={secret ? "password" : "text"}
          value={text}
          placeholder={secret ? "Paste it here" : "Type your answer"}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && text.trim()) void onAnswer(text.trim());
          }}
        />
        <button className="primary" disabled={!text.trim()} onClick={() => void onAnswer(text.trim())}>
          {secret ? "Save" : "Send"}
        </button>
      </div>
    </div>
  );
}

function Activity({ live }: { live: LiveState }) {
  const items = useMemo(() => [...live.activity].reverse().slice(0, 60), [live.activity]);
  if (items.length === 0) return <p className="muted small">Nothing yet.</p>;
  return (
    <ul className="activity">
      {items.map((a) => (
        <li key={a.key} className={a.tone} title={a.detail}>
          <span className="time">{new Date(a.ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
          <span>{a.text}</span>
          {a.detail && a.tone === "helper" && <div className="muted small">{a.detail}</div>}
        </li>
      ))}
    </ul>
  );
}

function NewProjectDialog({
  startPath,
  onClose,
  onCreated,
}: {
  startPath: string;
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const [listing, setListing] = useState<FolderListing | null>(null);
  const [name, setName] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  const open = useCallback(async (path?: string) => {
    try {
      setListing(await api.folders(path));
      setProblem(null);
    } catch (e) {
      setProblem(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void open(startPath || undefined);
  }, [open, startPath]);

  const submit = async (path: string, create: boolean) => {
    try {
      const res = await api.addProject(path, create);
      onCreated(res.id);
    } catch (e) {
      setProblem(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h2>New project</h2>
        <label className="small muted">Name</label>
        <input value={name} placeholder="e.g. Recipe planner" onChange={(e) => setName(e.target.value)} autoFocus />
        <div className="small muted">
          It will be created in <code>{listing?.path ?? "…"}</code>
        </div>
        <div className="folder-list">
          {listing?.parent && (
            <button className="ghost" onClick={() => void open(listing.parent ?? undefined)}>
              ← Up
            </button>
          )}
          {listing?.folders.map((f) => (
            <div key={f} className="folder-row">
              <button className="ghost grow left" onClick={() => void open(`${listing.path}/${f}`)}>
                📁 {f}
              </button>
              <button className="small-btn" onClick={() => void submit(`${listing.path}/${f}`, false)}>
                Open as project
              </button>
            </div>
          ))}
        </div>
        {problem && <p className="problem small">{problem}</p>}
        <div className="dialog-actions">
          <button className="ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            className="primary"
            disabled={!name.trim() || !listing}
            onClick={() => listing && void submit(`${listing.path}/${name.trim()}`, true)}
          >
            Create
          </button>
        </div>
      </div>
    </div>
  );
}
