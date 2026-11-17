import { useEffect, useState } from "react";

interface WorkerSettingsProps {
  value: number;
  onSave: (limit: number) => Promise<void>;
}

export function WorkerSettings({ value, onSave }: WorkerSettingsProps) {
  const [limit, setLimit] = useState(value);
  const [saving, setSaving] = useState(false);
  useEffect(() => setLimit(value), [value]);
  const save = async () => {
    setSaving(true);
    try { await onSave(limit); } finally { setSaving(false); }
  };
  return (
    <section className="card card-pad">
      <h2 style={{ fontSize: 20 }}>Concurrent projects</h2>
      <p className="muted small">Each project has one controlled task at a time. Independent projects can run together. Default: 3; maximum: 8.</p>
      <label><span className="field-label">Maximum active projects</span>
        <select className="input" value={limit} onChange={(event) => setLimit(Number(event.target.value))}>
          {Array.from({ length: 8 }, (_, i) => i + 1).map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
      </label>
      <button className="btn primary" disabled={saving || limit === value} onClick={() => void save()}>Save</button>
      <p className="muted small">Lowering the limit lets existing work finish before more starts. Your provider and model choices stay the same.</p>
    </section>
  );
}
