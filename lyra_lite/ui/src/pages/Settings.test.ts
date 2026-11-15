import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AgentModel } from "./Settings";
import type { AgentModelSetting, ModelOptions } from "../api";

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

import { WorkerSettings } from "./Settings";
import type { AiSettings } from "../api";

describe("parallel worker settings", () => {
  it("shows the saved cap and distinguishes experimental capacity", () => {
    const settings: AiSettings = {
      engine: "codex", codex: { provider: "codex", model: "example-model" },
      codex_effort: { effort: "", effective: "medium", overridden: false },
      about_me: "", agent_models: [], parallel_work: { active: 3, limit: 12, peak: 8 },
    };
    const html = renderToStaticMarkup(createElement(WorkerSettings, { settings, onSave: async () => {} }));
    expect(html).toContain('value="12" selected=""');
    expect(html).toContain("12 — experimental");
    expect(html).toContain("3 workers active when loaded");
    expect(html).toContain("includes role leads and helpers across all projects");
  });
});
