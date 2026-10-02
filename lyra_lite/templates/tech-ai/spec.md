# Template: AI / Tech Company

A company site for [COMPANY — one line on what you build and for whom], led
by a living 3D visual instead of stock photos.

## Stack
Vite + TypeScript, three.js (points + BufferGeometry), GSAP + ScrollTrigger,
Lenis. Static output.

## Mood
Deep space dark, teal and periwinkle light, crisp off-white text. A light,
wide geometric sans (e.g. Outfit) at thin weights for big headings, a mono
(e.g. IBM Plex Mono) for small labels. Calm, precise, quietly confident.

## Sections
1. **Hero + journey** — one sticky 3D stage for ~4 screens of scroll: a cloud
   of ~6,000 glowing points (2,600 on phones) starts as a sphere behind the
   headline, then morphs into a sound wave, a neural cloud and tilted orbits —
   one shape per chapter ("Listen", "Learn", "Answer"), each with its caption.
   Points drift with the pointer; a side progress bar shows the chapter.
2. **Services** — an accordion of four services; one open at a time, with
   tags.
3. **Stats** — four counters in a ruled strip.
4. **Results** — three case cards with a soft glow that follows the cursor.
5. **Contact** — a huge closing line with a gradient button; footer.

## Effects to check
Sphere → wave → cloud → orbits as you scroll · captions change with the shape
· rendering pauses off-screen · accordion opens and closes · counters count ·
reduced motion shows a still cloud and every chapter as text.

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
