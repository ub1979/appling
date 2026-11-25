import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type AiConnection, type AgentModelSetting, type AiSettings, type ConnectionTestResult, type ModelOptions, type ModelSelection, type ProjectDetail } from "../api";
import { WorkerSettings } from "../components/WorkerSettings";
import { PhoneConnections } from "../components/PhoneConnections";
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
        <p>Choose Codex, Claude Code, Copilot, local Ollama models, or an API connection. Changes apply to the next task.</p>
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
          <PrimaryModel
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

          <section className="card card-pad">
            <h2 style={{ fontSize: 20 }}>Agent models</h2>
            <p className="muted small">Choose a provider, model and effort for each agent. Saved choices apply to future tasks in all projects. Appling leads the Requirements interview and uses the Requirements model for its draft review.</p>
            {settings.agent_models.map((agent) => (
              <AgentModel key={agent.id} agent={agent} options={options}
                onSave={async (selection) => {
                  setSettings(await api.agentModelSave(agent.id, selection));
                  setNote(`${agent.label} model saved.`);
                }} />
            ))}
          </section>

          <WorkerSettings value={settings.parallel_work.max_workers}
            agentsPerProject={settings.parallel_work.agents_per_project ?? 3}
            onSave={async (parallel_work) => {
              setSettings(await api.settingsSave({ parallel_work }));
              setNote("Worker limits saved. Active work continues safely.");
            }} />

          <Connections settings={settings} options={options} onSave={async (id, connection) => {
            setSettings(await api.settingsSave({ connections: { [id]: connection } }));
            await loadModels(true);
          }} />

          <PhoneConnections />

          <AboutMe
            initial={settings.about_me}
            onSave={(text) => run(async () => setSettings(await api.settingsSave({ about_me: text })), "Saved. Open projects will offer to use it.")}
          />

          {project && (
            <section className="card card-pad">
              <h2 style={{ fontSize: 20 }}>This project: {project.name}</h2>
              <label><span className="field-label">Build coordination</span>
                <select value={project.execution_mode ?? "planned"} disabled={project.running}
                  onChange={event => { const execution_mode = event.target.value; void run(async () => {
                    const updated = await api.settings(project.id, { execution_mode }) as ProjectDetail;
                    if (updated.execution_mode !== execution_mode) throw new Error("Restart Appling to load build coordination settings.");
                    setProject(updated);
                  }, "Saved. Return to the project and send a message to continue."); }}>
                  <option value="direct">One builder, step by step</option>
                  <option value="blocks">Blocks built in parallel, then joined</option>
                  <option value="planned">Review a separate implementation plan</option>
                </select>
              </label>
              <p className="small muted">Appling keeps requirements, approvals and independent QA. The coding engine can call specialists and coordinate their work. Changing this setting preserves files and saved handoffs.</p>
              <p style={{ margin: "14px 0 4px" }}><b>{project.engine}</b> · Project memory stays with Appling</p>
              <p className="muted small">Uses the saved model and effort for each agent.</p>
            </section>
          )}
        </div>
      )}
    </div>
  );
}

export function PrimaryModel({
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
  const [customModel, setCustomModel] = useState(false);
  useEffect(() => {
    setProvider(settings.hermes.provider);
    setModel(settings.hermes.model);
  }, [settings.hermes.provider, settings.hermes.model]);
  const models = useMemo(() => providers.find((p) => p.slug === provider)?.models ?? [], [providers, provider]);
  const selectedProvider = providers.find((p) => p.slug === provider);
  const supportsDefault = ["codex", "claude-cli", "copilot"].includes(settings.connections[provider]?.engine ?? "");
  const changed = provider !== settings.hermes.provider || model !== settings.hermes.model;

  return (
    <section className="card card-pad">
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
        <div>
          <h2 style={{ fontSize: 20 }}>Appling’s model</h2>
          <p className="muted small" style={{ margin: "4px 0 0" }}>
            Now: <b>{settings.hermes.model || providers.find((item) => item.slug === settings.hermes.provider)?.default_model || "the connection’s default model"}</b>
            {settings.hermes.provider ? ` · ${providers.find((p) => p.slug === settings.hermes.provider)?.name ?? settings.hermes.provider}` : ""}
          </p>
        </div>
        <button className="btn ghost small" onClick={onRefresh} disabled={loading}>{loading ? "Checking…" : "↻ Refresh list"}</button>
      </div>
      {providers.length === 0 ? (
        <p className="muted small">{loading ? "Looking for your linked models…" : "Configure a connection below."}</p>
      ) : (
        <div className="folder-row" style={{ marginTop: 16, gridTemplateColumns: "minmax(0,1fr) minmax(0,1.4fr) auto" }}>
          <label>
            <span className="field-label">Provider</span>
            <select className="input" value={provider} onChange={(e) => {
              setProvider(e.target.value);
              setModel(providers.find((p) => p.slug === e.target.value)?.models[0] ?? "");
              setCustomModel(false);
            }}>
              {!providers.some((p) => p.slug === provider) && <option value={provider}>{provider || "Choose…"}</option>}
              {providers.map((p) => <option key={p.slug} value={p.slug}>{PROVIDER_HINTS[p.slug] ? `${p.name} — ${PROVIDER_HINTS[p.slug]}` : p.name}</option>)}
            </select>
          </label>
          <label>
            <span className="field-label">Model</span>
            <select className="input" aria-label="Appling model" value={customModel ? ":custom-model:" : model} onChange={(event) => {
              const custom = event.target.value === ":custom-model:";
              setCustomModel(custom); setModel(custom ? "" : event.target.value);
            }}>
              <option value="">{supportsDefault ? `CLI default${selectedProvider?.default_model ? ` · ${selectedProvider.default_model}` : ""}` : "Choose a model"}</option>
              {model && !customModel && !models.includes(model) && <option value={model}>{model} (saved)</option>}
              {models.map((m) => <option key={m} value={m}>{m}</option>)}
              <option value=":custom-model:">Enter a custom model ID…</option>
            </select>
          </label>
          <button className="btn primary" disabled={!changed || !provider || (!model && !supportsDefault)} onClick={() => void onSave(provider, model || "default", false)}>
            Use this model
          </button>
        </div>
      )}
      {customModel && <label><span className="field-label">Custom model ID</span><input className="input" value={model} onChange={(event) => setModel(event.target.value)} placeholder="Enter the provider’s model ID" /></label>}
      <DiscoveryStatus provider={selectedProvider} />
      <ConnectionCheck key={`${provider}:${model}`} provider={provider} model={model} disabled={!provider || (!model && !supportsDefault)} />
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
          A per-model setting in the connection settings gives {settings.hermes.model} effort “{effortName(settings.hermes_effort.effective)}”, and it wins over this one.
        </p>
      )}
    </section>
  );
}

function Connections({ settings, options, onSave }: { settings: AiSettings; options: ModelOptions | null; onSave: (id: string, value: AiConnection) => Promise<void> }) {
  const [id, setId] = useState("ollama-local");
  const [value, setValue] = useState<AiConnection>(settings.connections[id]);
  const [problem, setProblem] = useState("");
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [testModel, setTestModel] = useState("");
  const provider = options?.providers.find((item) => item.slug === id);
  const changed = JSON.stringify(value) !== JSON.stringify(settings.connections[id]);
  const select = (key: string) => {
    setId(key); setValue(settings.connections[key] ?? { engine: "openai-compatible", label: "Custom API", models: [] }); setNotice(""); setTestModel("");
  };
  const save = async () => {
    setSaving(true); setProblem("");
    try { await onSave(id, value); setNotice("Connection saved."); }
    catch (error) { setProblem(error instanceof Error ? error.message : String(error)); }
    finally { setSaving(false); }
  };
  return <section className="card card-pad">
    <h2 style={{ fontSize: 20 }}>AI connections</h2>
    <p className="muted small">CLI connections use their existing login. API keys stay in environment variables; never paste them into chat. No automatic provider fallback.</p>
    <div className="agent-status">{settings.installed.map((item) => <p key={item.id} className="small">{item.installed ? "✓" : "○"} {item.label} · {item.installed ? "installed" : "not installed"}</p>)}</div>
    <label><span className="field-label">Connection</span><select className="input" value={id in settings.connections ? id : ":new:"} onChange={(event) => select(event.target.value === ":new:" ? "custom-api" : event.target.value)}>
      {Object.entries(settings.connections).map(([key, connection]) => <option key={key} value={key}>{connection.label}</option>)}
      <option value=":new:">Add a custom API</option>
    </select></label>
    <label><span className="field-label">Name</span><input className="input" value={value.label} onChange={(event) => setValue({ ...value, label: event.target.value })} /></label>
    <label><span className="field-label">Engine</span><select className="input" value={value.engine} onChange={(event) => setValue({ ...value, engine: event.target.value })}>
      {[["codex", "Codex CLI"], ["claude-cli", "Claude Code CLI"], ["copilot", "Copilot CLI"], ["ollama", "Ollama"], ["openai-compatible", "OpenAI-compatible API"], ["anthropic", "Anthropic API"]].map(([key, label]) => <option key={key} value={key}>{label}</option>)}
    </select></label>
    {["ollama", "openai-compatible", "anthropic"].includes(value.engine) && <>
      <label><span className="field-label">API base URL</span><input className="input" placeholder="http://127.0.0.1:11434/v1" value={value.base_url ?? ""} onChange={(event) => setValue({ ...value, base_url: event.target.value })} /></label>
      <label><span className="field-label">API key environment variable name</span><input className="input" placeholder="OPENAI_API_KEY" value={value.api_key_env ?? ""} onChange={(event) => setValue({ ...value, api_key_env: event.target.value })} /></label>
    </>}
    <label><span className="field-label">Model IDs (comma separated; Ollama also discovers installed models)</span><input className="input" value={(value.models ?? []).join(", ")} onChange={(event) => setValue({ ...value, models: event.target.value.split(",").map((model) => model.trim()).filter(Boolean) })} /></label>
    <button className="btn primary" disabled={saving} style={{ marginTop: 12 }} onClick={() => void save()}>{saving ? "Saving…" : "Save connection"}</button>
    <DiscoveryStatus provider={provider} />
    <label><span className="field-label">Model to test</span><input className="input" list="test-models" value={testModel} onChange={(event) => setTestModel(event.target.value)} placeholder={["codex", "claude-cli", "copilot"].includes(value.engine) ? "Leave empty for the CLI default" : "Choose or enter a model ID"} /></label>
    <datalist id="test-models">{provider?.models.map((model) => <option key={model} value={model} />)}</datalist>
    {changed && <p className="small muted">Save the connection changes before testing.</p>}
    <ConnectionCheck key={`${id}:${testModel}`} provider={id} model={testModel} disabled={changed || (!testModel && !["codex", "claude-cli", "copilot"].includes(value.engine))} />
    {(problem || notice) && <p className="small" role="status">{problem || notice}</p>}
  </section>;
}

export function DiscoveryStatus({ provider }: { provider?: ModelOptions["providers"][number] }) {
  if (!provider?.status) return null;
  return <p className={`small ${["error", "login_required"].includes(provider.status.state) ? "" : "muted"}`} role="status">{provider.status.message}</p>;
}

export function ConnectionCheck({ provider, model, disabled = false }: { provider: string; model: string; disabled?: boolean }) {
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<ConnectionTestResult | null>(null);
  const [problem, setProblem] = useState("");
  useEffect(() => { setResult(null); setProblem(""); }, [provider, model]);
  const test = async () => {
    setChecking(true); setResult(null); setProblem("");
    try { setResult(await api.testConnection(provider, model)); }
    catch (error) { setProblem(error instanceof Error ? error.message : String(error)); }
    finally { setChecking(false); }
  };
  return <div style={{ marginTop: 12 }}>
    <button className="btn small" disabled={disabled || checking} onClick={() => void test()}>{checking ? "Testing connection…" : "Test connection"}</button>
    <p className="tiny muted">Sends a short test prompt to this model using its account quota. No project files are sent.</p>
    {result && <p className="small" role="status">{result.ok ? "✓ Connected" : "Connection failed"} · {result.message}{result.ok ? ` ${result.model} · ${(result.latency_ms / 1000).toFixed(1)}s` : ""}</p>}
    {problem && <p className="small" role="alert">{problem}</p>}
  </div>;
}

interface AgentModelProps {
  agent: AgentModelSetting;
  options: ModelOptions | null;
  onSave: (selection: ModelSelection | null) => Promise<void>;
}

export function AgentModel({ agent, options, onSave }: AgentModelProps) {
  const initial = agent.selection ?? agent.default;
  const [provider, setProvider] = useState(initial?.provider ?? "");
  const [model, setModel] = useState(initial?.model ?? "");
  const [effort, setEffort] = useState(initial?.effort ?? "");
  const [customModel, setCustomModel] = useState(false);
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const providers = options?.providers ?? [];
  const models = providers.find((p) => p.slug === provider)?.models ?? [];
  const status = initial
    ? `${initial.model}${initial.effort ? ` · ${effortName(initial.effort)}` : ""}`
    : "Appling’s model";

  const save = async (selection: ModelSelection | null) => {
    setSaving(true);
    setProblem(null);
    try {
      await onSave(selection);
      if (!selection) {
        setProvider(agent.default?.provider ?? "");
        setModel(agent.default?.model ?? "");
        setEffort(agent.default?.effort ?? "");
        setCustomModel(false);
      }
    } catch (e) {
      setProblem(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <details className="agent-model">
      <summary><b>{agent.label}</b><span className="muted small">{status}{agent.selection ? "" : " · Default"}</span></summary>
      <div className="agent-model-fields">
        <label>
          <span className="field-label">Provider</span>
          <select className="input" value={provider} onChange={(e) => {
            const chosen = e.target.value;
            setProvider(chosen);
            setModel(providers.find((p) => p.slug === chosen)?.models[0] ?? "");
            setCustomModel(false);
          }}>
            <option value="">Choose a provider</option>
            {provider && !providers.some((p) => p.slug === provider) && <option value={provider}>{provider}</option>}
            {providers.map((p) => <option key={p.slug} value={p.slug}>{p.name}</option>)}
          </select>
        </label>
        <label>
          <span className="field-label">Model</span>
          <select className="input" aria-label={`${agent.label} model`}
            value={customModel ? ":custom-model:" : model}
            onChange={(e) => {
              const custom = e.target.value === ":custom-model:";
              setCustomModel(custom);
              setModel(custom ? "" : e.target.value);
            }}>
            <option value="">Choose a model</option>
            {!customModel && model && !models.includes(model) && <option value={model}>{model} (saved)</option>}
            {models.map((m) => <option key={m} value={m}>{m}</option>)}
            <option value=":custom-model:">Enter a custom model ID…</option>
          </select>
        </label>
        {customModel && (
          <label>
            <span className="field-label">Custom model ID</span>
            <input className="input" value={model} onChange={(e) => setModel(e.target.value)}
              placeholder="Enter the provider’s model ID" autoFocus />
          </label>
        )}
        <label>
          <span className="field-label">Effort</span>
          <select className="input" value={effort} onChange={(e) => setEffort(e.target.value)}>
            <option value="">Appling’s effort</option>
            {HERMES_EFFORT_LEVELS.map((l) => <option key={l.id} value={l.id}>{effortName(l.id)}</option>)}
          </select>
        </label>
      </div>
      {problem && <p className="small" role="alert">{problem}</p>}
      <DiscoveryStatus provider={providers.find((item) => item.slug === provider)} />
      <ConnectionCheck key={`${provider}:${model}`} provider={provider} model={model} disabled={!provider || (!model && !["codex", "claude-cli", "copilot"].includes(provider))} />
      <div className="dialog-actions">
        {agent.selection && <button className="btn small" disabled={saving} onClick={() => void save(null)}>Reset default</button>}
        <button className="btn primary small" disabled={saving || !provider || !model.trim()}
          onClick={() => void save({ provider, model: model.trim(), effort })}>Save model</button>
      </div>
    </details>
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
