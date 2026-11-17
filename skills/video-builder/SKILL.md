---
name: video-builder
description: Make short promo, social and explainer videos.
---

# Video Builder Skill

Make short videos (6–60 s) that look designed, not generated: product
launch clips, app promos, social reels with captions, explainers,
announcements and data stories. Motion is built in code with HyperFrames
(HTML compositions rendered to MP4), from the owner's real screens and
words; AI pictures add atmosphere when the owner agrees. For a premium
30–40 s commercial with 3D and AI footage, load
`skill_view(name="ultimate-builder:business-motion-film")` instead.

## When to Use

- The project kind is **Video** (this is its kind skill); a chosen template's
  spec names the HyperFrames blocks to start from.
- The owner asks for a promo, launch clip, ad, reel, TikTok/Shorts video,
  explainer, product demo video, announcement or animated chart.

## Prerequisites

- Approved `requirements.md`: purpose, length, aspect ratio(s), where it is
  posted, brand, the screens / footage / data, audio choice.
- Node 20+ and FFmpeg + FFprobe (`ffmpeg -version`).
- `.lyra/kit/imagine` for AI stills (only after the owner agreed; each uses
  their ChatGPT plan). There is no GPT video model in Appling: moving AI
  footage needs a video provider switched on in `hermes tools` (Video
  Generation); otherwise motion is code-built.

## How to Run

```
export HYPERFRAMES_NO_TELEMETRY=1 DO_NOT_TRACK=1 HYPERFRAMES_SKIP_SKILLS=1
npx hyperframes@latest init film --non-interactive --example blank && cd film
npx hyperframes@latest add <block>     # each block from the plan; read its SKILL.md
npx hyperframes@latest snapshot        # stills for review
npx hyperframes@latest render -o out/film.mp4 --browser-gpu
```

Browse blocks and components at https://hyperframes.heygen.com/catalog
(captions, kinetic type, lower thirds, transitions, charts, 3D, devices).

## Quick Reference

| Format | Size | Use |
|---|---|---|
| 16:9 | 1920 × 1080 | Website, YouTube, presentations |
| 9:16 | 1080 × 1920 | Reels, TikTok, Shorts (keep text out of the top 14% and bottom 20%) |
| 1:1 / 4:5 | 1080 × 1080 / 1080 × 1350 | Feed posts, launch posts |

| Rule | Value |
|---|---|
| Hook | The point or the product on screen within 2 s |
| Reading hold | ≥ 1.5 s from the moment words are fully legible (longer for long lines) |
| Timing | Plan in seconds, build in frames: 30 fps → 0.6 s = 18 frames |
| Easing | Ease-out entrances, ease-in exits, springs for UI; never linear on objects |
| Captions | Burned in for social (most views are muted), ≤ 2 lines, ≤ 32 characters per line |
| Audio | Music under effects; −14 LUFS integrated, true peak ≤ −1 dBTP |
| Ending | Logo + one call to action held ≥ 2 s |

Story shapes and technique choices: `references/video-playbook.md`.
Review loop and the export checks: `references/review-and-export.md`.

## Procedure

```
- [ ] 1 Brief: purpose, viewer, one action, format, length
- [ ] 2 Script + shot list with timings (seconds and frames)
- [ ] 3 Assets: real screens, footage, AI stills, audio
- [ ] 4 Three key stills approved
- [ ] 5 Scenes built one at a time
- [ ] 6 Review rounds with frame-numbered fixes
- [ ] 7 Final render checked and delivered
```

1. **Brief.** Write `BRIEF.md`: what it is for, who watches, where it is
   posted, the one thing the viewer should do, length and aspect ratio(s),
   brand, what is provably true, and what must never be claimed.
2. **Script and shot list.** Pick a shape from `references/video-playbook.md`.
   One table: time (s) → frame → what is on screen → words → the technique
   → what carries into the next shot. Write the longest version of each
   headline and check it fits the layout before any motion.
3. **Assets.** The owner's screens (record or screenshot at 2×), footage
   and logo first. AI stills with `.lyra/kit/imagine` (key picture first,
   then `--ref` it for consistency); list each in `assets/ASSETS.md`. Only
   music the owner owns or a licence covers.
4. **Three stills first.** Render the opening frame, the moment the
   product result shows, and the closing card. Get them approved (or
   critique them yourself against the brief: readable, result visible,
   nothing cropped, room for the call to action) before animating.
5. **Build scene by scene.** Customise every block — words, brand colours,
   fonts, logo, real screens, real data; never ship sample content. All
   motion is driven by the composition's timeline so any frame renders the
   same (no free-running timers or unseeded randomness). Give each scene a
   defined incoming and outgoing state; one family of transitions.
6. **Review.** Follow `references/review-and-export.md`: contact sheet,
   watch at normal speed, a fresh critic on the brief + frames, fixes
   written as location / problem / change / keep-fixed. Order: missing
   information and unreadable text, then timing, then polish.
7. **Deliver.** Final MP4 per format, a cover image from an approved frame,
   the editable project, `ASSETS.md`, and the check results.

## Pitfalls

- Starting with effects instead of the message: decide what the viewer
  reads and does first; motion serves it.
- Text that moves while it should be read, or leaves before it can be read
  aloud once at normal speed.
- Two things competing for attention: the cursor crossing a headline, a
  background loop behind small text.
- Sample block content (placeholder logos, lorem ipsum, demo charts) left
  in the render.
- Fake product UI or invented numbers in a promo; use the real screens and
  the owner's data, or mark it as a concept.
- Social videos without captions, or captions under the platform buttons.
- Rendering the full film before the stills and timing are right — it
  multiplies every fix.

## Verification

- Three key stills were reviewed before the motion pass.
- The final render was watched end to end at normal speed and its contact
  sheet opened.
- `ffprobe` shows the expected size, frame rate and duration for each
  format; loudness measured when there is audio.
- No sample content, no invented claims; every AI picture listed.
