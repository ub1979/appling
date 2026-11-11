import { useEffect, useState } from "react";
import type { ProviderStatus } from "../live";

const REASONS: Record<string, string> = {
  rate_limit: "hit the provider’s rate limit",
  upstream_rate_limit: "hit the model’s rate limit",
  billing: "ran out of provider credits or quota",
  auth: "could not authenticate with the provider",
  auth_permanent: "needs a working provider login",
  timeout: "timed out waiting for the provider",
  overloaded: "is waiting because the provider is overloaded",
  server_error: "received an error from the provider",
  ssl_cert_verification: "could not verify the provider’s connection",
};

export function retryMessage(status: ProviderStatus, now: number): string {
  if (status.state !== "retrying") return "The request has failed. You can change the AI in Settings.";
  const seconds = Math.max(0, Math.ceil((status.retry_at ?? now) - now));
  if (!seconds) return "The next retry is due. Waiting for the provider to respond.";
  const duration = seconds >= 60 ? `${Math.ceil(seconds / 60)} minutes` : `${seconds} seconds`;
  return `Retrying in about ${duration} (attempt ${status.attempt ?? 1}/${status.max_attempts ?? 3}). You can change the AI now.`;
}

interface Props {
  statuses: ProviderStatus[];
  agentName: (goal: string) => string;
  onChangeAi: () => void;
}

export function ProviderAlerts({ statuses, agentName, onChangeAi }: Props) {
  const [now, setNow] = useState(Date.now() / 1000);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return statuses.map((status) => (
    <div className="banner warn" role="alert" key={status.id}>
      <span>
        <b>{status.goal ? agentName(status.goal) : "Appling"} · {status.model} · {status.provider}</b>
        <br />This AI {REASONS[status.reason] ?? "could not complete its request"}.
        <br />{retryMessage(status, now)}
      </span>
      <button className="btn small" onClick={onChangeAi}>Stop and change AI</button>
    </div>
  ));
}
