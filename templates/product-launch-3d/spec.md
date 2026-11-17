# Template: 3D Product Launch

A launch page where one hero product lives in 3D and reacts to scrolling,
for [PRODUCT — one line].

## Stack
Vite + TypeScript, three.js (or React Three Fiber), GSAP + ScrollTrigger,
Lenis. Static output.

## Mood
Dark, precise, a little electric — like a flagship device keynote. Palette:
near-black, an acid accent, a violet glow, soft white. Type: a tight
geometric sans for headlines, a mono for specs.

## Sections
1. **Hero** — the product (a real GLB model, or a sculpted primitive) floats
   centre stage with soft rim lights; headline and one-line promise; the
   product turns slowly and follows the mouse a little.
2. **Feature beats** — the 3D canvas stays pinned; as you scroll the camera
   dollies and the product rotates to show three features, each with a short
   headline that slides in and out.
3. **Specs** — key numbers count up as they enter; small mono labels.
4. **Colour picker** — three swatches recolour the product live.
5. **CTA** — price, a glowing buy button, and the product settling into a
   final hero angle.

## Images / assets
A product model (GLB) or studio renders; the demo sculpts the product from
three.js primitives with a particle halo.

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
five issues.
