---
name: web-cinematic
description: Build premium scroll-driven, parallax websites.
---

# Web Cinematic Skill

Build a website that feels hand-crafted: layered depth parallax, pinned scroll
stories, smooth scrolling and a few deliberate motion moments. It produces a
static site that opens anywhere (no server). It does not do back-end work,
log-ins or databases — hand those to `sw-developer` with `sw-architect`.

## When to Use

- The project kind is **Website**, or the owner asks for a landing page,
  portfolio, product page or "a site like Apple / Awwwards / Scrolltide".
- A template was chosen at set-up: its `template_spec` (in the setup message
  and `requirements.md`) is the starting design, and its live demo — copied
  to `.lyra/kit/reference/index.html` — is the approved look and motion.
  Build that, with the changes the owner approved.

## Prerequisites

- Approved `requirements.md` (with the build profile and any template).
- Node 20+ and npm (check with `node -v`).
- Images decided at requirements time (see "Assets" below).
- The `ultimate-builder:ui-designer` direction when the team has one.

## How to Run

Work in the project folder. Scaffold once:
`npm create vite@latest site -- --template vanilla-ts` (or React + TS when
the spec uses React Three Fiber), then `npm i gsap lenis` (+ `three` /
`@react-three/fiber` only if the spec has a 3D moment). Put the app at the
project root or build it to `dist/` so APP IT's **Open app** button shows it.
Run `npm run build` after every section and open the built page.

## Quick Reference

| Part | Choice |
|---|---|
| Build | Vite + TypeScript, static output (`dist/`) |
| Motion | GSAP + ScrollTrigger; Lenis smooth scroll |
| 3D | three / React Three Fiber, only where the spec says |
| Fonts | One expressive display face + one clean sans (Google Fonts) |
| Easing | `power3` / `expo`; never linear; 0.8–1.4 s transitions |
| Budget | ≤ 2 ambient animations on screen; one hero idea per section |

Section patterns: layered parallax hero (layers at 0.2 / 0.5 / 0.8 / 1.1
speed + mouse tilt on desktop), pinned story (pin ~300vh, canvas image
sequence or scene scrubbed by scroll, 3 text beats), horizontal gallery
(vertical scroll drives a horizontal track), word-by-word text reveal
(15% → 100% opacity), 3D moment (camera tied to scroll), CTA with an
oversized wordmark and a magnetic button.

## Procedure

1. **Plan first.** Read the spec, requirements and the reference demo (when
   there is one). For each section, name the reference effect it copies and
   how (the demo is our own code: reuse its GSAP/canvas/three.js techniques
   directly). Write the section plan to `.sdlc/site-plan.md` and report it
   before building. Build every section the spec has; add SEO, analytics
   hooks and an accessibility audit only when the site is going public and
   requirements ask.
2. **Assets.** Use what requirements decided, in this order of preference:
   the owner's own images (`assets/` or what they sent); free stock photos
   (only with a configured key, credit the photographer); AI images via the
   `image_generate` tool when image generation is switched on (on the Codex
   plan: provider `openai-codex`) — generate each parallax layer as its own
   transparent PNG; otherwise tasteful placeholders (gradients, SVG shapes)
   plus a list in the report of exactly which images to provide. Never ship
   hot-linked images or unlicensed stock.
3. **Build one section at a time.** Scaffold, then section 1; build, run the
   site check (below), look at its sheets, commit; then the next. Never
   one-shot the whole site.
4. **Performance and access.** Animate only `transform` and `opacity`;
   `will-change` sparingly; lazy-load media; dispose 3D scenes off-screen;
   respect `prefers-reduced-motion` with a static version; on phones,
   simplify parallax and turn off mouse tilt. Target Lighthouse
   performance ≥ 85.
5. **Taste pass.** Load `ultimate-builder:color-and-ux` (run its palette
   check on the site's colours), `design-taste-frontend` (and `frontend-design` when present)
   and remove anything that looks AI-made: generic gradients, centred
   everything, stock icon rows, purple-blue defaults.
6. **Judge pass.** Critique the site as a senior Awwwards judge, list the top
   five issues, fix them, rebuild.
7. **Finish.** `npm run build` clean, commit, refresh the Project Brain, and
   report what was built, the images still needed, and how to open it.

## Photo-real sites (footage, layers, AI pictures)

Templates marked photo-real get their look from real footage and layered
photos, not code-drawn art. In an APP IT project three commands help (they run
with APP IT's own Python; files the owner attaches are in `assets/uploads/`):

| Command | Use |
|---|---|
| `.lyra/kit/frames clip.mp4 public/frames --count 120` | Video → numbered WebP frames + `frames.json` for a scroll-scrubbed canvas |
| `.lyra/kit/cutout in.png out.webp --bg white\|black\|green [--from top]` | Cut a subject off a plain background for a parallax layer |
| `.lyra/kit/imagine "prompt" --out assets/x.png [--ref first.png]` | AI picture on the owner's ChatGPT plan — only after they said yes |

- **Frame player:** preload all frames, draw the current one on a canvas with
  cover-fit, blend toward the next; drive it from ScrollTrigger progress. With
  only 2–5 stills of one shot, wipe softly between them instead (the
  Grand Reveal demo shows both modes).
- **Layer recipes for AI pictures:** make each layer separately. Glowing
  subjects (planets, fire, light) on pure black and blend with
  `mix-blend-mode: screen`; landscapes with a pure black sky, cut `--from top`;
  dark foregrounds on pure white; light subjects (people, white products) on
  chroma green. Keep camera and light consistent: make the first picture, then
  `--ref` it for the rest ("same room, same camera, sheet removed").
- **Honesty:** AI pictures never stand in for a real product, place or person
  the owner sells; tell the owner which pictures are AI-made and list them in
  the report.
- Budget: hero frames ≤ 8 MB, each layer ≤ 400 KB WebP; lazy-load the rest.

## Site check (developers and QA)

`scripts/site-check.mjs` opens the build in the installed Chrome at desktop
and phone size, scrolls it like a visitor, and lists console errors, failed
requests, sideways overflow and text that never becomes readable. It writes
screenshots and one contact sheet per size; with `--compare` each row shows
the build next to the reference demo at the same scroll point. In an APP IT
project it is copied to `.lyra/kit/site-check.mjs`:

```
node .lyra/kit/site-check.mjs dist --compare .lyra/kit/reference/index.html
```

Exit 0 = nothing automatic found, 1 = problems listed, 3 = BLOCKED (no
browser). Automatic checks cannot judge taste: open every sheet it names.

## Pitfalls

- Parallax without real layers looks cheap: separate background,
  midground, foreground and subject, or use procedural layers.
- ScrollTrigger + Lenis: drive ScrollTrigger from Lenis
  (`lenis.on('scroll', ScrollTrigger.update)` and GSAP's ticker), or pins jump.
- Pinned sections need `ScrollTrigger.refresh()` after images load.
- Do not stack many simultaneous animations; motion should guide the eye.
- Mobile Safari: avoid `100vh` jumps (use `svh`), keep pins short.

## Verification

- `npm run build` succeeds and the site check reports no problems; every
  contact sheet was opened and each section matches the reference effect.
- Scrolling top to bottom is smooth; each section's motion triggers once and
  in order; reduced-motion shows a static, readable page.
- Narrow (390 px) and desktop widths both work without horizontal scroll.
- The report lists every placeholder image the owner still needs to supply.
