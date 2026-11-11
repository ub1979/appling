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
