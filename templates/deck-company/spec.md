# Template: Company Intro (slides)

A calm 8–10 slide introduction: who you are, what you do, who you serve,
how you work, results, team, next step. For [COMPANY / AUDIENCE — one line].

## Slides
1. Title on dark green — the positioning in one line, a short sub-line, a
   simple skyline-style drawing of what you do.
2. What we do — three services as numbered cards that build one by one.
3. Who we serve — customer types with a count each, beside a large photo
   (the owner's picture; a drawn placeholder until then).
4. How we work — four specific promises on dark, revealed in turn.
5. Results — three big numbers and one short case line, with a source line.
6–7. Our story — a timeline that grows (auto-animate) from the first
   customer to today.
8. Team and locations — the people the client will meet, then the offices.
9. Next step on dark — one action, contact details.

## How Appling builds it
The `deck-builder` skill. An HTML deck on reveal.js 5 (MIT): one
`index.html`, 1280×720 slides, speaker notes (press S), fragments for
build-ups, auto-animate between the two timeline slides. The live demo
(`.lyra/kit/reference/index.html` when this template was chosen) is the
starting point — copy it and replace the content.

- Headlines are sentences that state the point; read in order they tell
  the story.
- At most ~30 words of body text per slide; the rest goes in speaker notes.
- Real photographs replace the drawn placeholders; real numbers replace the
  sample figures, each with its source. Nothing invented.
- Pick and check colours with `color-and-ux`; deep green, warm paper and one
  amber accent, or the owner's brand in the same roles.

Check every version with the deck check and open its sheet:
`node .lyra/kit/deck-check.mjs deck --pdf deck/deck.pdf`.

## Ask the owner (one question at a time)
Who the audience is and what they should do afterwards, the one-line
positioning, the services and customer types, the principles they really
work by, the real results and where each number comes from, the team members
to show (photos with permission), office locations, photos and logo to use
(attach with 📎), brand colours, and the file they need: the HTML deck
(present from a browser), a PDF, or PowerPoint (`.pptx` via the `powerpoint`
skill, keeping this layout and palette).

## Quality
Readable from the back of a room: body ≥ 24 px, headings ≥ 56 px, labels
≥ 16 px, contrast ≥ 4.5:1 on both the dark and the light slides (check with
`palette.py`). The deck check exits 0: nothing runs off a slide, no slide
over 45 words; its sheet was opened and every slide reviewed; the PDF has one
page per slide.
