# Template: Editorial Scroll Story

A long-form, magazine-style story for [TOPIC — one line], told in chapters.

## Stack
Vite + TypeScript, GSAP + ScrollTrigger, Lenis. Static output.

## Mood
Thoughtful and tactile, like a printed feature: paper-white, ink black, one
red accent, an olive secondary. A literary serif for text, a condensed sans
for chapter labels. Comfortable reading width (60–70 characters).

## Sections
1. **Cover** — full-bleed photo with a slow push-in, title and dek.
2. **Chapters** — each opens with a big chapter number, then body text with
   pull quotes that slide in from the margin.
3. **Sticky media** — a photo or chart stays pinned while three paragraphs
   scroll past and annotate it.
4. **Before / after** — a draggable comparison slider.
5. **Data moment** — one animated chart that draws itself on scroll.
6. **Ending** — credits, sources and a share line.

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
