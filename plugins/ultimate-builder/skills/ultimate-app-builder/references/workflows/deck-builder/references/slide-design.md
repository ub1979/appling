# Slide design

## Contents
- Canvas and grid
- Type
- Colour
- Layouts
- Charts and data
- Pictures
- Motion
- Speaker notes
- reveal.js setup

## Canvas and grid

- 1280 × 720 (16:9). Safe margin 64 px on every side; nothing important
  outside it.
- 12-column grid, 24 px gutters. Align every element to it; the headline
  sits in the same place on every content slide.
- White space is part of the design: a slide at 60% full looks confident.

## Type

- One display face for headlines (with character), one text face for body;
  a monospace only for code. Load from Google Fonts or the brand files.
- Sizes at 1280 × 720: title 96–140 px, headline 56–72 px, body 24–32 px,
  labels and sources 16–20 px.
- Headlines in sentence case, left-aligned on content slides; maximum two
  lines.
- Numbers that matter set huge (120 px+) with a short label beneath.

## Colour

- Background, text, muted text, one accent, plus chart colours — all as CSS
  custom properties.
- The accent marks the one thing to look at (a word, a bar, a dot); never
  decoration.
- Dark slides for openers, section breaks and the close; light for dense
  content — or one theme throughout, chosen for the room (dark rooms favour
  dark slides).
- Check every pair with `palette.py check` (from `color-and-ux`).

## Layouts

Build these once and reuse them:

| Layout | Use |
|---|---|
| Title | Opening, section breaks, the close |
| Statement | One sentence or one big number, nothing else |
| Picture-led | Full-bleed photo or screen with a headline on a scrim |
| Two-column | Claim + evidence, before/after, text + screen |
| Chart | Headline (the takeaway) + one chart + source line |
| Cards | Three steps or three options, equal weight |
| Quote | A real quote, the person's name and role |
| Table | Comparison or pricing, ≤ 5 rows visible |

## Charts and data

- One message per chart; the headline states it ("Growth came in the
  second half").
- Bar for comparisons, line for change over time, a single big number when
  there is one number; avoid pie charts beyond 3 slices, never 3D.
- Label series directly at the end of the line or on the bar; no legend
  when direct labels fit.
- Highlight the bar or point that matters in the accent; the rest muted.
- Axes start at zero for bars; always a source line.
- Draw as inline SVG from the owner's data so it stays sharp and editable;
  animate with a fragment (bars grow, line draws) only when the talk
  reveals it step by step.

## Pictures

- Real screenshots of the product, cropped tight to the part being
  discussed, with a soft shadow or device frame.
- Photos full-bleed or in a strict grid; never small and floating.
- AI pictures (`.lyra/kit/imagine`, owner's consent) for mood, metaphor or
  illustration — one consistent style for the whole deck; never fake
  product screens, people presented as real, or charts.
- Icons from one set only, same stroke and size.

## Motion

- Build-ups (`fragment`) only when the speaker reveals points one at a
  time; otherwise show the whole slide.
- `data-auto-animate` between slides that share elements (a diagram that
  grows, a number that changes).
- One transition style for the whole deck (`fade` or `slide`), speed fast.
- Nothing moves on its own while the speaker talks.

## Speaker notes

Every content slide gets notes: what to say (3–5 short lines), the number
to stress, and the transition sentence to the next slide. Notes carry the
detail that was cut from the slide.

## reveal.js setup

```html
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/5.2.1/reveal.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/5.2.1/reveal.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/5.2.1/plugin/notes/notes.min.js"></script>
<script>
  Reveal.initialize({ hash: true, width: 1280, height: 720, margin: 0,
    transition: 'fade', center: false, plugins: [RevealNotes] });
</script>
```

Press **S** for the speaker view; `?print-pdf` is the print layout the deck
check uses for the PDF.
