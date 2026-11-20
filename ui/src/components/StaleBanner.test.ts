import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, STALE_EVENT, STALE_MESSAGE } from "../api";
import { StaleNotice } from "./StaleBanner";

describe("a tab left open across an Appling restart", () => {
  afterEach(() => { vi.unstubAllGlobals(); });
  it("announces itself as stale instead of silently ignoring clicks", async () => {
    const target = new EventTarget();
    const seen: string[] = [];
    target.addEventListener(STALE_EVENT, (e) => seen.push(e.type));
    vi.stubGlobal("window", Object.assign(target, { __LYRA_TOKEN__: "old-key" }));
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "Unauthorized" }), { status: 401 })));
    await expect(api.answer("p1", "item1", "Approve requirements")).rejects.toThrow(STALE_MESSAGE);
    expect(seen).toEqual([STALE_EVENT]);
  });
  it("tells the owner to reload and that nothing was sent", () => {
    const html = renderToStaticMarkup(createElement(StaleNotice, { onReload: () => {} }));
    for (const text of ["restarted", "Reload", "Nothing you clicked here was sent"]) expect(html).toContain(text);
  });
});
