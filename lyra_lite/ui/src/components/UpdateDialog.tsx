import { useEffect, useRef, useState } from "react";

interface Props {
  name: string;
  revision: number;
  onClose: () => void;
  onStart: (branch: string | null) => Promise<void>;
}

export function UpdateDialog({ name, revision, onClose, onStart }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [accepted, setAccepted] = useState(false);
  const [separate, setSeparate] = useState(true);
  const [branch, setBranch] = useState(`appling/update-${revision}`);
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    dialog.current?.showModal();
  }, []);

  const start = async () => {
    setPending(true);
    setProblem(null);
    try {
      await onStart(separate ? branch.trim() : null);
    } catch (e) {
      setProblem(e instanceof Error ? e.message : String(e));
      setPending(false);
    }
  };

  return (
    <dialog ref={dialog} className="dialog update-dialog" aria-labelledby="update-title"
      onCancel={(e) => { e.preventDefault(); if (!pending) onClose(); }}>
      <h2 id="update-title">{accepted ? `Start version ${revision}` : `Update ${name}?`}</h2>
      {accepted ? (
        <>
          <p className="small">Appling will start a new requirements interview using the existing project and its decisions.</p>
          <label className="small"><input type="checkbox" checked={separate} disabled={pending}
            onChange={(e) => setSeparate(e.target.checked)} /> Create a separate Git branch</label>
          {separate && <p className="muted small">This project folder switches to the new branch and carries over local edits.</p>}
          {separate && (
            <label>
              <span className="field-label">Branch name</span>
              <input className="input" value={branch} disabled={pending} onChange={(e) => setBranch(e.target.value)} />
            </label>
          )}
          {problem && <p className="small" role="alert">{problem}</p>}
          <div className="dialog-actions">
            <button className="btn" disabled={pending} onClick={onClose}>Cancel</button>
            <button className="btn primary" disabled={pending || (separate && !branch.trim())} onClick={() => void start()}>
              {pending ? "Starting…" : "Start requirements"}
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="small">Start a new version or open the project as it is.</p>
          <div className="dialog-actions">
            <button className="btn" onClick={onClose}>Open project</button>
            <button className="btn primary" onClick={() => setAccepted(true)}>Update project</button>
          </div>
        </>
      )}
    </dialog>
  );
}
