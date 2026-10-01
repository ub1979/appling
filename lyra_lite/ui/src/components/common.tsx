import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Moon, Sun } from "lucide-react";
import { api, avatarUrl, type Agent, type FolderListing } from "../api";
import { usePrefs } from "../prefs";

export function Brand({ sub, onClick }: { sub: string; onClick?: () => void }) {
  return (
    <button className="brand" onClick={onClick} type="button">
      <span className="brand-mark">L</span>
      <span>
        <span className="brand-name">Lyra Studio</span>
        <br />
        <span className="brand-sub">{sub}</span>
      </span>
    </button>
  );
}

/** A round icon button, like the Studio's; the label shows as a tooltip. */
export function IconButton({
  label,
  onClick,
  children,
  tone = "",
  disabled = false,
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
  tone?: "" | "danger" | "accent";
  disabled?: boolean;
}) {
  return (
    <button type="button" className={`round-btn ${tone}`} onClick={onClick} title={label} aria-label={label} disabled={disabled}>
      {children}
    </button>
  );
}

export function PrefButtons({ onAi }: { onAi?: () => void }) {
  const { theme, setTheme, size, cycleSize } = usePrefs();
  return (
    <>
      <IconButton label={`Text size: ${size}`} onClick={cycleSize}>Aa</IconButton>
      <IconButton label={theme === "dark" ? "Light mode" : "Dark mode"} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
        {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
      </IconButton>
      {onAi && (
        <IconButton label="AI engine and model" onClick={onAi}>
          <span className="ai-mark">AI</span>
        </IconButton>
      )}
    </>
  );
}

export function Avatar({ id, size = 40, className = "" }: { id: string; size?: number; className?: string }) {
  return <img className={`avatar ${className}`} src={avatarUrl(id)} width={size} height={size} alt="" loading="lazy" />;
}

export function AvatarStack({ ids, max = 6 }: { ids: string[]; max?: number }) {
  return (
    <span className="avatar-stack">
      {ids.slice(0, max).map((id) => (
        <Avatar key={id} id={id} size={30} />
      ))}
    </span>
  );
}

export function TeamPicker({
  agents,
  selected,
  recommended = [],
  onToggle,
}: {
  agents: Agent[];
  selected: string[];
  recommended?: string[];
  onToggle: (id: string) => void;
}) {
  return (
    <div className="agent-grid">
      {agents.map((a) => {
        const on = selected.includes(a.id);
        return (
          <button
            key={a.id}
            type="button"
            className={`agent-card ${on ? "on" : ""} ${recommended.includes(a.id) ? "recommended" : ""}`}
            disabled={a.required}
            onClick={() => onToggle(a.id)}
            title={a.required ? "Always on" : on ? "Remove from the team" : "Add to the team"}
          >
            <span className="check">{on ? "✓" : ""}</span>
            <Avatar id={a.id} size={52} />
            <span style={{ minWidth: 0 }}>
              <b>{a.label}</b>
              {a.required && <span className="tag">always on</span>}
              {!a.required && recommended.includes(a.id) && <span className="tag">recommended</span>}
              <p>{a.description}</p>
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function FolderDialog({
  start,
  title,
  pickLabel,
  onPick,
  onClose,
}: {
  start: string;
  title: string;
  pickLabel: string;
  onPick: (path: string) => void;
  onClose: () => void;
}) {
  const [listing, setListing] = useState<FolderListing | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const open = useCallback(async (path?: string) => {
    try {
      setListing(await api.folders(path));
      setProblem(null);
    } catch (e) {
      setProblem(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void open(start || undefined);
  }, [open, start]);

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h2>{title}</h2>
        <div className="muted small">
          <code>{listing?.path ?? "…"}</code>
        </div>
        <div className="folder-list">
          {listing?.parent && (
            <button className="folder-item" onClick={() => void open(listing.parent ?? undefined)}>
              ↖ Up one level
            </button>
          )}
          {listing?.folders.map((f) => (
            <button key={f} className="folder-item" onClick={() => void open(`${listing.path}/${f}`)}>
              📁 {f}
            </button>
          ))}
          {listing && listing.folders.length === 0 && <p className="muted small" style={{ padding: 8 }}>No folders here.</p>}
        </div>
        {problem && <p className="problem small">{problem}</p>}
        <div className="dialog-actions">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={!listing} onClick={() => listing && onPick(listing.path)}>
            {pickLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
