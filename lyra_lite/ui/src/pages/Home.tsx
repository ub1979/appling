import { useEffect, useState } from "react";
import { api, type Catalog, type ProjectSummary } from "../api";
import { AvatarStack, Brand, PrefButtons } from "../components/common";
import { go } from "../router";

function ago(ts: number): string {
  if (!ts) return "";
  const mins = Math.round((Date.now() / 1000 - ts) / 60);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

export function Home() {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [version, setVersion] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [deleteProblem, setDeleteProblem] = useState<string | null>(null);

  const deleteProject = async (project: ProjectSummary) => {
    if (!window.confirm(`Delete "${project.name}" from your projects? Its folder, files and saved chats will move to Appling Projects/Archive.`)) return;
    setDeleting(project.id);
    setDeleteProblem(null);
    try {
      const result = await api.deleteProject(project.id);
      setProjects((all) => all?.filter((p) => p.id !== project.id) ?? null);
      setNotice(`Project moved to ${result.archived_to}`);
    } catch (e) {
      setDeleteProblem(e instanceof Error ? e.message : String(e));
    } finally {
      setDeleting(null);
    }
  };

  useEffect(() => {
    const load = () =>
      api.projects().then((d) => {
        setProjects(d.projects);
        setVersion(d.version ?? "");
        setProblem(null);
      }).catch((e) => setProblem(e instanceof Error ? e.message : String(e)));
    void load();
    void api.catalog().then(setCatalog).catch(() => undefined);
    const timer = window.setInterval(load, 8000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="page">
      <header className="topbar">
        <Brand sub="Your software workspace" />
        <div className="top-actions">
          {problem ? <span className="pill need">Can't reach Appling</span> : <span className="status-dot">Ready</span>}
          <span className="version">Appling {version}</span>
          <PrefButtons onAi={() => go("/settings")} />
        </div>
      </header>

      <section className="hero">
        <div>
          <p className="kicker">Your AI product studio</p>
          <h1>Turn an idea into software.</h1>
          <p className="lead">
            Describe what you want to create. Appling brings in the right agents, keeps the work moving, and shows you what
            is ready—without the technical noise.
          </p>
          <div className="ticks">
            <span>Local projects</span>
            <span>Saved progress</span>
            <span>You approve key steps</span>
          </div>
        </div>
        <div className="card flow-card">
          <p className="kicker" style={{ color: "var(--muted)", letterSpacing: ".12em", fontFamily: "var(--font)", fontSize: 12 }}>
            From idea to working product
          </p>
          {[
            ["01", "Shape", "Clarify the product"],
            ["02", "Build", "Create and improve"],
            ["03", "Verify", "Test before delivery"],
          ].map(([n, t, d]) => (
            <div className="flow-step" key={n}>
              <span className="num-badge">{n}</span>
              <span>
                <b>{t}</b>
                <span>{d}</span>
              </span>
            </div>
          ))}
        </div>
      </section>

      {(notice || problem || deleteProblem) && <div className={`banner ${problem || deleteProblem ? "bad" : "good"}`} role="status">{deleteProblem ?? problem ?? notice}</div>}

      {projects && projects.length > 0 && (
        <>
          <div className="section-head">
            <span className="num-badge">↺</span>
            <div>
              <h2>Continue a project</h2>
              <p>Everything is saved — pick up where Appling left off.</p>
            </div>
          </div>
          <div className="recent-grid">
            {projects.map((p) => (
              <div key={p.id} className="recent-project">
              <button className="recent-card" disabled={deleting === p.id} onClick={() => go(`/p/${p.id}`)}>
                <div className="recent-row">
                  <b>{p.name}</b>
                  {p.inbox > 0 ? (
                    <span className="pill need">Needs you</span>
                  ) : p.running ? (
                    <span className="pill busy">Working</span>
                  ) : (
                    <span className="pill">{ago(p.updated)}</span>
                  )}
                </div>
                <span className="path"><bdi>{p.root}</bdi></span>
                <div className="recent-row">
                  <AvatarStack ids={["app-it", ...p.team]} />
                  <span className="tiny muted">Codex</span>
                </div>
              </button>
              <button className="btn small danger" disabled={p.running || deleting !== null}
                title={p.running ? "Stop Appling and its agents before deleting this project" : "Move this project to Archive"}
                onClick={() => void deleteProject(p)}>
                {deleting === p.id ? "Moving to archive…" : "Delete project"}
              </button>
              </div>
            ))}
          </div>
        </>
      )}

      <div className="section-head">
        <span className="num-badge">01</span>
        <div>
          <h2>Start building</h2>
          <p>Begin fresh or continue from code you already have.</p>
        </div>
      </div>
      <div className="start-grid">
        <button className="start-card featured" onClick={() => go("/new")}>
          <span className="start-icon">+</span>
          <span>
            <b>Create a new project</b>
            <span className="desc">Start with an idea and let Appling guide the build.</span>
          </span>
          <span className="arrow">→</span>
        </button>
        <button className="start-card" onClick={() => go("/open")}>
          <span className="start-icon">↗</span>
          <span>
            <b>Open an existing project</b>
            <span className="desc">Choose a folder and decide what to improve next.</span>
          </span>
          <span className="arrow">→</span>
        </button>
      </div>

      <div className="section-head">
        <span className="num-badge">02</span>
        <div>
          <h2>Choose a starting style</h2>
          <p>Appling can adjust the team later as your project takes shape.</p>
        </div>
      </div>
      <div className="style-grid">
        {(catalog?.styles ?? []).map((s) => (
          <button key={s.id} className="style-card" onClick={() => go(`/new?style=${s.id}`)}>
            <span className={`bar accent-${s.accent}`} style={{ display: "block" }} />
            <span className="count">{Math.max(2, new Set([...s.team, "req-engineer", "task-planner"]).size)} agents</span>
            <b>{s.name}</b>
            <p>{s.description}</p>
          </button>
        ))}
      </div>
    </div>
  );
}
