# Template: SaaS Launch

A product page for [APP — one line on what it does and for whom].

## Stack
Vite + TypeScript, GSAP + ScrollTrigger, Lenis. Static output.

## Mood
Crisp and trustworthy: deep ink, white, one blue accent, a green "success"
colour. A modern sans for everything, generous spacing, soft shadows.

## Sections
1. **Hero** — headline and sub-line; a product screenshot assembles itself
   from its panels (sidebar, cards, chart) as the page loads.
2. **How it works** — three steps; the screenshot stays pinned and highlights
   the part each step talks about.
3. **Features grid** — six features with small looping micro-animations.
4. **Logos and quotes** — an infinite logo marquee and three testimonials.
5. **Pricing** — three plans with a monthly / yearly toggle that animates.
6. **CTA + footer** — sign-up field and links.

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
