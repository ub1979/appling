// APP IT preview helper — added to every page APP IT's preview serves.
// Inert unless the page sits inside APP IT's preview panel. It lets the owner
// point at a part of the page (🎯 Pick) and reports page errors to the panel.
(() => {
  if (window.parent === window || window.__appitPick) return;
  window.__appitPick = true;
  const post = (msg) => window.parent.postMessage({ source: "appit-preview", ...msg }, "*");

  // Page errors reach the panel, so the owner (and APP IT) can see them.
  addEventListener("error", (e) => post({ type: "error", text: String(e.message || e.error || "Error").slice(0, 300) }));
  addEventListener("unhandledrejection", (e) => post({ type: "error", text: ("Unhandled: " + String(e.reason)).slice(0, 300) }));
  const original = console.error;
  console.error = (...args) => {
    post({ type: "error", text: args.map((a) => (a && a.message) || String(a)).join(" ").slice(0, 300) });
    original.apply(console, args);
  };

  const box = document.createElement("div");
  const tag = document.createElement("div");
  for (const el of [box, tag]) el.setAttribute("data-appit", "");
  Object.assign(box.style, { position: "fixed", zIndex: 2147483646, pointerEvents: "none", display: "none",
    outline: "2px solid #7c5cff", background: "rgba(124,92,255,.12)", borderRadius: "4px", transition: "all .06s" });
  Object.assign(tag.style, { position: "fixed", zIndex: 2147483647, pointerEvents: "none", display: "none",
    font: "600 11px system-ui, sans-serif", color: "#fff", background: "#7c5cff", padding: "3px 7px", borderRadius: "6px" });
  let on = false;
  let current = null;

  const name = (el) => {
    let s = el.tagName.toLowerCase();
    if (el.id) return `${s}#${el.id}`;
    const cls = [...el.classList].filter((c) => !/^(css|sc|jsx|svelte)-|\d{3,}/.test(c)).slice(0, 2);
    return cls.length ? `${s}.${cls.join(".")}` : s;
  };
  const path = (el) => {
    const parts = [];
    for (let n = el; n && n !== document.body && parts.length < 5; n = n.parentElement) {
      let part = name(n);
      if (!n.id && n.parentElement) {
        const same = [...n.parentElement.children].filter((c) => c.tagName === n.tagName);
        if (same.length > 1) part += `:nth-of-type(${same.indexOf(n) + 1})`;
      }
      parts.unshift(part);
      if (n.id) break;
    }
    return parts.join(" > ");
  };
  const near = (el) => {
    const scope = el.closest("section, header, footer, nav, main, article, aside, form, dialog");
    const heading = scope && scope.querySelector("h1, h2, h3, h4, legend, [aria-label]");
    const label = heading && (heading.getAttribute("aria-label") || heading.textContent || "").trim();
    return [scope ? name(scope) : "", label ? `“${label.slice(0, 60)}”` : ""].filter(Boolean).join(" ");
  };
  // The element's own markup without inline animation styles (noise for a reader).
  const clean = (el) => {
    const copy = el.cloneNode(true);
    for (const n of [copy, ...copy.querySelectorAll("[style]")]) n.removeAttribute && n.removeAttribute("style");
    return copy.outerHTML.replace(/\s+/g, " ").slice(0, 200);
  };
  const describe = (el) => {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    const text = (el.innerText || el.getAttribute("alt") || el.getAttribute("aria-label") || el.getAttribute("placeholder") || el.value || "").trim();
    return {
      element: name(el), selector: path(el), text: text.replace(/\s+/g, " ").slice(0, 120), within: near(el),
      page: location.pathname + location.hash, size: `${Math.round(r.width)}×${Math.round(r.height)} px`,
      style: { color: st.color, background: st.backgroundColor, fontSize: st.fontSize, fontWeight: st.fontWeight },
      html: clean(el),
    };
  };
  const show = (el) => {
    const r = el.getBoundingClientRect();
    Object.assign(box.style, { display: "block", left: `${r.left}px`, top: `${r.top}px`, width: `${r.width}px`, height: `${r.height}px` });
    tag.textContent = name(el);
    Object.assign(tag.style, { display: "block", left: `${Math.max(4, r.left)}px`, top: `${r.top > 26 ? r.top - 24 : r.bottom + 4}px` });
  };
  const stop = () => {
    on = false; current = null;
    box.style.display = tag.style.display = "none";
    document.documentElement.style.cursor = "";
  };
  addEventListener("mousemove", (e) => {
    if (!on) return;
    const el = e.target;
    if (!(el instanceof Element) || el.hasAttribute("data-appit")) return;
    current = el; show(el);
  }, true);
  for (const type of ["click", "mousedown", "mouseup", "pointerdown", "submit"]) {
    addEventListener(type, (e) => {
      if (!on) return;
      e.preventDefault(); e.stopPropagation();
      if (type === "click" && current) { post({ type: "picked", element: describe(current) }); stop(); }
    }, true);
  }
  addEventListener("keydown", (e) => { if (on && e.key === "Escape") { stop(); post({ type: "pick-cancelled" }); } }, true);
  addEventListener("message", (e) => {
    if (e.source !== window.parent || !e.data || e.data.source !== "appit-panel") return;
    if (e.data.type === "pick") {
      if (e.data.on) { on = true; document.documentElement.style.cursor = "crosshair"; } else stop();
    }
  });
  const mount = () => { document.body.append(box, tag); post({ type: "ready", page: location.pathname }); };
  if (document.body) mount(); else addEventListener("DOMContentLoaded", mount);
})();
