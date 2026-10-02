# Template: Grand Reveal (photo-real)

A cinematic launch page for [PRODUCT — one line: what is being unveiled and
for whom]. Built on real footage: the hero is a video played frame by frame
as the visitor scrolls.

## Footage and pictures (ask first, one question)
Best → worst, and what Lyra does with each:
1. **The owner's video** of the reveal (5–15 s, steady camera, 1080p+).
   Lyra turns it into 90–150 frames with `.lyra/kit/frames` and plays them
   on a canvas as you scroll.
2. **Frames** the owner already has (a numbered image sequence) — used as is.
3. **Two to five stills of the same shot** (covered → half → uncovered) — the
   player slides a soft wipe from one to the next (what the demo does).
4. **AI stills** with `.lyra/kit/imagine` on the owner's ChatGPT plan: make the
   first still, then edit it with `--ref` so camera and room stay identical.
   Only with the owner's yes; real products need real photos.
Details for the tour section: two or three close-ups (owner's or AI).

## Stack
Vite + TypeScript, GSAP + ScrollTrigger, Lenis; a canvas frame player
(preload, `object-fit: cover` drawing, blend between neighbouring frames).

## Mood
Dark atelier: warm black, oxblood, brass, bone. A refined italic display
serif (e.g. Cormorant) for acts and headings, a light sans for text, a mono
for timecodes and labels. Film language: acts, reel numbers, timecode.

## Sections
1. **The reveal** — pinned for ~3–4 screens; scroll (or drag sideways) scrubs
   the footage; three acts fade in and out; a timecode and speed readout move
   with the scroll; a slow push-in.
2. **Detail tour** — pinned close-ups with a slow camera drift; the second
   shot wipes across the first; captions change with the shot.
3. **Specification** — a drawn tachometer (or gauge fitting the product)
   whose needle sweeps while the spec numbers count up with it.
4. **Private viewing** — an invitation with a one-line form; footer.

## Effects to check
Footage scrubs smoothly both ways · acts match what is on screen · drag
scrubs on desktop · second detail shot wipes in · needle and numbers move
together · reduced motion shows the final frame and all text.

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
