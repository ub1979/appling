# Template: Sales Demo (slides)

A customer-first demo deck: their situation, what it costs them, your product at work, one next step. For [PRODUCT / AUDIENCE — one line].

## Slides
1. Title on dark — the customer's outcome (not your product name), who it is prepared for and the date.
2. Their situation — three numbers that describe how they work today.
3. The cost of it — one big number, its parts building one by one, and where the figures came from.
4–5. Before → after — the same moment twice ("one sick call means twelve phone calls" → "one tap"); the counter and the phone auto-animate between them.
6–8. Three capabilities — each a one-sentence headline, two short points (the second builds in) and a product screen showing exactly that feature.
9. Proof — a real, attributed customer quote and two result numbers.
10. How you start — three steps of a pilot beside the plan options, the recommended one highlighted.
11. Next step on dark — one action, one date, one contact.

## How Appling builds it
The `deck-builder` skill: an HTML deck on reveal.js 5 (MIT), one `index.html`,
1280×720 slides, speaker notes on every content slide (press S), fragments
only where the speaker reveals step by step, auto-animate between the
before/after slides. The live demo (`.lyra/kit/reference/index.html` when this
template was chosen) is the starting point — copy it and replace the content.

- Headlines are sentences that state the point, written for this customer.
- At most ~30 words of body text per slide; the detail goes in the notes.
- Product screens are the owner's real screenshots, or HTML recreations of
  real screens — never invented features.
- Numbers on the cost slide are the customer's own (say where they came from);
  the demo's case study is fictional and must be replaced or removed.
- Pick and check colours with `color-and-ux`; keep one accent.
- Check with `node .lyra/kit/deck-check.mjs deck --pdf deck/deck.pdf` and open
  its `sheet.png`.

## Ask the owner (one question at a time)
Who the customer is and what they told you in discovery, the cost numbers
they shared, the three capabilities that matter most to them (with
screenshots — attach with 📎), a real customer result you may quote, pilot
steps and prices, the single next step and its date, logo and brand colours,
and the file they need: the HTML deck, a PDF, or PowerPoint (`.pptx` via the
`powerpoint` skill, keeping this layout and palette).

## Quality
Readable on a shared screen: body ≥ 24 px, headings ≥ 56 px, labels ≥ 16 px,
contrast ≥ 4.5:1 (check with `palette.py`). The deck check passes (nothing
off a slide, no tiny text, ≤ 45 words per slide), every slide was looked at
with all fragments shown, and the PDF has one page per slide.
