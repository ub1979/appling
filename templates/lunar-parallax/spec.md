# Template: Lunar Parallax (photo-real)

An expedition-style landing page for [TOPIC — one line], told with deep,
layered photography.

## Pictures (ask first, one question)
The hero is six separate layers, each its own picture:
background (sky/space) · a glowing subject (planet, sun) · the title · the
landscape · a figure · a foreground frame (rocks, leaves). Options:
1. **The owner's photos** — Appling cuts subjects out with `.lyra/kit/cutout`
   (plain or green-screen backgrounds work best).
2. **AI pictures** with `.lyra/kit/imagine` on the owner's ChatGPT plan, each
   layer made separately: glowing subjects on pure black (blend with
   `mix-blend-mode: screen`), landscapes with a pure black sky (cut out
   `--from top`), dark foregrounds on pure white, figures on chroma green.
3. A **short video** works for the reel section (frames via `.lyra/kit/frames`).

## Stack
Vite + TypeScript, GSAP + ScrollTrigger, Lenis. WebP layers.

## Mood
Deep black, frost white, one warm amber accent, a cool ice blue. A wide
geometric display face (e.g. Syncopate) with generous tracking, a light sans
and a mono for coordinates and timecodes.

## Sections
1. **Earthrise** — pinned; six layers drift with the pointer by depth; on
   scroll the planet rises behind the title, the camera pushes in and the
   foreground parts; coordinates and mission time tick.
2. **Trajectory** — pinned; a route inks itself from Earth to Moon, a craft
   rides the line, milestones light up and the distance counts to 384,400 km.
3. **Mission reel** — film-strip frames (sprocket holes, timecodes) slide
   past and warm from dim to full colour.
4. **Reserve a seat** — closing call to action with a one-line form.

## Effects to check
Layers move at different speeds · the planet rises behind the title · route
draws and the counter matches · milestones light in order · the reel slides
· reduced motion shows the full scene still.

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
five issues. The live demo (`.lyra/kit/reference/index.html` in an Appling
project) is the reference for every effect above.
