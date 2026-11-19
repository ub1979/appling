import { useEffect, useState } from "react";
import { api, type AcceptanceStatus } from "../api";
import { headline, openSetup, rows, setupNeededNow, STATUS_LABEL } from "./acceptance-view";

export function AcceptancePanel({ id, refresh }: { id: string; refresh: number }) {
  const [status, setStatus] = useState<AcceptanceStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const load = () => api.acceptance(id).then(s => { setStatus(s); setError(""); }).catch(e => setError(String(e.message ?? e)));
  useEffect(() => { void load(); }, [id, refresh]);
  if (!status) return error ? <section className="panel"><h3>Acceptance</h3><p className="small muted">{error}</p></section> : null;
  const list = rows(status);
  if (!list.length && !status.prerequisites.length) return null;
  const mark = async (item: string, done: boolean) => {
    setBusy(item);
    try { await api.prerequisite(id, item, done); await load(); }
    catch (e) { setError(String((e as Error).message ?? e)); }
    finally { setBusy(""); }
  };
  const waiting = openSetup(status);
  return (
    <section className="panel" aria-label="Acceptance">
      <h3>Acceptance</h3>
      <p className="small" role="status" style={{ marginTop: 0 }}><b>{headline(status)}</b></p>
      {status.derived && <p className="tiny muted">Criteria are derived one per requirement. Send <code>/criteria</code> to propose
        approved criteria and setup items, including live checks that may wait on you.</p>}
      {status.prerequisites.length > 0 && (
        <details open={setupNeededNow(status)} style={{ marginBottom: 8 }}>
          <summary className="small muted" style={{ cursor: "pointer" }}>
            {setupNeededNow(status) ? `Your turn: ${waiting.length} setup item${waiting.length === 1 ? "" : "s"} needed for the live checks`
              : `Setup you'll provide later (${status.prerequisites.length}) · not needed yet`}
          </summary>
          <ul className="setup-list" style={{ listStyle: "none", padding: 0, margin: "4px 0 0" }}>
            {status.prerequisites.map(p => (
              <li key={p.id} className="small" style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                <input type="checkbox" id={`setup-${p.id}`} checked={p.done} disabled={busy === p.id}
                  onChange={e => void mark(p.id, e.target.checked)} />
                <label htmlFor={`setup-${p.id}`}>{p.description} <span className="tiny muted">({p.kind}, needed at {p.needed_at})</span></label>
              </li>
            ))}
          </ul>
          <p className="tiny muted" style={{ margin: "4px 0 0" }}>Tick an item once it is ready. That lets its live checks run; it never passes them.</p>
        </details>
      )}
      {list.length > 0 && (
        <details open={status.phase === "implementation_verified"}>
          <summary className="small muted" style={{ cursor: "pointer" }}>Criteria ({list.length})</summary>
          <table className="tiny" style={{ width: "100%", borderCollapse: "collapse", marginTop: 6 }}>
            <thead><tr><th align="left">ID</th><th align="left">Status</th><th align="left">Next</th></tr></thead>
            <tbody>
              {list.map(r => (
                <tr key={r.id} title={r.description}>
                  <td>{r.id}{r.live ? " · live" : ""}</td>
                  <td className={`acc-${r.status}`}>{STATUS_LABEL[r.status]}{r.stale ? " (source changed)" : ""}</td>
                  <td>{r.owner ? `${r.owner}: ` : ""}{r.next}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
      {error && <p className="tiny" style={{ color: "var(--danger, #b42318)" }}>{error}</p>}
    </section>
  );
}
