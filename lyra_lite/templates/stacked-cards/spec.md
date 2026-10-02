# Template: Stacked Cards

A friendly product page for [APP — one line on what it does and for whom],
built around the phone it lives on.

## Stack
Vite + TypeScript, GSAP + ScrollTrigger, Lenis. Static output.

## Mood
Warm and confident: cream background, ink text, one indigo brand colour,
amber and mint accents. A heavy geometric display face (e.g. Sora) with tight
tracking, a clean sans (e.g. Inter) for body. Rounded corners everywhere.

## Sections
1. **Phone story** — the phone (real screenshots, or the app drawn in HTML)
   stays pinned beside three text beats; its screen cross-fades to match the
   beat being read. On phones the device rides along at the top, smaller.
2. **Stacked cards** — four feature cards stick one over another as you
   scroll; each card sinks and dims slightly as the next slides over it.
3. **Numbers** — three big stats that count up once.
4. **Card flip** — a 3D card that turns over as it crosses the screen.
5. **Get the app** — dark panel with store buttons; footer.

## Effects to check
Phone screen matches the beat (desktop and phone) · cards stack and dim ·
numbers count up · card turns to its back · reduced motion shows every screen.

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
