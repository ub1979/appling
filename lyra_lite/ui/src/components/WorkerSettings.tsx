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
      <h2 style={{ fontSize: 20 }}>Parallel workers</h2>
      <p className="muted small">Appling chooses how many workers help each task and explains why. This shared limit includes role agents and their workers across open projects. Default: 10; maximum: 15. Independent work can run together; shared changes stay with one lead.</p>
      <label><span className="field-label">Maximum workers</span>
        <select className="input" value={limit} onChange={(event) => setLimit(Number(event.target.value))}>
          {Array.from({ length: 15 }, (_, i) => i + 1).map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
      </label>
      <button className="btn primary" disabled={saving || limit === value} onClick={() => void save()}>Save</button>
      <p className="muted small">Lowering the limit lets existing work finish before more starts. Your provider and model choices stay the same.</p>
    </section>
  );
}
