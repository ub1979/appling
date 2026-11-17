import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ProviderAlerts, retryMessage } from "./ProviderAlerts";
import { applyEvent, emptyLive, type LyraEvent, type ProviderStatus } from "../live";

const status: ProviderStatus = { id: "child", state: "retrying", provider: "custom", model: "test-model", goal: "requirements", reason: "rate_limit", retry_at: 700, attempt: 1, max_attempts: 3 };
describe("provider delays", () => {
  it("explains the wait and offers an immediate way to change AI", () => {
    expect(retryMessage(status, 100)).toContain("10 minutes");
    expect(retryMessage(status, 701)).toContain("next retry is due");
    const html = renderToStaticMarkup(createElement(ProviderAlerts, { statuses: [status], agentName: () => "Requirements", onChangeAi: () => {} }));
    for (const text of ["Requirements", "test-model", "custom", "rate limit", "Stop and change AI"]) expect(html).toContain(text);
  });
  it("keeps failures visible until recovery or an explicit stop", () => {
    const event = { type: "provider_status", ts: 1, ...status } as LyraEvent;
    const waiting = applyEvent(emptyLive(), event);
    expect(waiting.providerStatuses.child.reason).toBe("rate_limit");
    const recovered = applyEvent(waiting, { ...event, state: "recovered" } as LyraEvent);
    expect(recovered.providerStatuses).toEqual({});
    expect(applyEvent(waiting, { type: "stop_requested", ts: 2 }).providerStatuses).toEqual({});
  });
});
