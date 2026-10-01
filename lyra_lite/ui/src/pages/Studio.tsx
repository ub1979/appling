import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  api,
  streamUrl,
  type Agent,
  type Catalog,
  type ChatMessage,
  type ProjectDetail,
  type ProjectMap,
} from "../api";
import { Avatar, PrefButtons, TeamPicker } from "../components/common";
import { SettingsDialog } from "../components/SettingsDialog";
import { activeHelpers, applyEvent, emptyLive, type InboxItem, type LiveState, type LyraEvent } from "../live";
import { go } from "../router";
import {
  extractAppItSkillSelection,
  orderGuidedPhases,
  parseGuidedPhaseMarkers,
  phasesFromProgressLedger,
  sanitizeGuidedResponse,
} from "../studio";

// The same answers the Studio offered under a requirements question.
const ANSWERS = [
  { label: "Skip this question", text: "Skip this question. Record it as an open decision and ask the next single question." },
  { label: "Decide for me", text: "Decide this question for me using the safest sensible default. Briefly state the default, then ask the next single question." },
  { label: "Use smart defaults", text: "Use sensible defaults for all remaining requirements questions. Summarize the complete requirements and choices for my approval before any coding." },
];

interface ResetAction {
  type: "reset";
  detail: ProjectDetail;
}

function liveReducer(state: LiveState, action: LyraEvent | ResetAction): LiveState {
  if (action.type === "reset" && "detail" in action) {
    const { detail } = action as ResetAction;
    return { ...emptyLive(), inbox: detail.inbox, queued: detail.queue, paused: detail.paused };
  }
  return applyEvent(state, action as LyraEvent);
}

interface Shown {
  role: "user" | "lyra" | "note" | "report";
  text: string;
  proposal: string[] | null;
}

function clean(raw: string, ids: string[]): { text: string; proposal: string[] | null; started: string[]; completed: string[] } {
  const markers = parseGuidedPhaseMarkers(raw, ids);
  const selection = extractAppItSkillSelection(markers.content, ids);
  return {
    text: sanitizeGuidedResponse(selection ? selection.content : markers.content),
    proposal: selection?.skillIds.length ? selection.skillIds : null,
    started: markers.started,
    completed: markers.completed,
  };
}

function shownMessage(m: ChatMessage, ids: string[]): Shown {
  if (m.kind === "auto") return { role: "note", text: m.content, proposal: null };
  if (m.kind === "system") return { role: "report", text: m.content, proposal: null };
  if (m.role === "user") return { role: "user", text: m.content, proposal: null };
  const c = clean(m.content, ids);
  return { role: "lyra", text: c.text, proposal: c.proposal };
}

const timeOf = (ts: number) => new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

export function Studio({ id }: { id: string }) {
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [map, setMap] = useState<ProjectMap | null>(null);
  const [live, dispatch] = useReducer(liveReducer, undefined, emptyLive);
  const [problem, setProblem] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showTeam, setShowTeam] = useState(false);

  const load = useCallback(async () => {
    const data = await api.project(id);
    setDetail(data);
    return data;
  }, [id]);

  useEffect(() => {
    void api.catalog().then(setCatalog).catch(() => undefined);
  }, []);

  useEffect(() => {
    let source: EventSource | null = null;
    let cancelled = false;
    load().then((data) => {
      if (cancelled) return;
      dispatch({ type: "reset", detail: data });
      source = new EventSource(streamUrl(id, data.turn_start_offset));
      source.onmessage = (msg) => {
        try {
          dispatch(JSON.parse(msg.data) as LyraEvent);
        } catch {
          // skip a malformed line
        }
      };
    }).catch((e) => setProblem(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
      source?.close();
    };
  }, [id, load]);

  useEffect(() => {
    if (live.turnsEnded > 0 || live.helperChanges > 0) void load();
  }, [live.turnsEnded, live.helperChanges, load]);

  useEffect(() => {
    let alive = true;
    const fetchMap = () => void api.map(id).then((m) => alive && setMap(m)).catch(() => undefined);
    fetchMap();
    const timer = window.setInterval(fetchMap, 15000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [id, live.turnsEnded]);

  const run = useCallback(async (action: () => Promise<unknown>) => {
    try {
      setProblem(null);
      await action();
    } catch (e) {
      setProblem(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const agents = catalog?.agents ?? [];
  const ids = useMemo(() => agents.map((a) => a.id), [agents]);
  const team = detail?.team?.length ? detail.team : ["req-engineer", "task-planner"];
  const helpers = detail?.helpers ?? [];
  const liveHelpers = activeHelpers(live);
  const busy = !!live.turn;

  // Phase state from Lyra's markers, then the project's own plan file.
  const phases = useMemo(() => {
    const started: string[] = [];
    const completed = new Set<string>();
    const raws = [...(detail?.messages ?? []).filter((m) => m.role === "assistant").map((m) => m.content), live.turn?.reply ?? ""];
    for (const raw of raws) {
      const p = parseGuidedPhaseMarkers(raw, ids);
      started.push(...p.started);
      p.completed.forEach((c) => completed.add(c));
    }
    let current: string | null = [...started].reverse().find((s) => !completed.has(s)) ?? null;
    if (map?.markdown) {
      const labels = Object.fromEntries(agents.map((a) => [a.id, a.label]));
      const ledger = phasesFromProgressLedger(map.markdown, labels);
      ledger.completed.forEach((c) => completed.add(c));
      if (ledger.current) current = ledger.current;
    }
    const ordered = orderGuidedPhases(Array.from(new Set([...team, ...started, ...completed])).filter((x) => ids.includes(x)));
    return { ordered, completed, current };
  }, [detail?.messages, live.turn?.reply, ids, agents, map?.markdown, team]);

  const shown: Shown[] = useMemo(() => (detail?.messages ?? []).map((m) => shownMessage(m, ids)), [detail?.messages, ids]);
  const lastLyra = [...shown].map((s, i) => [s, i] as const).reverse().find(([s]) => s.role === "lyra");
  const lastTeamNote = shown.map((s, i) => [s, i] as const).reverse().find(([s]) => s.role === "note" && s.text.startsWith("Team updated"));
  const openProposal =
    !busy && lastLyra && lastLyra[0].proposal && (!lastTeamNote || lastTeamNote[1] < lastLyra[1]) ? lastLyra[0].proposal : null;
  const lastText = lastLyra?.[0].text.trim() ?? "";
  const asksQuestion = !busy && live.queued.length === 0 && /[?？]\s*$/.test(lastText) && !openProposal;
  const asksApproval = !busy && live.queued.length === 0 && /\bapprov/i.test(lastText.slice(-500)) && !openProposal;

  if (!detail) {
    return (
      <div className="page">
        <p className="muted" style={{ padding: 40 }}>{problem ?? "Opening project…"}</p>
      </div>
    );
  }

  const status = live.inbox.length
    ? { text: "Needs you", tone: "need" }
    : busy
      ? { text: "Lyra is working", tone: "busy" }
      : helpers.length
        ? { text: `${helpers.length} agent${helpers.length > 1 ? "s" : ""} working`, tone: "busy" }
        : live.paused
          ? { text: "Stopped", tone: "" }
          : { text: "Ready", tone: "good" };

  const send = (text: string) => run(() => api.send(id, text));
  const labelOf = (agentId: string) => agents.find((a) => a.id === agentId)?.label ?? agentId;

  return (
    <div className="studio">
      <header className="studio-top">
        <button className="btn ghost small" onClick={() => go("/")} title="All projects">←</button>
        <span className="brand-mark" style={{ width: 30, height: 30, fontSize: 14, borderRadius: 9 }}>L</span>
        <div className="studio-title">
          <b>{detail.name}</b>
          <span><bdi>{detail.root}</bdi></span>
        </div>
        <div className="studio-actions">
          <span className={`pill ${status.tone}`}>{status.text}</span>
          <label className="toggle" title="When work is left and nothing waits for you, Lyra continues by itself after 10 quiet minutes.">
            <span
              className={`switch ${detail.keep_going ? "on" : ""}`}
              role="switch"
              aria-checked={detail.keep_going}
              tabIndex={0}
              onClick={() => {
                const on = !detail.keep_going;
                setDetail({ ...detail, keep_going: on });
                void run(async () => { await api.settings(id, { keep_going: on }); await load(); });
              }}
            />
            <span className="label">Keep going</span>
          </label>
          {(busy || live.queued.length > 0 || helpers.length > 0) && (
            <button className="btn danger small" onClick={() => void run(() => api.stop(id))}>■ Stop</button>
          )}
          <button className="btn small" onClick={() => setShowSettings(true)} title="Engine and model">
            {detail.engine === "claude" ? "Claude Code" : "Hermes"} ⚙
          </button>
          <button
            className="btn small"
            disabled={busy || helpers.length > 0}
            title="Start a fresh conversation. Project files stay as they are."
            onClick={() => void run(async () => { await api.newChat(id); await load(); })}
          >
            New chat
          </button>
          <PrefButtons />
        </div>
      </header>

      <div>
        {detail.rules_outdated && (
          <div className="banner warn">
            Lyra's rules were updated since this chat started.
            <button className="btn small" disabled={busy || helpers.length > 0} onClick={() => void run(async () => { await api.applyRules(id); await load(); })}>
              Use the new rules
            </button>
          </div>
        )}
        {(problem || live.lastProblem) && <div className="banner bad">{problem ?? live.lastProblem}</div>}
      </div>

      <div className="studio-body">
        <aside className="side left">
          <section className="panel">
            <div className="agent-row working" style={{ background: "transparent", padding: 0 }}>
              <Avatar id="app-it" size={44} />
              <div className="who">
                <b>Lyra</b>
                <span>
                  {live.inbox.length ? "Waiting for your answer" : busy ? "Working on it…" : helpers.length ? "Guiding the agents" : "Here when you need me"}
                </span>
              </div>
            </div>
          </section>
          <section className="panel">
            <h3>
              Your team
              <button className="btn ghost small" onClick={() => setShowTeam(true)}>Change</button>
            </h3>
            {orderedTeamAgents(agents, team).map((a) => {
              const working = (busy || helpers.length > 0) && phases.current === a.id;
              const done = phases.completed.has(a.id);
              const tool = working ? liveHelpers[0]?.lastTool : undefined;
              return (
                <div key={a.id} className={`agent-row ${working ? "working" : ""}`} title={a.description}>
                  <Avatar id={a.id} size={36} />
                  <div className="who">
                    <b>{a.label}</b>
                    <span>{working ? tool ?? "Working" : done ? "Done ✓" : "Ready"}</span>
                  </div>
                </div>
              );
            })}
          </section>
          {helpers.length > 0 && (
            <section className="panel">
              <h3>Agents at work</h3>
              {helpers.map((h) => {
                const lh = liveHelpers.find((x) => x.goal && h.goal.startsWith(x.goal.slice(0, 30)));
                return (
                  <div key={h.id} style={{ marginBottom: 10 }}>
                    <div className="tiny muted">{lh?.lastTool ?? "Working"}{h.started ? ` · since ${timeOf(h.started)}` : ""}</div>
                    <div className="helper-goal">{h.goal}</div>
                  </div>
                );
              })}
            </section>
          )}
        </aside>

        <section className="chat-col">
          <ChatScroll
            shown={shown}
            live={live}
            ids={ids}
            agents={agents}
            team={team}
            asksQuestion={asksQuestion}
            asksApproval={asksApproval}
            proposal={openProposal}
            onSend={(t) => void send(t)}
            onTeam={(t) => void run(async () => { await api.team(id, t); await load(); })}
            onAnswer={(item, a) => void run(() => api.answer(id, item, a))}
          />
          <Composer busy={busy} onSend={send} />
        </section>

        <aside className="side right">
          <section className="panel">
            <h3>Project map</h3>
            <ol className="phase-list">
              {phases.ordered.map((pid, i) => {
                const state = phases.completed.has(pid) ? "done" : phases.current === pid ? "now" : "pending";
                return (
                  <li key={pid} className={`phase ${state}`}>
                    <span className="dot">{state === "done" ? "✓" : i + 1}</span>
                    <span className="name">{labelOf(pid)}</span>
                    <span className="state">{state === "done" ? "Done" : state === "now" ? "Now" : ""}</span>
                  </li>
                );
              })}
            </ol>
            {map?.exists && map.phases.length > 0 && (
              <details style={{ marginTop: 10 }}>
                <summary className="small muted" style={{ cursor: "pointer" }}>From the project plan</summary>
                <ol className="phase-list" style={{ marginTop: 6 }}>
                  {map.phases.map((p, i) => (
                    <li key={`${i}-${p.name}`} className={`phase ${p.state === "running" ? "now" : p.state}`} title={p.status}>
                      <span className="dot">{p.state === "done" ? "✓" : p.state === "owner" ? "!" : "·"}</span>
                      <span className="name">{p.name}</span>
                    </li>
                  ))}
                </ol>
              </details>
            )}
          </section>
          <section className="panel" style={{ flex: 1 }}>
            <h3>Activity</h3>
            {live.activity.length === 0 ? (
              <p className="muted small" style={{ margin: 0 }}>Nothing yet.</p>
            ) : (
              <ul className="activity">
                {[...live.activity].reverse().slice(0, 60).map((a) => (
                  <li key={a.key} title={a.detail}>
                    <time>{timeOf(a.ts)}</time>
                    <span className={`what ${a.tone}`}>{a.text}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </aside>
      </div>

      {showSettings && (
        <SettingsDialog
          detail={detail}
          busy={busy || helpers.length > 0}
          onClose={() => setShowSettings(false)}
          onSave={async (body) => {
            await api.settings(id, body);
            await load();
            setShowSettings(false);
          }}
        />
      )}
      {showTeam && catalog && (
        <TeamDialog
          agents={agents}
          team={team}
          onClose={() => setShowTeam(false)}
          onSave={async (t) => {
            await run(async () => { await api.team(id, t); await load(); });
            setShowTeam(false);
          }}
        />
      )}
    </div>
  );
}

function orderedTeamAgents(agents: Agent[], team: string[]): Agent[] {
  return agents.filter((a) => team.includes(a.id));
}

function TeamDialog({ agents, team, onClose, onSave }: { agents: Agent[]; team: string[]; onClose: () => void; onSave: (t: string[]) => Promise<void> }) {
  const [draft, setDraft] = useState(team);
  const toggle = (agentId: string) => setDraft((d) => (d.includes(agentId) ? d.filter((x) => x !== agentId) : [...d, agentId]));
  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog wide" onClick={(e) => e.stopPropagation()}>
        <h2>Your team</h2>
        <p className="muted small" style={{ margin: 0 }}>Lyra will use only these agents. Requirements and Task planning are always on.</p>
        <TeamPicker agents={agents} selected={draft} onToggle={toggle} />
        <div className="dialog-actions">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary" onClick={() => void onSave(draft)}>Save team</button>
        </div>
      </div>
    </div>
  );
}

function ChatScroll(props: {
  shown: Shown[];
  live: LiveState;
  ids: string[];
  agents: Agent[];
  team: string[];
  asksQuestion: boolean;
  asksApproval: boolean;
  proposal: string[] | null;
  onSend: (text: string) => void;
  onTeam: (team: string[]) => void;
  onAnswer: (item: string, answer: string) => void;
}) {
  const { shown, live, ids } = props;
  const box = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const turn = live.turn;
  const liveText = turn ? clean(turn.reply, ids).text : "";

  useEffect(() => {
    const el = box.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [shown.length, liveText.length, live.queued.length, live.inbox.length, props.proposal]);

  const lastLyraIndex = shown.map((s) => s.role).lastIndexOf("lyra");

  return (
    <div
      className="chat-scroll"
      ref={box}
      onScroll={(e) => {
        const el = e.currentTarget;
        stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
      }}
    >
      <div className="chat-inner">
        {shown.length === 0 && !turn && (
          <div className="empty-note">Let's start building. What's the idea? ✨</div>
        )}
        {shown.map((s, i) => (
          <Message key={i} item={s}>
            {i === lastLyraIndex && props.proposal && (
              <TeamProposal agents={props.agents} proposal={props.proposal} current={props.team} onConfirm={props.onTeam} />
            )}
            {i === lastLyraIndex && (props.asksQuestion || props.asksApproval) && (
              <div className="answer-row">
                {props.asksApproval && (
                  <button className="btn primary small" onClick={() => props.onSend("approve")}>Approve and continue</button>
                )}
                {props.asksQuestion &&
                  ANSWERS.map((a) => (
                    <button key={a.label} className="chip" onClick={() => props.onSend(a.text)}>{a.label}</button>
                  ))}
                {props.asksApproval && <span className="tiny muted" style={{ alignSelf: "center" }}>Or type what you'd like changed.</span>}
              </div>
            )}
          </Message>
        ))}
        {turn && <TurnStart kind={turn.kind} text={turn.text} />}
        {turn && (
          <div className="msg lyra">
            <div className="bubble">
              <div className="msg-head"><img className="lyra-face" src="/avatars/app-it.webp" alt="" /> Lyra</div>
              {liveText ? (
                <div className="md"><ReactMarkdown remarkPlugins={[remarkGfm]}>{liveText}</ReactMarkdown></div>
              ) : null}
              <span className="typing"><i /><i /><i /></span>
            </div>
          </div>
        )}
        {live.queued.map((q) => (
          <div key={q.id} className="msg user queued">
            <div className="bubble">
              <div className="msg-head">You · Lyra reads this next</div>
              {q.text.startsWith("IDRAK_INTERNAL") ? "…" : q.text}
            </div>
          </div>
        ))}
        {live.inbox.map((item) => (
          <NeedCard key={item.id} item={item} onAnswer={(a) => props.onAnswer(item.id, a)} />
        ))}
      </div>
    </div>
  );
}

function TurnStart({ kind, text }: { kind: string; text: string }) {
  if (kind === "user") return <Message item={{ role: "user", text, proposal: null }} />;
  if (kind === "helper_done") return <Message item={{ role: "report", text, proposal: null }} />;
  const note = kind === "watchdog" ? "Lyra kept going on its own." : kind === "team" ? text : kind === "setup" && text !== "Project opened" ? null : "Project opened";
  if (note === null) return <Message item={{ role: "user", text, proposal: null }} />;
  return <Message item={{ role: "note", text: note, proposal: null }} />;
}

function Message({ item, children }: { item: Shown; children?: React.ReactNode }) {
  const [copied, setCopied] = useState(false);
  if (item.role === "note") return <div className="note">↻ {item.text}</div>;
  if (item.role === "report") {
    return (
      <details className="report">
        <summary>An agent reported back</summary>
        <pre>{item.text}</pre>
      </details>
    );
  }
  const copy = () => {
    void navigator.clipboard?.writeText(item.text).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    });
  };
  return (
    <div className={`msg ${item.role}`}>
      <div className="bubble">
        <div className="msg-head">
          {item.role === "lyra" && <img className="lyra-face" src="/avatars/app-it.webp" alt="" />}
          {item.role === "lyra" ? "Lyra" : "You"}
          <button className="copy" onClick={copy}>{copied ? "Copied" : "Copy"}</button>
        </div>
        {item.role === "lyra" ? (
          <div className="md"><ReactMarkdown remarkPlugins={[remarkGfm]}>{item.text}</ReactMarkdown></div>
        ) : (
          item.text
        )}
        {children}
      </div>
    </div>
  );
}

function TeamProposal({ agents, proposal, current, onConfirm }: { agents: Agent[]; proposal: string[]; current: string[]; onConfirm: (t: string[]) => void }) {
  const [draft, setDraft] = useState(() => Array.from(new Set([...proposal, "req-engineer", "task-planner"])));
  const [more, setMore] = useState(false);
  const shownAgents = more ? agents : agents.filter((a) => proposal.includes(a.id) || current.includes(a.id) || a.required);
  const toggle = (agentId: string) => setDraft((d) => (d.includes(agentId) ? d.filter((x) => x !== agentId) : [...d, agentId]));
  return (
    <div className="team-proposal" style={{ marginTop: 12 }}>
      <b style={{ color: "var(--ink)" }}>Lyra suggests this team</b>
      <div className="tiny muted">Untick anyone you don't want, or add more. Nothing changes until you confirm.</div>
      <TeamPicker agents={shownAgents} selected={draft} recommended={proposal} onToggle={toggle} />
      <div className="answer-row" style={{ borderTop: 0, paddingTop: 0 }}>
        <button className="btn primary small" onClick={() => onConfirm(draft)}>Confirm team ({draft.length})</button>
        <button className="btn ghost small" onClick={() => setMore((m) => !m)}>{more ? "Show fewer" : "Add other agents"}</button>
      </div>
    </div>
  );
}

const APPROVAL_CHOICES = [
  { value: "once", label: "Allow once", tone: "primary" },
  { value: "session", label: "Allow for this chat", tone: "" },
  { value: "always", label: "Always allow", tone: "" },
  { value: "deny", label: "Don't allow", tone: "danger" },
];

function NeedCard({ item, onAnswer }: { item: InboxItem; onAnswer: (a: string) => void }) {
  const [text, setText] = useState("");
  if (item.kind === "approval") {
    return (
      <div className="need-card">
        <b>Lyra wants to run a command</b>
        {item.description && <span className="small">Why it's flagged: {item.description}</span>}
        <pre>{item.command}</pre>
        <div className="answer-row" style={{ borderTop: 0, paddingTop: 0, marginTop: 0 }}>
          {APPROVAL_CHOICES.map((c) => (
            <button key={c.value} className={`btn small ${c.tone}`} onClick={() => onAnswer(c.value)}>{c.label}</button>
          ))}
        </div>
      </div>
    );
  }
  const secret = item.kind === "secret";
  return (
    <div className="need-card">
      <b>{secret ? "Lyra needs a key or password" : "Lyra has a question"}</b>
      <div className="md"><ReactMarkdown remarkPlugins={[remarkGfm]}>{item.question ?? ""}</ReactMarkdown></div>
      {secret && item.env_var && <span className="tiny muted">Saved privately as {item.env_var}; never shown in the chat.</span>}
      {!!item.choices?.length && (
        <div className="answer-row" style={{ borderTop: 0, paddingTop: 0, marginTop: 0 }}>
          {item.choices.map((c) => <button key={c} className="chip" onClick={() => onAnswer(c)}>{c}</button>)}
          {!secret && <button className="chip" onClick={() => onAnswer("Decide for me using the safest sensible default.")}>Decide for me</button>}
        </div>
      )}
      <div style={{ display: "flex", gap: 8 }}>
        <input
          className="input"
          type={secret ? "password" : "text"}
          value={text}
          placeholder={secret ? "Paste it here" : "Type your answer"}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && text.trim()) onAnswer(text.trim());
          }}
        />
        <button className="btn primary" disabled={!text.trim()} onClick={() => onAnswer(text.trim())}>{secret ? "Save" : "Send"}</button>
      </div>
    </div>
  );
}

function Composer({ busy, onSend }: { busy: boolean; onSend: (text: string) => Promise<void> }) {
  const [text, setText] = useState("");
  const area = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = area.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [text]);
  const send = async () => {
    const value = text.trim();
    if (!value) return;
    setText("");
    await onSend(value);
  };
  return (
    <div className="composer">
      <div className="composer-box">
        <textarea
          ref={area}
          rows={1}
          value={text}
          placeholder={busy ? "Lyra is working — write anyway, she'll read it next…" : "Message Lyra…"}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <button className="send" onClick={() => void send()} disabled={!text.trim()} aria-label="Send">↑</button>
      </div>
      <div className="hint">Enter to send · Shift+Enter for a new line</div>
    </div>
  );
}
