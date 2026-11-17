import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AgentModel, PrimaryModel, ConnectionCheck, DiscoveryStatus } from "./Settings";
import { api, type AiSettings, type AgentModelSetting, type ModelOptions } from "../api";

const agent: AgentModelSetting = {
  id: "sw-developer",
  label: "Development",
  default: null,
  selection: { provider: "ollama-local", model: "local-model-b", effort: "high" },
};
const options: ModelOptions = {
  provider: "ollama-local",
  model: "local-model-b",
  providers: [{
    slug: "ollama-local", name: "Ollama", current: true,
    models: ["local-model-a", "local-model-b", "local-model-c"],
  }],
};

function modelMenu(setting: AgentModelSetting, catalog: ModelOptions | null): string {
  const html = renderToStaticMarkup(createElement(AgentModel, {
    agent: setting, options: catalog, onSave: async () => {},
  }));
  return html.match(/<select[^>]*aria-label="Development model"[^>]*>([\s\S]*?)<\/select>/)?.[1] ?? "";
}

describe("agent model dropdown", () => {
  it("includes every provider model even when a specific model is selected", () => {
    const menu = modelMenu(agent, options);
    for (const model of options.providers[0].models) {
      expect(menu).toContain(`value="${model}"`);
    }
    expect(menu).toContain('value="local-model-b" selected=""');
    expect(menu).toContain("Enter a custom model ID");
  });

  it("keeps a saved model visible when it is absent from the provider catalog", () => {
    const menu = modelMenu({
      ...agent, selection: { provider: "ollama-local", model: "private-model" },
    }, options);
    expect(menu).toContain('value="private-model" selected=""');
    for (const model of options.providers[0].models) {
      expect(menu).toContain(`value="${model}"`);
    }
  });

  it("preserves the saved selection while model discovery is loading", () => {
    expect(modelMenu(agent, null)).toContain('value="local-model-b" selected=""');
  });
});

const settings: AiSettings = {
  engine: "ollama-local", hermes: { provider: "ollama-local", model: "local-model-b" },
  hermes_effort: { effort: "", effective: "", overridden: false }, about_me: "", agent_models: [],
  parallel_work: { max_workers: 3, maximum: 8, default: 3, active: 0 }, installed: [],
  connections: { "ollama-local": { engine: "ollama", label: "Ollama" } },
};

describe("primary model controls", () => {
  it("shows discovered models in a visible dropdown and offers a connection test", () => {
    const html = renderToStaticMarkup(createElement(PrimaryModel, {
      settings, options, loading: false, onRefresh: () => {}, onSave: async () => {}, onSaveEffort: async () => {},
    }));
    const menu = html.match(/<select[^>]*aria-label="Appling model"[^>]*>([\s\S]*?)<\/select>/)?.[1] ?? "";
    for (const model of options.providers[0].models) expect(menu).toContain(`value="${model}"`);
    expect(menu).toContain('value="local-model-b" selected=""');
    expect(menu).toContain("Enter a custom model ID");expect(html).toContain("Test connection");
  });
  it("displays catalogue failures instead of silently hiding them", () => {
    const provider = { ...options.providers[0], status: { state: "error", message: "Ollama is not running.", source: "provider" } };
    const html = renderToStaticMarkup(createElement(DiscoveryStatus, { provider }));
    expect(html).toContain('role="status"');expect(html).toContain("Ollama is not running.");
  });
  it("explains testing uses quota without sending project files", () => {
    const html = renderToStaticMarkup(createElement(ConnectionCheck, { provider: "codex", model: "", disabled: true }));
    expect(html).toContain("Test connection");expect(html).toContain("account quota");
    expect(html).toContain("No project files are sent");expect(html).toContain("disabled");
  });
});

describe("connection test request", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("sends the selected provider and model to the authenticated endpoint", async () => {
    vi.stubGlobal("window", { __LYRA_TOKEN__: "test-session" });
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true, message: "Responded", model: "chosen-model", latency_ms: 12 }) });
    vi.stubGlobal("fetch", fetch);
    expect((await api.testConnection("codex", "chosen-model")).ok).toBe(true);
    expect(fetch).toHaveBeenCalledWith("/api/settings/connections/codex/test", expect.objectContaining({
      method: "POST", body: JSON.stringify({ model: "chosen-model" }),
      headers: expect.objectContaining({ "x-lyra-token": "test-session" }),
    }));
  });
});
