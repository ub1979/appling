# Template: Charity & Impact

A warm, trustworthy site for [CAUSE — one line: who you help and how] that
turns visitors into supporters.

## Stack
Vite + TypeScript, GSAP + ScrollTrigger, Lenis. Static output.

## Mood
Hopeful and honest: deep sea blue, sand, sunshine yellow, sea-glass teal. A
characterful serif (e.g. DM Serif Display) for headlines, a friendly sans
(e.g. DM Sans) for everything else. Real faces and places when you have them.

## Sections
1. **Hero** — a layered scene (waves, hills or city) whose layers move at
   different speeds; the sun sinks as you scroll away; a short promise.
2. **Journey map** — the section pins while a route draws itself across a
   simple map; each stop lights up with a pulse and its own caption, one after
   another, with no empty moments.
3. **Impact** — three big numbers that count up, with growing bars.
4. **Stories** — three short story cards with pictures.
5. **Donate** — monthly / one-off switch, three amounts, a line saying what
   that gift does, and a big button; footer with charity number.

## Effects to check
Waves move at different speeds · route draws and stops light up in order ·
a caption is always visible during the map · numbers count · the donation
line updates with the amount · reduced motion lists every stop as text.

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
