# Template: Workshop & Teaching (slides)

A friendly class deck: agenda, goals, code, quiz, timed exercise. For [TOPIC / AUDIENCE — one line].

## Slides
1. Title — what people will make today, duration, what to bring.
2. Agenda — timed sections appearing one by one.
3. Goals — three coloured cards: what everyone will be able to do.
4. A step — code (or instructions) beside the result it produces.
5. Quick check — a multiple-choice question; the right answer lights up on
   the next click with a one-line explanation.
6. Your turn — three numbered tasks and a countdown (press T).
7. Recap — what was built, what is next, where the materials are.

## How Lyra builds it
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
