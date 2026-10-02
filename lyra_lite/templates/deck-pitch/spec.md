# Template: Investor Pitch (slides)

A crisp 10–12 slide pitch: problem, product, traction, the ask. For [TOPIC / AUDIENCE — one line].

## Slides
1. Title on dark — the promise in five words, one line on what you do.
2. Problem — three numbers that hurt, building one by one.
3. Product — the app or service in one picture with a one-line promise.
4–5. How it works — three steps; the second slide auto-animates in the detail.
6. Market — TAM / SAM / SOM rings that appear in turn.
7. Traction — the headline number counts up; the growth line draws itself.
8. Business model — a simple pricing table that builds row by row.
9. Competition — a 2×2 map; your dot lands last.
10. Team — faces (or initials), names, one credential each.
11. The ask on dark — amount, what it buys (bar), runway, contact.

## How APP IT builds it
An HTML deck on reveal.js 5 (MIT): one `index.html`, 1280×720 slides,
speaker notes (press S), fragments for build-ups, auto-animate between
related slides. The live demo (`.lyra/kit/reference/index.html` when this
template was chosen) is the starting point — copy it and replace the content.

- One idea per slide; a headline that says the point, not the topic.
- At most ~30 words of body text per slide; the rest goes in speaker notes.
- Charts drawn from the owner's real numbers (SVG), labelled in words.
- Pick and check colours with `color-and-ux`; keep one accent.

## Ask the owner (one question at a time)
Audience and goal, length (slides or minutes), the real numbers and
pictures to use (attach with 📎), logo and brand colours, and the file they
need: the HTML deck (present from a browser), a PDF (Chrome print of
`?print-pdf`), or PowerPoint (`.pptx` via the `powerpoint` skill, keeping
this layout and palette).

## Quality
Readable from the back of a room: body ≥ 24 px, headings ≥ 56 px, contrast
≥ 4.5:1 (check with `palette.py`). Every slide checked as a screenshot with
all fragments shown; nothing cut off; the PDF export opens cleanly.
