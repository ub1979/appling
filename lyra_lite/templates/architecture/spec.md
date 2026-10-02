# Template: Architecture & Property

A quiet, premium site for [PROJECT OR PRACTICE — one line: what, where].

## Stack
Vite + TypeScript, GSAP + ScrollTrigger, Lenis. Static output.

## Mood
Gallery-like restraint: stone, ink, warm grey, one brass accent. A tall
editorial serif (e.g. Instrument Serif) for headlines, a light condensed sans
(e.g. Inter Tight) for text and small spaced capitals for labels. Lots of air.

## Sections
1. **Hero** — the building picture opens from a small window to full screen
   with a slow zoom-out; two headline lines rise from masks; it drifts with
   scroll.
2. **Split screen** — on the left, one short text pinned in the middle of the
   screen; on the right, tall framed pictures scroll past; the text changes
   to match the picture in view (stacked simply on phones).
3. **Plans** — tabs for each home type; the floor plan draws its walls as
   lines, room names appear, and a spec table and price update beside it.
4. **Gallery** — an off-grid set of framed pictures, each drifting inside its
   frame and wiping up as it enters; a pull quote.
5. **Register interest** — dark closing block with a one-line email form;
   footer.

## Effects to check
Hero window opens to full bleed · pinned text follows the pictures · plan
lines draw · type tabs switch plan, specs and price · pictures drift in their
frames · form confirms.

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
five issues. The live demo (`.lyra/kit/reference/index.html` in a Lyra
project) is the reference for every effect above.
