# Template: Cinematic Parallax

A cinematic, scroll-driven landing page for [BRAND — one line: what it is,
who it's for].

## Stack
Vite + TypeScript, GSAP + ScrollTrigger, Lenis smooth scroll. Static output.

## Mood
Calm, premium, editorial — like a luxury travel film. Palette: deep night
blue, warm sand, ember accent, mist. Type: an expressive display serif for
headlines (e.g. Fraunces) and a clean sans for body (e.g. Inter). Generous
whitespace, huge headlines (clamp 4–12vw).

## Sections (each a full-viewport scene)
1. **Hero** — layered depth parallax: background, midground, foreground and
   subject layers move at 0.2 / 0.5 / 0.8 / 1.1 speed on scroll plus a subtle
   mouse tilt. Headline split by word, staggered reveal from blur to sharp.
   Scroll cue.
2. **Pinned story** — the section pins for ~300vh; an image sequence (or a
   canvas scene) scrubs frame by frame with scroll, with three text beats
   fading in and out beside it.
3. **Horizontal gallery** — vertical scroll drives a horizontal track of five
   cards; cards skew slightly with scroll velocity.
4. **Text reveal** — a large paragraph whose words go from 15% to 100%
   opacity as they scroll into view.
5. **CTA + footer** — an oversized wordmark bleeding off the bottom edge and
   a magnetic button.

## Images
Parallax layers as transparent PNGs (bg, mid, fg, subject), a 60–120 frame
sequence for the pinned story, five gallery images. The demo uses procedural
SVG/canvas art instead.

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
