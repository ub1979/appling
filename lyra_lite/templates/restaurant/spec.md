# Template: Restaurant & Food

A warm site for [RESTAURANT — one line: what you cook and where], made to
get people to book.

## Stack
Vite + TypeScript, GSAP + ScrollTrigger, Lenis. Static output.

## Mood
Candle-lit and generous: cream, espresso brown, terracotta, olive. An elegant
serif with italics (e.g. Cormorant Garamond) for names and headings, a
friendly sans (e.g. Manrope) for details. Arched picture frames.

## Sections
1. **Hero** — the name on dark brown; a small circle near the bottom grows
   with the scroll until the table photo (or illustration) fills the screen,
   the dish turning slightly, then a one-line caption appears.
2. **Our kitchen** — short story text; two pictures (one arched) wipe up into
   place with a slow zoom-out.
3. **Menu** — tabs (starters, mains, desserts…) that swap the list with a
   soft stagger; prices in the accent colour.
4. **Plates** — the section pins and a row of round plates slides past,
   spinning as it goes.
5. **Book a table** — opening hours and a booking form (name, date, time,
   guests) with a friendly confirmation; footer with address.

## Effects to check
Circle grows to full screen · pictures wipe up · menu tabs switch · plates
slide and spin · the form confirms · reduced motion shows the table photo.

## Motion rules
Easing power3/expo, never linear; one hero idea per section; at most two
ambient animations on screen; transitions 0.8–1.4 s.

## Quality
60 fps (animate only transform/opacity), lazy-load media, dispose 3D
off-screen, respect prefers-reduced-motion with a static version, fully
responsive (simplify parallax and drop mouse-tilt on phones), Lighthouse
performance ≥ 85.

## Process
Section plan + component tree first; build one section at a time and review;
finish with a taste pass and a senior Awwwards-judge critique, fixing the top
five issues. The live demo (`.lyra/kit/reference/index.html` in an Appling
project) is the reference for every effect above.
