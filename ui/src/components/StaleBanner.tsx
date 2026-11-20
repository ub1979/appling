import { useEffect, useState } from "react";
import { STALE_EVENT, STALE_MESSAGE } from "../api";

export function StaleNotice({ onReload }: { onReload: () => void }) {
  return (
    <div className="banner bad" role="alert" style={{ position: "sticky", top: 0, zIndex: 50 }}>
      <span>{STALE_MESSAGE}</span>
      <button className="btn primary small" onClick={onReload}>Reload</button>
    </div>
  );
}

/** Shown on every page once the server refuses this tab's access key. */
export function StaleBanner() {
  const [stale, setStale] = useState(false);
  useEffect(() => {
    const mark = () => setStale(true);
    window.addEventListener(STALE_EVENT, mark);
    return () => window.removeEventListener(STALE_EVENT, mark);
  }, []);
  return stale ? <StaleNotice onReload={() => window.location.reload()} /> : null;
}
