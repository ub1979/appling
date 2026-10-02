import { useEffect, useRef, useState } from "react";
import QRCode from "qrcode";
import { Crosshair, ExternalLink, Laptop, RotateCw, Smartphone, X } from "lucide-react";
import type { AppPreview } from "../api";
import { IconButton } from "./common";

/** What the owner picked in the preview, described for APP IT. */
export interface PickedElement {
  element: string;
  selector: string;
  text: string;
  within: string;
  page: string;
  size: string;
  style: { color: string; background: string; fontSize: string; fontWeight: string };
  html: string;
}

export function pickNote(p: PickedElement): string {
  return [
    "Change this part of the app (picked in the preview):",
    `- element: ${p.element}${p.text ? ` “${p.text}”` : ""}`,
    p.within ? `- inside: ${p.within}` : "",
    `- page: ${p.page} · selector: ${p.selector}`,
    `- looks: ${p.style.fontSize} ${p.style.fontWeight}, text ${p.style.color} on ${p.style.background}, ${p.size}`,
    `- html: ${p.html}`,
  ].filter(Boolean).join("\n");
}

export function pickLabel(p: PickedElement): string {
  return `${p.element}${p.text ? ` “${p.text.slice(0, 32)}${p.text.length > 32 ? "…" : ""}”` : ""}`;
}

interface Props {
  preview: AppPreview;
  onClose: () => void;
  onPicked: (p: PickedElement) => void;
}

export function PreviewPanel({ preview, onClose, onPicked }: Props) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [device, setDevice] = useState<"computer" | "phone">("computer");
  const [picking, setPicking] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [showErrors, setShowErrors] = useState(false);
  const [qr, setQr] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const origin = preview.kind === "web" ? new URL(preview.url).origin : "";

  useEffect(() => {
    if (preview.kind !== "expo") return;
    void QRCode.toDataURL(preview.url, { margin: 1, width: 240, color: { dark: "#15152a", light: "#ffffff" } }).then(setQr);
  }, [preview]);

  // Messages from APP IT's helper inside the previewed page.
  useEffect(() => {
    if (preview.kind !== "web") return;
    const onMessage = (e: MessageEvent) => {
      if (e.origin !== origin || !e.data || e.data.source !== "appit-preview") return;
      if (e.data.type === "picked") { setPicking(false); onPicked(e.data.element as PickedElement); }
      if (e.data.type === "pick-cancelled") setPicking(false);
      if (e.data.type === "error") setErrors((all) => [...all.slice(-19), String(e.data.text)]);
      if (e.data.type === "ready") setPicking(false);
    };
    addEventListener("message", onMessage);
    return () => removeEventListener("message", onMessage);
  }, [preview, origin, onPicked]);

  const togglePick = () => {
    const on = !picking;
    setPicking(on);
    frame.current?.contentWindow?.postMessage({ source: "appit-panel", type: "pick", on }, origin);
  };
  const reload = () => { setErrors([]); setPicking(false); setNonce((n) => n + 1); };
  const tabUrl = preview.kind === "web" ? preview.url : null;

  return (
    <aside className="preview-panel" aria-label="App preview">
      <header className="preview-bar">
        <b>{preview.kind === "expo" ? "Phone preview" : "Preview"}</b>
        {preview.kind === "web" && (
          <>
            <div className="seg" role="group" aria-label="Screen size">
              <button type="button" className={device === "computer" ? "on" : ""} onClick={() => setDevice("computer")} title="Computer size"><Laptop size={15} /></button>
              <button type="button" className={device === "phone" ? "on" : ""} onClick={() => setDevice("phone")} title="Phone size"><Smartphone size={15} /></button>
            </div>
            <button type="button" className={`btn small pick ${picking ? "on" : ""}`} onClick={togglePick}
              title="Point at a part of the app, then say what to change">
              <Crosshair size={14} /> {picking ? "Click a part… (Esc)" : "Pick"}
            </button>
          </>
        )}
        <span style={{ flex: 1 }} />
        {preview.kind === "web" && <IconButton label="Reload" onClick={reload}><RotateCw size={15} /></IconButton>}
        {tabUrl && <IconButton label="Open in a new tab" onClick={() => window.open(tabUrl, "_blank")}><ExternalLink size={15} /></IconButton>}
        <IconButton label="Close preview" onClick={onClose}><X size={15} /></IconButton>
      </header>

      {preview.kind === "web" ? (
        <div className={`preview-stage ${device}`}>
          <iframe key={nonce} ref={frame} src={preview.url} title="Your app" className="preview-frame" />
        </div>
      ) : (
        <div className="phone-qr">
          {qr ? <img src={qr} alt={`QR code for ${preview.url}`} width={240} height={240} /> : <div className="qr-wait">Starting…</div>}
          <ol>
            <li>Install <b>Expo Go</b> on your phone (App Store or Google Play).</li>
            <li>Join the <b>same Wi-Fi</b> as this computer.</li>
            <li>iPhone: scan with the Camera. Android: scan inside Expo Go.</li>
          </ol>
          <p className="muted small">Your app opens on the phone and updates by itself whenever APP IT changes it.</p>
          <code>{preview.url}</code>
        </div>
      )}

      {errors.length > 0 && (
        <footer className="preview-errors">
          <button type="button" onClick={() => setShowErrors((s) => !s)}>
            ⚠ {errors.length} error{errors.length > 1 ? "s" : ""} in the app {showErrors ? "▾" : "▸"}
          </button>
          {showErrors && <ul>{errors.map((e, i) => <li key={i}>{e}</li>)}</ul>}
        </footer>
      )}
    </aside>
  );
}
