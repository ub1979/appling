import { useEffect, useState } from "react";
import { api } from "../api";
import { blockLine, blocksHeadline, type BlocksStatus } from "./blocks-view";

export function BlocksPanel({ id, refresh }: { id: string; refresh: number }) {
  const [status, setStatus] = useState<BlocksStatus | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () => void api.blocks(id).then(s => alive && setStatus(s)).catch(() => undefined);
    load();
    const timer = window.setInterval(load, 15000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [id, refresh]);
  if (!status?.exists || !status.blocks.length) return null;
  return (
    <section className="panel" aria-label="Blocks">
      <h3>Blocks</h3>
      <p className="small" role="status" style={{ marginTop: 0 }}><b>{blocksHeadline(status)}</b></p>
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {status.blocks.map(b => (
          <li key={b.id} className={`block-row block-${b.status}`} style={{ marginBottom: 8 }} title={b.purpose}>
            <div className="small"><b>{b.name}</b>{b.runtime === "service" ? <span className="tiny muted"> · own process</span> : null}</div>
            <div className="tiny muted">{blockLine(b, status.blocks.some(x => x.status === "building"))}</div>
          </li>
        ))}
      </ul>
      {status.body && <p className="tiny muted" style={{ margin: "6px 0 0" }}>App body: {status.body}</p>}
    </section>
  );
}
