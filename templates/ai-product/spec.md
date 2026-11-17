# Template: AI Product

A product site for [PRODUCT — one line on what the AI does and for whom],
where the product proves itself: a real question answered live, with its
sources, in the first screen.

## Stack
Vite + TypeScript, GSAP + ScrollTrigger, Lenis. Static output. The product
interface is drawn in HTML/CSS (or real screenshots of it), never AI art.

## Mood
Warm paper, not "futuristic": an off-white page (#f6f3ec), near-black ink,
one deep forest-green accent. An editorial serif for display (e.g.
Instrument Serif, italic for emphasis) and a clean text sans (e.g. DM Sans).
Hairline rules, generous margins, calm and trustworthy — like a good
journal that happens to contain software. No glowing brains, robots,
neural-net art or purple gradients.

## Sections
1. **Hero** — outcome headline, a one-line subhead naming who it is for,
   one primary call to action (plus a quiet secondary). Beside it, the
   product window: a question types itself in, the answer streams in word
   by word, then numbered source chips appear and the cited passage is
   highlighted.
2. **Proof strip** — customer logos, a usage number or a press line.
3. **How it works** — three steps (connect → ask → act), each with a small
   product screen; the step number and screen enter together as you scroll.
4. **Use cases** — four cards, each a concrete job with a before / after
   (time or effort) written as words, not only colour.
5. **Show the model at work** — a worked example: the input, the answer,
   the sources it used, and an honest "what it won't do" note.
6. **Trust and data** — where data goes, retention, access control, the
   standards the owner really meets, and human review.
7. **Integrations** — the tools it connects to, as a simple grid of names.
8. **Pricing** — three plans, the recommended one highlighted.
9. **FAQ** — accuracy, privacy, setup time, pricing, as `<details>`.
10. **Final call to action** — the headline promise again and the button;
    footer.

## Effects to check
Question types in, answer streams, sources appear and the cited line
highlights · how-it-works screens enter with their step · use-case cards
rise in turn · worked example lines reveal as it scrolls into view · FAQ
opens and closes · reduced motion shows the finished answer, sources and
every section at once.

## Motion rules
Easing power3/expo, never linear; one hero idea per section; at most two
ambient animations on screen; transitions 0.6–1.2 s. Motion explains the
product (typing, streaming, citing) — no decorative loops.

## Quality
60 fps (animate only transform/opacity), lazy-load media, respect
prefers-reduced-motion with a static version, fully responsive (the
product window stacks under the headline on phones), visible focus
rings, one h1, Lighthouse performance ≥ 85, contrast checked with
`palette.py`.

## Ask the owner (one question at a time)
- The product's name, the one outcome it gives, and who it is for.
- A real question and the real answer the product gives (with its
  sources) for the hero and the worked example — or real screenshots.
- Proof they can back up: customer logos with permission, a usage number
  with a source, a press quote. Missing proof stays a visible placeholder.
- The 3–4 real use cases and the time or effort each one saves.
- Data facts: where data is stored, retention, whether it trains on
  customer data, certifications actually held (SOC 2, ISO 27001, GDPR).
- Integrations that really exist.
- Plans and prices (or "contact us"), and the call to action (trial,
  waitlist, demo).
- Logo and brand colours, if they differ from this palette.

## Process
The `website-builder` skill applies (AI product blueprint, copy and proof
rules, quality checklist). Section plan + component tree first; build one
section at a time and review; finish with a taste pass and a senior design
critique, fixing the top five issues. The live demo
(`.lyra/kit/reference/index.html` in an Appling project) is the reference
for every effect above.
