---
name: deck-builder
description: Design and build clear, persuasive slide decks.
---

# Deck Builder Skill

Make a presentation people remember: a story with one point per slide,
headlines that state the point, real numbers drawn as honest charts, and a
look that fits the brand. With a deck template the output is an HTML deck
on reveal.js (present from a browser, export to PDF); without one it is a
PowerPoint (`.pptx`) built with the `powerpoint` skill, unless the owner
prefers HTML. Story and design rules are the same for both. It does not
invent data, quotes or results.

## When to Use

- The project kind is **Slides** (this is its kind skill). A chosen
  template's live demo is in `.lyra/kit/reference/index.html`.
- The owner asks for a pitch deck, sales or product demo deck, company
  intro, report, keynote, lesson or workshop slides.
- An existing deck needs a redesign or a story rewrite.

## Prerequisites

- Approved `requirements.md`: audience, goal, length, format (HTML / PDF /
  PPTX), brand, the real numbers and pictures.
- Node 20+ (`node -v`) for the deck check.
- `.lyra/kit/imagine` for AI pictures (only after the owner agreed).
- For `.pptx`: `skill_view(name="powerpoint")`.

## How to Run

```
node .lyra/kit/deck-check.mjs deck --pdf deck/deck.pdf
```

(Outside an Appling project: `scripts/deck-check.mjs` in this skill.)
`deck/` holds `index.html` (one file, reveal.js 5 from cdnjs, 1280 × 720,
`hash: true`) and `assets/`. The check opens it in Chrome, shows every slide
with all build-up steps, saves screenshots plus `sheet.png` under
`.lyra/qa/deck-check/`, and lists content running off a slide, text under
16 px and slides over 45 words. `--pdf` exports one page per slide. Exit
0 = clean, 1 = problems listed, 3 = BLOCKED (no browser or not a reveal deck).

## Quick Reference

| Part | Rule |
|---|---|
| Story | Pick a structure from `references/story-structures.md` before any slide |
| Headline | A full sentence stating the slide's point (≤ 2 lines) |
| Words | ≤ 30 words of body per slide; detail goes to speaker notes |
| Type | Headline ≥ 56 px, body ≥ 24 px, labels ≥ 16 px at 1280 × 720 |
| Colour | Brand tokens, one accent for emphasis; contrast ≥ 4.5:1 (`palette.py check`) |
| Charts | One message per chart, labelled directly, the takeaway in the headline |
| Motion | Build-ups that follow the spoken point; auto-animate between related slides |
| Length | ~1 slide per 1–2 minutes of talk; pitch 10–12, demo 8–12 |

Design rules, layouts and chart guidance: `references/slide-design.md`.

## Procedure

```
- [ ] 1 Audience, goal and the one thing they must remember
- [ ] 2 Story outline (headlines only) approved
- [ ] 3 Design system set (tokens, type, layouts)
- [ ] 4 Pictures and charts planned
- [ ] 5 Slides built, notes written
- [ ] 6 Deck check clean, sheet reviewed
- [ ] 7 Export delivered (HTML / PDF / PPTX)
```

1. **Frame it.** Write in `.sdlc/deck-plan.md`: who is in the room, what
   they should do or believe afterwards, and the single sentence they must
   remember ("the big idea").
2. **Outline with headlines only.** Choose the structure in
   `references/story-structures.md` (template decks already fix it). Write
   every slide's headline as a sentence; read them in order — they alone
   must tell the story. Show the owner this outline before designing.
3. **Set the design system.** From the template, brand or `design-brief.md`:
   colour tokens (checked with `ultimate-builder:color-and-ux`), one display
   face and one text face, 4–6 layouts (title, statement, two-column,
   picture-led, chart, quote). Use `skill_view(name="frontend-design")` to
   avoid the generic look. Every slide reuses these layouts.
4. **Plan the visuals** for each slide: the owner's screenshots, photos and
   numbers first; charts drawn as SVG from their real data; AI pictures via
   `.lyra/kit/imagine` for atmosphere or illustration only (record each in
   `assets/ASSETS.md`); a designed type slide when no picture helps.
5. **Build.** One `<section>` per slide, speaker notes in
   `<aside class="notes">`, `class="fragment"` for build-ups, `data-auto-animate`
   between slides that evolve. Keep CSS in tokens. Missing facts become a
   visible `[owner to supply]` placeholder, never an invented figure.
6. **Check.** Run the deck check, fix every listed problem, then open
   `sheet.png` and judge it as a presentation coach: does each headline
   state a point, is there one idea per slide, is the layout consistent, is
   anything cramped? Fix the five weakest slides and re-run.
7. **Export** the formats in `requirements.md`: the HTML deck and its PDF
   (`--pdf`); a `.pptx` through the `powerpoint` skill, keeping the
   outline, palette and fonts, and checked with that skill's thumbnail
   rendering (the deck check covers HTML decks only).

## Pitfalls

- Topic headlines ("Market", "Traction") waste the most-read line; state
  the point ("2.1 million small fleets in Europe").
- Bullet walls: if a slide needs more than three bullets, it is two slides
  or a diagram.
- Charts with legends, gridlines and 3D effects; label the lines directly
  and remove everything that is not data.
- Invented traction, logos or quotes in a pitch deck — never, even as a
  sample; use placeholders.
- Different fonts and colours per slide; the system from step 3 applies to
  all.
- Content positioned for one screen size: always build at 1280 × 720 and let
  reveal.js scale it.

## Verification

- The headlines read in order tell the whole story.
- `deck-check.mjs` exits 0 (or each remaining item is reported with a
  reason) and `sheet.png` was opened and reviewed.
- The PDF has one page per slide and opens cleanly; a `.pptx` opens in
  PowerPoint or Keynote with nothing missing.
- Every number has a source the owner gave; every AI picture is listed.
