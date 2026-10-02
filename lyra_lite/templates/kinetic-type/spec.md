# Template: Kinetic Type

A loud, type-led site for [EVENT OR BRAND — one line], where the words are
the visuals.

## Stack
Vite + TypeScript, GSAP + ScrollTrigger, Lenis. Static output.

## Mood
Night-club poster energy: near-black, acid lime, hot pink, off-white. A tall
condensed display face (e.g. Anton) at enormous sizes, a technical grotesk
(e.g. Space Grotesk) for small caps details. No photos needed.

## Sections
1. **Hero** — the name in two giant lines; letters drop in one by one, the
   lines slide apart as you scroll, and every letter stretches taller the
   faster you scroll.
2. **Marquee rows** — three rows of words (filled, outlined, accent colour)
   moving in alternating directions with the scroll; rows skew with speed.
3. **Split headline** — a four-word statement whose words fly in from
   scattered, rotated positions and lock into place with the scroll.
4. **Line-up / list** — big names in rows; hovering (or focusing) a name
   scrambles its letters into place; details on the right.
5. **Tickets** — full-colour block with a live countdown and a magnetic
   ticket button; footer.

## Effects to check
Letters stretch on fast scroll · rows move in opposite directions · words
assemble in the split headline · names scramble on hover · countdown counts
to a future date · reduced motion shows everything still.

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
five issues. The live demo (`.lyra/kit/reference/index.html` in an APP IT
project) is the reference for every effect above.
