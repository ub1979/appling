import { useCallback, useEffect, useState } from "react";
import QRCode from "qrcode";
import { api, type PhoneAction, type PhoneChannel, type PhoneConnection, type PhoneSettings } from "../api";

interface PhoneChannelCardProps {
  channel: PhoneChannel;
  connection: PhoneConnection;
  busy: boolean;
  onAction: (channel: PhoneChannel, action: PhoneAction) => Promise<boolean>;
}

export function PhoneChannelCard({ channel, connection, busy, onAction }: PhoneChannelCardProps) {
  const [botToken, setBotToken] = useState("");
  const [tokenEnv, setTokenEnv] = useState(connection.token_env || "TELEGRAM_BOT_TOKEN");
  const [qrImage, setQrImage] = useState("");
  const telegram = channel === "telegram";
  const label = telegram ? "Telegram" : "WhatsApp";
  useEffect(() => setTokenEnv(connection.token_env || "TELEGRAM_BOT_TOKEN"), [connection.token_env]);
  useEffect(() => {
    let current = true;
    setQrImage("");
    if (connection.qr) {
      void QRCode.toDataURL(connection.qr, { width: 256, margin: 2 })
        .then((image) => { if (current) setQrImage(image); })
        .catch(() => { /* A fresh QR arrives on the next status refresh. */ });
    }
    return () => { current = false; };
  }, [connection.qr]);
  const configure = async () => {
    const action: PhoneAction = { action: "configure", enabled: true, token_env: tokenEnv.trim() || "TELEGRAM_BOT_TOKEN" };
    if (botToken.trim()) action.bot_token = botToken.trim();
    const succeeded = await onAction(channel, action);
    if (succeeded) setBotToken("");
  };
  return <section className="card card-pad">
    <h2 style={{ fontSize: 20 }}>{label} phone connection</h2>
    <p className="small" role="status">{connection.paired ? connection.connected ? "✓ Phone paired" : "Phone paired · offline" : connection.connected ? "Connected · waiting for pairing" : connection.enabled ? "Connecting" : "Not connected"} · {connection.message}</p>
    {telegram ? <>
      <p className="muted small">Create a private bot with <a href="https://t.me/BotFather" target="_blank" rel="noreferrer">@BotFather</a>, save its token here, then pair your phone. Use a bot dedicated to Appling.</p>
      <label><span className="field-label">Telegram bot token</span>
        <input className="input" type="password" autoComplete="off" value={botToken} onChange={(event) => setBotToken(event.target.value)} placeholder={connection.configured ? "Saved · leave blank to keep it" : "Paste the token from BotFather"} />
      </label>
      <p className="tiny muted">The token stays in Appling’s private credential file. It is never added to project chat or memory.</p>
      <details><summary className="small">Use an environment variable instead</summary>
        <label><span className="field-label">Bot token environment variable</span><input className="input" value={tokenEnv} onChange={(event) => setTokenEnv(event.target.value)} /></label>
        <p className="tiny muted">The variable must be available to the process that starts Appling.</p>
      </details>
      <button className="btn small" disabled={busy} onClick={() => void configure()}>Save Telegram settings</button>
    </> : <>
      <p className="muted small">Connect through WhatsApp’s Linked devices using Baileys. This is an unofficial WhatsApp connection and may require reconnecting after WhatsApp changes.</p>
      <details><summary className="small">First-time setup</summary><p className="small">Install the local bridge once from the Appling folder:</p><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}><code>cd bridge/whatsapp &amp;&amp; npm install</code></pre></details>
    </>}
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
      <button className="btn primary small" disabled={busy || (telegram && !connection.configured)} onClick={() => void onAction(channel, { action: "pair" })}>{connection.paired ? telegram ? "Pair a different account" : "Refresh owner pairing" : "Pair phone"}</button>
      <button className="btn small" disabled={busy || !connection.paired} onClick={() => void onAction(channel, { action: "test" })}>Send test message</button>
      <button className="btn ghost small" disabled={busy || (!connection.enabled && !connection.configured)} onClick={() => void onAction(channel, { action: "disconnect" })}>Disconnect</button>
    </div>
    {connection.pairing_code && !connection.paired && <div style={{ marginTop: 14 }}>
      {telegram ? <>
        <p className="small">Open your bot and send <code>/pair {connection.pairing_code}</code> from your private Telegram chat.</p>
        {connection.pairing_url?.startsWith("https://t.me/") && <a className="btn small" href={connection.pairing_url} target="_blank" rel="noreferrer">Open Telegram to pair</a>}
      </> : <>
        {connection.connected ? <p className="small">WhatsApp is already linked. Confirm your account below.</p> : <>
          <p className="small">In WhatsApp, open <b>Settings → Linked devices → Link a device</b> and scan this QR code.</p>
          {qrImage ? <img src={qrImage} alt="WhatsApp device pairing QR code" width={256} height={256} style={{ maxWidth: "100%", height: "auto", borderRadius: 12 }} /> : <p className="small muted">Waiting for the QR code…</p>}
        </>}
        <p className="small">Then open <b>Message yourself</b> and send <code>/pair {connection.pairing_code}</code> to authorize your account.</p>
      </>}
      <p className="tiny muted">This pairing code expires after 10 minutes. Keep it private.</p>
    </div>}
  </section>;
}

export function PhoneConnections() {
  const [settings, setSettings] = useState<PhoneSettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const [loadProblem, setLoadProblem] = useState("");
  const load = useCallback(async () => {
    try { setSettings(await api.phoneSettings()); setLoadProblem(""); }
    catch (error) { setLoadProblem(error instanceof Error ? error.message : String(error)); }
  }, []);
  useEffect(() => {
    void load();
    const timer = window.setInterval(() => { void load(); }, 3000);
    return () => window.clearInterval(timer);
  }, [load]);
  const act = async (channel: PhoneChannel, action: PhoneAction): Promise<boolean> => {
    setBusy(true); setProblem("");
    try { setSettings(await api.phoneAction(channel, action)); return true; }
    catch (error) { setProblem(error instanceof Error ? error.message : String(error)); return false; }
    finally { setBusy(false); }
  };
  return <>
    <section className="card card-pad">
      <h2 style={{ fontSize: 20 }}>Questions and approvals on your phone</h2>
      <p className="muted small">Choose Telegram, WhatsApp, or both. Appling sends pending questions and review requests to your paired account. Replies appear in the project conversation. Each answer is tied to its original request; outdated approvals are rejected.</p>
      <p className="muted small">Your computer must stay awake, online and running Appling. Prototype previews still need a secure phone-accessible link; pairing does not expose your local app.</p>
      <button className="btn ghost small" disabled={busy} onClick={() => void load()}>Refresh phone status</button>
      {(problem || loadProblem) && <p className="small" role="alert">{problem || loadProblem}</p>}
      {!settings && !problem && !loadProblem && <p className="small muted">Loading phone connections…</p>}
    </section>
    {settings && (["telegram", "whatsapp"] as const).map((channel) => <PhoneChannelCard key={channel} channel={channel} connection={settings[channel]} busy={busy} onAction={act} />)}
  </>;
}
