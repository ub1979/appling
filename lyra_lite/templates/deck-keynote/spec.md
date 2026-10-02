# Template: Keynote Story (slides)

A cinematic talk: full-bleed photos, big type, one idea per slide. For [TOPIC / AUDIENCE — one line].

## Slides
1. Title over a full-bleed photo — the big promise, one line under it.
2. The map of the talk — three chapters revealed one by one.
3. Chapter opener — full-bleed photo with a short headline at the bottom.
4–5. The number — one huge figure; the next slide auto-animates it smaller
   and adds the sentence that gives it meaning.
6. Chapter opener — photo with a side shade for the text.
7. A quote on its own, set large in italic serif.
8. What comes next — photo, headline, one line.
9. Thank you — closing photo, contact.

Photos slowly push in while their slide is on screen; speaker notes carry
the script (press S).

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
