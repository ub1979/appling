# Template: Data Report (slides)

An editorial report deck: KPIs, charts that grow, honest tables. For [TOPIC / AUDIENCE — one line].

## Slides
1. Title — the year's story in one line; organisation and date.
2. At a glance — four KPIs, each with its change, revealed one by one.
3. The main trend — a bar (or line) chart that grows in, values labelled on
   the bars, the headline says what it means.
4. Money or mix — a donut that sweeps in, with the three parts explained in words.
5. Breakdown — a table that builds row by row; good and bad marked in words
   and colour; one sentence explaining the outlier.
6. What we will change — three numbered decisions.

Every chart slide names its source at the bottom. Colour carries meaning
only together with a word or sign (▲ ▼ + −).

## How Appling builds it
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
