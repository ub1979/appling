import { useEffect, useMemo, useState } from "react";
import { api, type BuildProfile, type Catalog } from "../api";
import { AvatarStack, Brand, FolderDialog, PrefButtons, TeamPicker } from "../components/common";
import { go } from "../router";

const REQUIRED = ["req-engineer", "task-planner"];

const PROFILES: { id: BuildProfile; name: string; text: string }[] = [
  { id: "personal", name: "Personal / one-off", text: "For you, used now and then. The core features, basic safety and a real check — quick and light." },
  { id: "reusable", name: "Reusable project", text: "Used again and again. Stronger error handling, cleaner code, review and full testing." },
  { id: "production", name: "Production / public", text: "For other people or the public. Full security, deployment, performance and release checks." },
];

function withRequired(ids: string[]): string[] {
  return Array.from(new Set([...REQUIRED, ...ids]));
}

export function Setup({ mode, styleId }: { mode: "new" | "open"; styleId: string | null }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [parent, setParent] = useState("");
  const [name, setName] = useState("");
  const [folder, setFolder] = useState("");
  const [style, setStyle] = useState(styleId || (mode === "open" ? "review" : "app-it"));
  const [team, setTeam] = useState<string[]>(REQUIRED);
  const [customizing, setCustomizing] = useState(false);
  const [brief, setBrief] = useState("");
  const [profile, setProfile] = useState<BuildProfile>("personal");
  const [picking, setPicking] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    void api.catalog().then((c) => {
      setCatalog(c);
      setParent(c.default_root);
      const s = c.styles.find((x) => x.id === (styleId || (mode === "open" ? "review" : "app-it")));
      if (s) setTeam(withRequired(s.team));
    }).catch((e) => setProblem(e instanceof Error ? e.message : String(e)));
  }, [mode, styleId]);

  const chooseStyle = (id: string) => {
    setStyle(id);
    const s = catalog?.styles.find((x) => x.id === id);
    if (s) setTeam(withRequired(s.team));
  };

  const toggle = (id: string) =>
    setTeam((t) => (REQUIRED.includes(id) ? t : t.includes(id) ? t.filter((x) => x !== id) : [...t, id]));

  const orderedTeam = useMemo(
    () => (catalog ? catalog.agents.map((a) => a.id).filter((id) => team.includes(id)) : team),
    [catalog, team],
  );
  const path = mode === "new" ? (parent && name.trim() ? `${parent}/${name.trim()}` : "") : folder;
  const currentStyle = catalog?.styles.find((s) => s.id === style);

  const start = async () => {
    if (!path) return;
    setSaving(true);
    try {
      const res = await api.addProject({ path, create: mode === "new", team: orderedTeam, style, brief, profile });
      go(`/p/${res.id}`);
    } catch (e) {
      setProblem(e instanceof Error ? e.message : String(e));
      setSaving(false);
    }
  };

  return (
    <div className="page">
      <header className="topbar">
        <button className="btn ghost" onClick={() => go("/")}>← Projects</button>
        <Brand sub={mode === "new" ? "New project" : "Open a project"} onClick={() => go("/")} />
        <div className="top-actions">
          <PrefButtons />
        </div>
      </header>

      <div className="setup-head">
        <p className="kicker">{mode === "new" ? "Create something new" : "Continue existing work"}</p>
        <h1>{mode === "new" ? "Set up your new project" : "Open an existing project"}</h1>
        <p>
          {mode === "new"
            ? "Choose the folder and tell Lyra the outcome you want. Everything else can be adjusted later."
            : "Pick the folder with your code and tell Lyra what you'd like to improve."}
        </p>
      </div>

      <div className="setup-grid">
        <div className="setup-main">
          <section className="card card-pad">
            <h3>Project folder</h3>
            {mode === "new" ? (
              <div className="folder-row" style={{ marginTop: 16 }}>
                <label>
                  <span className="field-label">Save inside</span>
                  <input className="input" value={parent} onChange={(e) => setParent(e.target.value)} />
                </label>
                <button className="btn" onClick={() => setPicking(true)}>Browse</button>
                <label>
                  <span className="field-label">Project name</span>
                  <input className="input" value={name} placeholder="My new app" autoFocus onChange={(e) => setName(e.target.value)} />
                </label>
              </div>
            ) : (
              <div className="folder-row" style={{ marginTop: 16, gridTemplateColumns: "minmax(0,1fr) auto" }}>
                <label>
                  <span className="field-label">Folder</span>
                  <input className="input" value={folder} placeholder="Choose the project's folder" onChange={(e) => setFolder(e.target.value)} />
                </label>
                <button className="btn" onClick={() => setPicking(true)}>Browse</button>
              </div>
            )}
          </section>

          <section className="card card-pad">
            <h3>How much should Lyra build?</h3>
            <p className="muted small" style={{ margin: "4px 0 0" }}>This sets how big the plan, the checks and the team are. You can grow it later.</p>
            <div className="profile-grid">
              {PROFILES.map((p) => (
                <button key={p.id} type="button" className={`profile-card ${profile === p.id ? "on" : ""}`} onClick={() => setProfile(p.id)}>
                  <span className="radio" />
                  <b>{p.name}</b>
                  <span>{p.text}</span>
                </button>
              ))}
            </div>
          </section>

          <section className="card card-pad">
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
              <div>
                <h2 style={{ fontSize: 20 }}>Your starting team</h2>
                <p className="muted small" style={{ margin: "4px 0 0" }}>
                  {orderedTeam.length} of {catalog?.agents.length ?? 21} agents selected · Lyra can recommend changes later
                </p>
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
                {customizing && (
                  <>
                    <button className="btn ghost small" onClick={() => setTeam(withRequired(currentStyle?.team ?? []))}>Reset</button>
                    <button className="btn ghost small" onClick={() => setTeam(REQUIRED)}>Clear optional</button>
                  </>
                )}
                <button className="btn soft small" onClick={() => setCustomizing((c) => !c)}>
                  {customizing ? "Hide choices" : "Customize team"}
                </button>
              </div>
            </div>
            {customizing && catalog ? (
              <TeamPicker agents={catalog.agents} selected={orderedTeam} onToggle={toggle} />
            ) : (
              <div className="team-summary">
                <AvatarStack ids={orderedTeam} />
                <div style={{ flex: 1 }}>
                  <b>{orderedTeam.length} agents ready</b>
                  <div className="muted small">This team follows your starting style and can be changed at any time.</div>
                </div>
                <button className="btn ghost small" onClick={() => setCustomizing(true)}>Change →</button>
              </div>
            )}
          </section>

          <section className="card card-pad">
            <h3>What should Lyra help with?</h3>
            <textarea
              className="textarea"
              style={{ marginTop: 14 }}
              value={brief}
              placeholder={
                style === "app-it"
                  ? "Help me shape my idea and recommend the smallest useful agent team."
                  : "Describe the app or the change you want — a sentence or two is enough."
              }
              onChange={(e) => setBrief(e.target.value)}
            />
          </section>
        </div>

        <aside className="setup-side">
          <section className="card" style={{ padding: 16 }}>
            <h3 style={{ padding: "6px 8px 10px" }}>Starting style</h3>
            {(catalog?.styles ?? []).map((s) => (
              <button key={s.id} className={`style-option ${s.id === style ? "on" : ""}`} onClick={() => chooseStyle(s.id)}>
                <span className="radio" />
                <span>
                  <b>{s.name}</b>
                  <span>{s.description}</span>
                </span>
              </button>
            ))}
            <div className="team-count" style={{ marginTop: 12 }}>
              <div className="kicker" style={{ color: "var(--muted)", marginBottom: 6 }}>Starting team</div>
              <div className="big">{orderedTeam.length} agents</div>
              <div className="muted small">Lyra can recommend changes later and will ask before applying them.</div>
            </div>
            {problem && <p className="problem small">{problem}</p>}
            <button className="btn primary big" style={{ marginTop: 14 }} disabled={!path || saving} onClick={() => void start()}>
              {saving ? "Opening…" : "Enter project studio →"}
            </button>
            <p className="muted small" style={{ textAlign: "center", margin: "10px 0 0" }}>
              The project opens in a simple chat. Lyra handles tools and terminal work quietly in the background.
            </p>
          </section>
        </aside>
      </div>

      {picking && (
        <FolderDialog
          start={mode === "new" ? parent : folder || parent}
          title={mode === "new" ? "Where should the project live?" : "Choose the project folder"}
          pickLabel={mode === "new" ? "Save inside this folder" : "Open this folder"}
          onClose={() => setPicking(false)}
          onPick={(p) => {
            if (mode === "new") setParent(p);
            else setFolder(p);
            setPicking(false);
          }}
        />
      )}
    </div>
  );
}
