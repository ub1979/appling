import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type AiSettings, type ModelOptions, type ProjectDetail } from "../api";
import { Brand, PrefButtons } from "../components/common";
import { DEFAULT_EFFORT_LABEL, HERMES_EFFORT_LEVELS, effortName } from "../effort";
import { go } from "../router";

// Plain-language billing hints for the providers people mix up.
const PROVIDER_HINTS: Record<string, string> = {
  "claude-cli": "your Claude subscription",
  "openai-codex": "your ChatGPT/Codex subscription",
  anthropic: "Anthropic API key, pay per use",
  "ollama-local": "models on this computer",
};

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
        <h1>Model and effort</h1>
        <p>Every project runs on Hermes. Model and effort changes apply from the next message.</p>
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
                setNote(`Appling now uses ${model}.`);
              })
            }
            onSaveEffort={(effort) =>
              run(async () => {
                await api.effortSave(effort);
                setSettings(await api.settingsGet());
              }, `Effort saved: ${effortName(effort)}. Applies from the next message.`)
            }
          />

          <AboutMe
            initial={settings.about_me}
            onSave={(text) => run(async () => setSettings(await api.settingsSave({ about_me: text })), "Saved. Open projects will offer to use it.")}
          />

          {project && (
            <section className="card card-pad">
              <h2 style={{ fontSize: 20 }}>This project: {project.name}</h2>
              <p style={{ margin: "14px 0 4px" }}><b>Hermes</b> · Locked to this project</p>
              <p className="muted small">Uses the model and effort settings above.</p>
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
  onSaveEffort,
}: {
  settings: AiSettings;
  options: ModelOptions | null;
  loading: boolean;
  onRefresh: () => void;
  onSave: (provider: string, model: string, confirm: boolean) => Promise<void>;
  onSaveEffort: (effort: string) => Promise<void>;
}) {
  const providers = options?.providers ?? [];
  const [effort, setEffort] = useState(settings.hermes_effort.effort);
  useEffect(() => {
    setEffort(settings.hermes_effort.effort);
  }, [settings.hermes_effort.effort]);
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
              {providers.map((p) => <option key={p.slug} value={p.slug}>{PROVIDER_HINTS[p.slug] ? `${p.name} — ${PROVIDER_HINTS[p.slug]}` : p.name}</option>)}
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
      <div className="folder-row" style={{ marginTop: 12, gridTemplateColumns: "minmax(0,1fr) auto" }}>
        <label>
          <span className="field-label">Effort</span>
          <select className="input" value={effort} onChange={(e) => setEffort(e.target.value)}>
            <option value="">{DEFAULT_EFFORT_LABEL}</option>
            {HERMES_EFFORT_LEVELS.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
          </select>
        </label>
        <button className="btn primary" disabled={effort === settings.hermes_effort.effort} onClick={() => void onSaveEffort(effort)}>
          Save
        </button>
      </div>
      {settings.hermes_effort.overridden && (
        <p className="small muted" style={{ margin: "8px 0 0" }}>
          A per-model setting in config.yaml gives {settings.hermes.model} effort “{effortName(settings.hermes_effort.effective)}”, and it wins over this one.
        </p>
      )}
    </section>
  );
}

function AboutMe({ initial, onSave }: { initial: string; onSave: (text: string) => Promise<void> }) {
  const [text, setText] = useState(initial);
  return (
    <section className="card card-pad">
      <h2 style={{ fontSize: 20 }}>About me</h2>
      <p className="muted small" style={{ margin: "4px 0 0" }}>
        The only thing Appling carries between projects. Everything else stays inside each project's own memory.
      </p>
      <textarea
        className="textarea"
        style={{ marginTop: 14 }}
        maxLength={2000}
        value={text}
        placeholder="e.g. Explain things simply, I'm not a programmer. I use an Android phone. Keep apps small and good-looking."
        onChange={(e) => setText(e.target.value)}
      />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
        <span className="tiny muted">{text.length} / 2000</span>
        <button className="btn primary" disabled={text === initial} onClick={() => void onSave(text)}>Save</button>
      </div>
    </section>
  );
}
