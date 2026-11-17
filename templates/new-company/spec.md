# Template: New Company

The first website for [COMPANY — one line on what you do and for whom]: a
calm, editorial site that says who you are, what you do and how to start
working with you.

## Stack
Vite + TypeScript, GSAP + ScrollTrigger. Static output. No images needed to
start: the hero figure and case pictures are drawn in SVG and swapped for
real photos when the owner has them.

## Mood
Refined and credible. Warm stone background, near-black ink, one deep
ultramarine accent used sparingly (a word in each headline, the main button,
one shape in the hero figure). A serif with presence for headings (e.g.
Newsreader, light weight, italics for emphasis) and a clean humanist sans for
text (e.g. Albert Sans). Strict 12-column grid, generous whitespace, thin
rules, numbered sections (01–05).

## Sections
1. **Hero** — a positioning line in three lines of large serif, a short
   paragraph, one call to action ("Book an intro call"), and a wide figure
   plate: a technical-drawing-style SVG composition with labels.
2. **Services marquee** — a slow italic strip of the services.
3. **What we do** — a heading on the left, an accordion of 3–4 services on
   the right; one open at a time.
4. **How we work** — three specific principles in three ruled columns
   (never "innovative solutions").
5. **Selected work** — three case cards (picture, sector, year, one-line
   outcome); real work only, or capability descriptions when there is none.
6. **The studio** — founders as initials avatars with roles, then a short
   founding story with a pull quote.
7. **Contact** — email and location, and a three-field form (name, email,
   message) with inline errors and a success message.
8. **Footer** — copyright, legal links, social links that exist.

## Effects to check
Headline rises line by line on load · the accent flap in the hero figure
unfolds · the circles drift as the figure scrolls past · marquee runs slowly
· sections fade up once · accordion opens and closes with keyboard · phone
menu opens full height, keeps focus inside, closes with Escape · form shows
errors next to each field and a success line · reduced motion shows
everything static.

## Motion rules
Restrained: one orchestrated page load, then single fade-ups per section.
Easing power3/expo, never linear on objects; nothing moves while the visitor
reads; transitions 0.8–1.4 s.

## Quality
Animate only transform/opacity; one h1, landmarks, visible focus rings;
contrast ≥ 4.5:1 for text (check with `palette.py`); no sideways scroll at
390 px; meta description and Open Graph tags; Lighthouse performance ≥ 85.

## Ask the owner (one question at a time)
1. The positioning line: what you do and for whom, in one sentence.
2. Your 3–4 services, each with one line on the result for the client.
3. Real work you can show (projects, clients who agreed to be named) — or
   none yet, and we describe capability instead.
4. The team: names, roles, and whether to use photos or initials.
5. Photos or brand files you have (logo, colours, office or product shots).
6. Contact details: email, city or address, and where form messages go.

## Process
Use the website-builder skill (New company blueprint, copy and proof rules,
quality checklist). Section plan first; build one section at a time and run
the site check after each; finish with a judge pass that fixes the five
weakest things. Never invent clients, logos or numbers — use marked
placeholders. The live demo (`.lyra/kit/reference/index.html` in an Appling
project) is the reference for every effect above.
