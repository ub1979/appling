---
name: website-builder
description: Build professional product and company websites.
---

# Website Builder Skill

Build a website a real company would ship: an AI product, a software / SaaS
product, a landing page for one offer, a new company's site, or a technical
/ developer site. It decides the page structure, the words, the look and the
pictures, then builds a fast static site and checks it in a real browser.
Scroll films and parallax stories are an overlay (`web-cinematic`); back-end
work, log-ins and databases go to `sw-developer` with `sw-architect`.

## When to Use

- The project kind is **Website** (this is its kind skill).
- The owner asks for a landing page, product page, homepage, company site,
  pricing page, docs or developer site, or "make my site look professional".
- A website template was chosen: its `template_spec` and the live demo in
  `.sdlc/template/reference/index.html` are the approved starting design.

## Prerequisites

- Approved `requirements.md` (build profile, template, brand, pages).
- `design-brief.md` from `ui-designer` when the team has one.
- Node 20+ and npm (`node -v`).
- The bundled `web-cinematic/scripts/site-check.mjs` checker.
- Optional authorized image generation, when the design needs generated assets.

## How to Run

Resolve `<skills-directory>` to the absolute Skills directory supplied in the
engine briefing before executing example commands. No project-kit installation
is required; use the bundled scripts in place.

Work from the project folder:

```
npm create vite@latest . -- --template vanilla-ts   # React + TS only if the site needs it
npm i                                               # + gsap / lenis only when motion calls for it
npm run build                                       # after every section
node <skills-directory>/web-cinematic/scripts/site-check.mjs dist --compare .sdlc/template/reference/index.html
```

Drop `--compare` when there is no template. The site builds to `dist/` so
Appling's **Open app** shows it.

## Quick Reference

| Site type | Blueprint (read before planning) |
|---|---|
| AI product | `references/site-blueprints.md` → AI product |
| Software / SaaS product | `references/site-blueprints.md` → Software product |
| Landing page (one offer) | `references/site-blueprints.md` → Landing page |
| New company | `references/site-blueprints.md` → New company |
| Technical / developer | `references/site-blueprints.md` → Developer site |

| Part | Default |
|---|---|
| Build | Vite + TypeScript, static `dist/`, no server |
| Type | One display face with character + one text face; never Inter/Roboto/Arial as the display face |
| Colour | Tokens as CSS custom properties; one dominant colour, one sharp accent; `palette.py check` passes |
| Layout | 12-column grid, max text width ~70 characters, 8 px spacing scale |
| Motion | One orchestrated page-load reveal + scroll reveals; `transform`/`opacity` only |
| Speed | LCP ≤ 2.5 s, CLS ≤ 0.1, INP ≤ 200 ms; hero image ≤ 250 KB |
| Pictures | Owner's real product screens first; AI pictures only with a yes |

## Procedure

Copy this checklist into the plan and tick it as you go:

```
- [ ] 1 Site type and blueprint chosen
- [ ] 2 Message: headline, proof, call to action written
- [ ] 3 Direction: tokens, type, references
- [ ] 4 Pictures listed (real / AI / placeholder)
- [ ] 5 Sections built one at a time, each checked
- [ ] 6 Quality checklist passed
- [ ] 7 Judge pass done, fixes rebuilt
- [ ] 8 Report written
```

1. **Pick the site type** from requirements and read only its blueprint in
   `references/site-blueprints.md`. Write `.sdlc/site-plan.md`: each section,
   the job it does for the visitor, and its effect. With a template, each
   section names the demo technique it reuses.
2. **Write the message before the layout.** Following
   `references/copy-and-proof.md`: one headline that says what it is and who
   it is for, a one-line subhead, one primary call to action used site-wide,
   and the proof the owner can actually back up. Missing facts become
   clearly marked placeholders — never invented customers, logos, numbers
   or quotes.
3. **Set the direction.** Use `design-brief.md` when it exists. Otherwise
   load `skills/design-reference/SKILL.md` (one site the owner likes,
   opened in the browser), `skills/frontend-design/SKILL.md` and
   `skills/taste-skill/SKILL.md` for the anti-generic rules,
   and `skills/color-and-ux/SKILL.md` for palette and
   tokens. Commit to one named aesthetic (e.g. "calm editorial", "terminal
   precision", "warm hardware") and write its tokens before any section.
4. **Plan the pictures** with `references/visual-assets.md`: real product
   screens framed in browser or phone chrome, the owner's photos, AI
   pictures through an available image-generation tool (only after the owner agreed; only through an available authorized tool), or designed placeholders. Record every AI picture in
   `assets/ASSETS.md` (prompt, file, where used).
5. **Build coherent owned sections** with focused checks and native tools.
   Independent assigned sections can run concurrently. After integration, build
   the combined site, run the site check and inspect its contact sheets. Leave
   snapshots and commits to the host; do not force a build/commit per section.
   For parallax, pinned scroll stories, frame-scrubbed video or 3D, load
   `skills/web-cinematic/SKILL.md` for that section.
6. **Run the quality checklist** in `references/quality-checklist.md`
   (speed, theme and contrast, responsive, accessibility, SEO and sharing,
   forms). Fix every failed line; re-run.
7. **Judge pass.** Look at the desktop and phone sheets as a senior agency
   design director would: list the five weakest things (hierarchy, spacing
   rhythm, generic look, weak proof, unclear call to action), fix them,
   rebuild, re-check.
8. **Report**: what was built, how to open it, which pictures are AI-made,
   which placeholders the owner must still fill, and the checklist results.

## Pitfalls

- A professional site is mostly restraint: generous spacing, a strict type
  scale and one accent beat any number of effects.
- Feature lists without outcomes read as filler; lead each feature with the
  result for the visitor, then the mechanism.
- Fake social proof (made-up logos, stars, "trusted by 10,000 teams") is
  never allowed, even as filler. Use a marked placeholder instead.
- AI hero art that pretends to be the product. Show the real interface; use
  AI pictures for mood, texture and illustration only.
- Dark mode added as an afterthought fails contrast. Define both themes as
  tokens up front, or ship one theme well.
- Web fonts: at most two families, `font-display: swap`, preload the hero
  face only.
- Huge unoptimised PNGs: convert to WebP/AVIF, give every image width and
  height, lazy-load below the fold.

## Verification

- `npm run build` is clean; the site check exits 0 and every contact sheet
  it names was opened (exit 3 = no browser = BLOCKED, never a pass).
- Every line of `references/quality-checklist.md` is ticked or reported as
  a known gap.
- 390 px and 1440 px widths: no sideways scroll, nothing cut off, the call
  to action visible without hunting.
- No invented proof anywhere; every AI picture is listed in `assets/ASSETS.md`.
