import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type AiSettings, type ModelOptions, type ProjectDetail } from "../api";
import { Brand, PrefButtons } from "../components/common";
import { go } from "../router";

const ENGINE_CARDS = [
  {
    id: "hermes",
    name: "Hermes",
    text: "Lyra's own engine. Works with any model you've linked — Codex, Ollama, Copilot, Claude and more.",
  },
  {
    id: "claude",
    name: "Claude Code",
    text: "Anthropic's coding agent. Needs an Anthropic API key, or a model address such as Ollama.",
  },
];

export function Settings({ projectId }: { projectId: string | null }) {
  const [settings, setSettings] = useState<AiSettings | null>(null);
  const [options, setOptions] = useState<ModelOptions | null>(null);
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [loadingModels, setLoadingModels] = useState(false);

  const run = useCallback(async (action: () => Promise<void>, done?: string) => {
    try {
      setProblem(null);
      await action();
      if (done) setNote(done);
    } catch (e) {
      setProblem(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const loadModels = useCallback(async (refresh = false) => {
    setLoadingModels(true);
    try {
      setOptions(await api.modelOptions(refresh));
    } catch (e) {
      setProblem(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingModels(false);
    }
  }, []);

  useEffect(() => {
    void run(async () => setSettings(await api.settingsGet()));
    void loadModels();
    if (projectId) void api.project(projectId).then(setProject).catch(() => undefined);
  }, [projectId, run, loadModels]);

  const back = () => go(projectId ? `/p/${projectId}` : "/");

  return (
    <div className="page">
      <header className="topbar">
        <button className="btn ghost" onClick={back}>← {projectId ? "Back to project" : "Projects"}</button>
        <Brand sub="Settings" onClick={() => go("/")} />
        <div className="top-actions"><PrefButtons /></div>
      </header>

      <div className="setup-head">
        <p className="kicker">AI settings</p>
        <h1>Engine and model</h1>
        <p>Choose how Lyra thinks. Changes apply from Lyra's next message; anything already running finishes as it started.</p>
      </div>

      {(note || problem) && (
        <div className={`banner ${problem ? "bad" : "good"}`} style={{ borderRadius: 14, marginBottom: 18 }}>
          {problem ?? note}
        </div>
      )}

      {!settings ? (
        <p className="muted">Loading…</p>
      ) : (
        <div className="settings-grid">
          <section className="card card-pad">
            <h2 style={{ fontSize: 20 }}>Engine</h2>
            <p className="muted small" style={{ margin: "4px 0 0" }}>Used by every project that doesn't pick its own.</p>
            <div className="profile-grid two">
              {ENGINE_CARDS.map((e) => (
                <button
                  key={e.id}
                  type="button"
                  className={`profile-card ${settings.engine === e.id ? "on" : ""}`}
                  onClick={() => void run(async () => setSettings(await api.settingsSave({ engine: e.id })), `${e.name} is now Lyra's engine.`)}
                >
                  <span className="radio" />
                  <b>{e.name}</b>
                  <span>{e.text}</span>
                </button>
              ))}
            </div>
          </section>

          {settings.engine === "hermes" ? (
            <HermesModel
              settings={settings}
              options={options}
              loading={loadingModels}
              onRefresh={() => void loadModels(true)}
              onSave={(provider, model, confirm) =>
                run(async () => {
                  const res = await api.modelSave(provider, model, confirm);
                  if (res.confirm_required) {
                    if (window.confirm(`${res.message}\n\nUse it anyway?`)) {
                      await api.modelSave(provider, model, true);
                    } else {
                      return;
                    }
                  }
                  setSettings(await api.settingsGet());
                  setNote(`Lyra now uses ${model}.`);
                })
              }
            />
          ) : (
            <ClaudeModel
              settings={settings}
              suggestions={options?.providers.find((p) => p.slug === "anthropic")?.models ?? []}
              onSave={(claude) => run(async () => setSettings(await api.settingsSave({ claude })), "Claude Code settings saved.")}
            />
          )}

          {project && (
            <section className="card card-pad">
              <h2 style={{ fontSize: 20 }}>This project: {project.name}</h2>
              <p className="muted small" style={{ margin: "4px 0 0" }}>Usually a project follows Lyra's engine. You can pin one for this project only.</p>
              <div className="stack" style={{ marginTop: 14 }}>
                {[
                  { id: "default", label: `Follow Lyra's engine (now ${settings.engine === "claude" ? "Claude Code" : "Hermes"})` },
                  { id: "hermes", label: "Always use Hermes for this project" },
                  { id: "claude", label: "Always use Claude Code for this project" },
                ].map((o) => {
                  const current = project.engine_override ? project.engine : "default";
                  return (
                    <button
                      key={o.id}
                      type="button"
                      className={`style-option ${current === o.id ? "on" : ""}`}
                      onClick={() =>
                        void run(async () => {
                          await api.settings(project.id, { engine: o.id });
                          setProject(await api.project(project.id));
                        }, "Saved for this project.")
                      }
                    >
                      <span className="radio" />
                      <span><b>{o.label}</b></span>
                    </button>
                  );
                })}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}

function HermesModel({
  settings,
  options,
  loading,
  onRefresh,
  onSave,
}: {
  settings: AiSettings;
  options: ModelOptions | null;
  loading: boolean;
  onRefresh: () => void;
  onSave: (provider: string, model: string, confirm: boolean) => Promise<void>;
}) {
  const providers = options?.providers ?? [];
  const [provider, setProvider] = useState(settings.hermes.provider);
  const [model, setModel] = useState(settings.hermes.model);
  useEffect(() => {
    setProvider(settings.hermes.provider);
    setModel(settings.hermes.model);
  }, [settings.hermes.provider, settings.hermes.model]);
  const models = useMemo(() => providers.find((p) => p.slug === provider)?.models ?? [], [providers, provider]);
  const changed = provider !== settings.hermes.provider || model !== settings.hermes.model;

  return (
    <section className="card card-pad">
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
        <div>
          <h2 style={{ fontSize: 20 }}>Model</h2>
          <p className="muted small" style={{ margin: "4px 0 0" }}>
            Now: <b>{settings.hermes.model || "not set"}</b>
            {settings.hermes.provider ? ` · ${providers.find((p) => p.slug === settings.hermes.provider)?.name ?? settings.hermes.provider}` : ""}
          </p>
        </div>
        <button className="btn ghost small" onClick={onRefresh} disabled={loading}>{loading ? "Checking…" : "↻ Refresh list"}</button>
      </div>
      {providers.length === 0 ? (
        <p className="muted small">{loading ? "Looking for your linked models…" : "No linked models found. Link a provider in the old Studio or with `hermes setup`."}</p>
      ) : (
        <div className="folder-row" style={{ marginTop: 16, gridTemplateColumns: "minmax(0,1fr) minmax(0,1.4fr) auto" }}>
          <label>
            <span className="field-label">Provider</span>
            <select className="input" value={provider} onChange={(e) => {
              setProvider(e.target.value);
              setModel(providers.find((p) => p.slug === e.target.value)?.models[0] ?? "");
            }}>
              {!providers.some((p) => p.slug === provider) && <option value={provider}>{provider || "Choose…"}</option>}
              {providers.map((p) => <option key={p.slug} value={p.slug}>{p.name}</option>)}
            </select>
          </label>
          <label>
            <span className="field-label">Model</span>
            <select className="input" value={model} onChange={(e) => setModel(e.target.value)}>
              {!models.includes(model) && <option value={model}>{model || "Choose…"}</option>}
              {models.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </label>
          <button className="btn primary" disabled={!changed || !provider || !model} onClick={() => void onSave(provider, model, false)}>
            Use this model
          </button>
        </div>
      )}
    </section>
  );
}

function ClaudeModel({
  settings,
  suggestions,
  onSave,
}: {
  settings: AiSettings;
  suggestions: string[];
  onSave: (claude: Record<string, string>) => Promise<void>;
}) {
  const [model, setModel] = useState(settings.claude.model);
  const [baseUrl, setBaseUrl] = useState(settings.claude.base_url);
  const [token, setToken] = useState("");
  return (
    <section className="card card-pad">
      <h2 style={{ fontSize: 20 }}>Claude Code model</h2>
      <div className="stack" style={{ marginTop: 14 }}>
        <label>
          <span className="field-label">Model</span>
          <input className="input" list="claude-models" value={model} placeholder="claude-opus-5-5 (or an Ollama model, e.g. qwen3-coder)" onChange={(e) => setModel(e.target.value)} />
          <datalist id="claude-models">{suggestions.map((m) => <option key={m} value={m} />)}</datalist>
        </label>
        <label>
          <span className="field-label">Model address — leave empty to use your Anthropic API key</span>
          <input className="input" value={baseUrl} placeholder="e.g. http://localhost:11434 for Ollama" onChange={(e) => setBaseUrl(e.target.value)} />
        </label>
        {baseUrl && (
          <label>
            <span className="field-label">Access token for that address {settings.claude.has_token ? "(saved — leave empty to keep it)" : "(Ollama: leave empty)"}</span>
            <input className="input" type="password" value={token} onChange={(e) => setToken(e.target.value)} />
          </label>
        )}
        {!baseUrl && (
          <p className={`small ${settings.anthropic_key ? "muted" : "problem"}`} style={{ margin: 0 }}>
            {settings.anthropic_key
              ? "✓ Anthropic API key found. Claude Code is billed per use by Anthropic."
              : "No Anthropic API key found. Add ANTHROPIC_API_KEY to ~/.hermes/.env (or run `hermes setup`) and restart Lyra — or use a model address such as Ollama."}
          </p>
        )}
        <div>
          <button className="btn primary" onClick={() => void onSave({ model, base_url: baseUrl, ...(token ? { auth_token: token } : {}) })}>
            Save
          </button>
        </div>
      </div>
    </section>
  );
}
