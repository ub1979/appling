import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, type PhoneConnection } from "../api";
import { PhoneChannelCard } from "./PhoneConnections";
import { WorkerSettings } from "./WorkerSettings";

const disconnected: PhoneConnection = { enabled: false, configured: false, connected: false, paired: false, message: "Not configured." };

describe("phone connection setup", () => {
  it("keeps the Telegram credential in a password field and explains explicit pairing", () => {
    const html = renderToStaticMarkup(createElement(PhoneChannelCard, {
      channel: "telegram", connection: disconnected, busy: false, onAction: async () => true,
    }));
    expect(html).toContain('type="password"'); expect(html).toContain('autoComplete="off"');
    expect(html).toContain("BotFather"); expect(html).toContain("project chat or memory");
    expect(html).toMatch(/disabled=""[^>]*>Pair phone/);
    expect(html).toMatch(/disabled=""[^>]*>Send test message/);
  });
  it("displays the temporary Telegram code without linking an unexpected origin", () => {
    const html = renderToStaticMarkup(createElement(PhoneChannelCard, {
      channel: "telegram", connection: { ...disconnected, configured: true, pairing_code: "TEMP123", pairing_url: "https://unexpected.example/" },
      busy: false, onAction: async () => true,
    }));
    expect(html).toContain("/pair TEMP123"); expect(html).toContain("expires after 10 minutes");
    expect(html).not.toContain("unexpected.example");
  });
  it("explains WhatsApp linked-device and owner pairing without needing a bot token", () => {
    const html = renderToStaticMarkup(createElement(PhoneChannelCard, {
      channel: "whatsapp", connection: { ...disconnected, pairing_code: "OWNER123" }, busy: false, onAction: async () => true,
    }));
    expect(html).toContain("Linked devices"); expect(html).toContain("Message yourself");
    expect(html).toContain("/pair OWNER123"); expect(html).toContain("unofficial");
    expect(html).not.toContain('type="password"');
  });
  it("allows owner pairing on an already linked WhatsApp account without waiting for another QR", () => {
    const html = renderToStaticMarkup(createElement(PhoneChannelCard, {
      channel: "whatsapp", connection: { ...disconnected, connected: true, pairing_code: "OWNER123" }, busy: false, onAction: async () => true,
    }));
    expect(html).toContain("WhatsApp is already linked");
    expect(html).toContain("/pair OWNER123"); expect(html).not.toContain("Waiting for the QR code");
  });
});

describe("phone settings requests", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("uses local authentication and exact channel/action for owner pairing", async () => {
    vi.stubGlobal("window", { __LYRA_TOKEN__: "studio-session" });
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ telegram: disconnected, whatsapp: disconnected }) });
    vi.stubGlobal("fetch", fetch);
    await api.phoneSettings();
    await api.phoneAction("whatsapp", { action: "pair" });
    expect(fetch).toHaveBeenCalledWith("/api/settings/phone", expect.objectContaining({ method: "GET", headers: expect.objectContaining({ "x-lyra-token": "studio-session" }) }));
    expect(fetch).toHaveBeenCalledWith("/api/settings/phone/whatsapp", expect.objectContaining({ method: "POST", body: JSON.stringify({ action: "pair" }), headers: expect.objectContaining({ "x-lyra-token": "studio-session" }) }));
  });
});

describe("worker limits", () => {
  it("distinguishes agents per project from simultaneous projects", () => {
    const html = renderToStaticMarkup(createElement(WorkerSettings, { value: 2, agentsPerProject: 4, onSave: async () => {} }));
    expect(html).toContain("Maximum development agents per project"); expect(html).toContain("Maximum active projects");
    expect(html).toContain('value="4" selected=""'); expect(html).toContain('value="2" selected=""');
    expect(html).toContain("isolated workspaces"); expect(html).toContain("native agent limits and messaging");
    expect(html).toContain("one task at a time");
  });
});
