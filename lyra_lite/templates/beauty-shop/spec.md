# Template: Beauty & Wellness Shop

A soft, shoppable site for [BRAND — one line: what you make and for whom].

## Stack
Vite + TypeScript, GSAP + ScrollTrigger, Lenis. Static output. A real shop
plugs in later (Shopify Buy Button, Stripe links or similar) — ask first.

## Mood
Calm and tactile: blush, cocoa, rose, sage. A high-contrast fashion serif
(e.g. Bodoni Moda) for headlines, a rounded sans (e.g. Nunito Sans) for text.
Blurred colour blobs instead of hard shapes.

## Sections
1. **Hero** — the hero product floats gently below the headline; the section
   pins, the headline lifts away, the product grows and turns slightly, and
   three ingredients pop out around it one by one, then a one-line promise.
2. **Bestsellers** — four product cards; hovering tints the card and tilts
   the product; "Add to bag" bumps the bag counter in the header.
3. **Reviews** — a slow marquee of five-star quotes.
4. **Ritual** — three numbered steps on soft cards with drifting colour dots.
5. **Join** — newsletter sign-up with a first-order offer; footer.

## Effects to check
Product floats · ingredients gather around it in turn · bag counter bumps on
add · cards tint on hover · reviews scroll · reduced motion lists the
ingredients as plain text.

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
