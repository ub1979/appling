import { useEffect, useState } from "react";

interface WorkerSettingsProps {
  value: number;
  agentsPerProject?: number;
  onSave: (limits: { max_workers: number; agents_per_project: number }) => Promise<void>;
}

export function WorkerSettings({ value, agentsPerProject = 3, onSave }: WorkerSettingsProps) {
  const [limit, setLimit] = useState(value);
  const [agents, setAgents] = useState(agentsPerProject);
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState("");
  useEffect(() => setLimit(value), [value]);
  useEffect(() => setAgents(agentsPerProject), [agentsPerProject]);
  const save = async () => {
    setSaving(true); setProblem("");
    try { await onSave({ max_workers: limit, agents_per_project: agents }); }
    catch (error) { setProblem(error instanceof Error ? error.message : String(error)); }
    finally { setSaving(false); }
  };
  return (
    <section className="card card-pad">
      <h2 style={{ fontSize: 20 }}>Parallel agents and projects</h2>
      <p className="muted small">Independent development tasks can run together in isolated workspaces. Appling integrates their changes before checking the complete app. Dependent tasks wait for their prerequisites.</p>
      <label><span className="field-label">Maximum development agents per project</span>
        <select className="input" value={agents} onChange={(event) => setAgents(Number(event.target.value))}>
          {Array.from({ length: 6 }, (_, i) => i + 1).map((n) => <option key={n} value={n}>{n === 1 ? "1 · one task at a time" : `${n} agents`}</option>)}
        </select>
      </label>
      <p className="muted small">This is a limit, not a fixed team size. Small changes may use one agent. More agents can increase model usage and do not guarantee faster work.</p>
      <label><span className="field-label">Maximum active projects</span>
        <select className="input" value={limit} onChange={(event) => setLimit(Number(event.target.value))}>
          {Array.from({ length: 8 }, (_, i) => i + 1).map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
      </label>
      <button className="btn primary" disabled={saving || (limit === value && agents === agentsPerProject)} onClick={() => void save()}>{saving ? "Saving…" : "Save worker limits"}</button>
      <p className="muted small">Lowering the limit lets existing work finish before more starts. Your provider and model choices stay the same.</p>
      <p className="muted small">The development-agent limit applies to separately planned builds. Direct builds use the coding engine’s native agent limits and messaging. Appling keeps requirements, approvals, project memory and independent QA in both modes.</p>
      {problem && <p className="small" role="alert">{problem}</p>}
    </section>
  );
}
