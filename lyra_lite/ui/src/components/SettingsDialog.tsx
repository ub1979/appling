import { useEffect, useState } from "react";
import { api, type ProjectDetail } from "../api";

export function SettingsDialog({
  detail,
  busy,
  onClose,
  onSave,
}: {
  detail: ProjectDetail;
  busy: boolean;
  onClose: () => void;
  onSave: (body: Record<string, unknown>) => Promise<void>;
}) {
  const [engine, setEngine] = useState(detail.engine || "hermes");
  const [model, setModel] = useState(detail.claude?.model ?? "");
  const [baseUrl, setBaseUrl] = useState(detail.claude?.base_url ?? "");
  const [token, setToken] = useState("");
  const [hasKey, setHasKey] = useState<boolean | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    void api.engines().then((e) => setHasKey(e.anthropic_key)).catch(() => setHasKey(null));
  }, []);

  const save = async () => {
    try {
      const body: Record<string, unknown> = { engine };
      if (engine === "claude") {
        body.claude = { model, base_url: baseUrl, ...(token ? { auth_token: token } : {}) };
      }
      await onSave(body);
    } catch (e) {
      setProblem(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h2>Engine for this project</h2>
        <label className="radio-row">
          <input type="radio" checked={engine === "hermes"} onChange={() => setEngine("hermes")} />
          <span>
            <b>Hermes</b>
            <span className="muted small"> — uses the model you linked in Lyra (Codex, Ollama, Copilot, Claude, …)</span>
          </span>
        </label>
        <label className="radio-row">
          <input type="radio" checked={engine === "claude"} onChange={() => setEngine("claude")} />
          <span>
            <b>Claude Code</b>
            <span className="muted small"> — Anthropic's agent. Needs an Anthropic API key, or a model address such as Ollama.</span>
          </span>
        </label>
        {engine === "claude" && (
          <div className="settings-box">
            <label className="small muted">Model</label>
            <input value={model} placeholder="claude-opus-5-5 (or an Ollama model, e.g. qwen3-coder)" onChange={(e) => setModel(e.target.value)} />
            <label className="small muted">Model address (leave empty to use your Anthropic API key)</label>
            <input value={baseUrl} placeholder="e.g. http://localhost:11434 for Ollama" onChange={(e) => setBaseUrl(e.target.value)} />
            {baseUrl && (
              <>
                <label className="small muted">Access token for that address (Ollama: leave empty)</label>
                <input type="password" value={token} onChange={(e) => setToken(e.target.value)} />
              </>
            )}
            {!baseUrl && hasKey === false && (
              <p className="problem small">
                No Anthropic API key found. Add ANTHROPIC_API_KEY to ~/.hermes/.env (or run <code>hermes setup</code>), then restart Lyra.
              </p>
            )}
            <p className="muted small">Switching engines keeps this chat: the new engine reads the conversation so far.</p>
          </div>
        )}
        {busy && <p className="muted small">Lyra is working — you can switch when it's idle.</p>}
        {problem && <p className="problem small">{problem}</p>}
        <div className="dialog-actions">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={busy} onClick={() => void save()}>Save</button>
        </div>
      </div>
    </div>
  );
}

