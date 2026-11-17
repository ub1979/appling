# Template: Creative Portfolio

A portfolio for [NAME — what they do], showing selected work.

## Stack
Vite + TypeScript, GSAP + ScrollTrigger, Lenis. Static output.

## Mood
Confident and minimal: off-black, bone white, one red signal colour. An
oversized grotesk for names and titles, small caps for meta.

## Sections
1. **Intro** — the name huge and cropped by the viewport edge; a one-line
   statement types in.
2. **Work index** — a list of projects; hovering a row reveals a floating
   preview image that follows the cursor (on phones: a tap opens it).
3. **Case study** — clicking a project expands its image into a full page
   with a smooth transition; sections of process images and text.
4. **About** — portrait with a slow parallax, short bio, clients marquee.
5. **Contact** — a giant email link with a magnetic hover.

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
