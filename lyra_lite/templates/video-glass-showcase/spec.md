# Template: Glass UI Showcase (video)

Frosted-glass widgets over a living aurora — modern SaaS polish. For [BRAND / PRODUCT — one line].

## Scenes
1. Aurora background with the headline
2. Glass stat cards build up
3. A notification shows the value
4. The product UI in 3D
5. Logo and call to action

## Blocks to start from (HyperFrames registry)
`liquid-glass-widgets`, `liquid-glass-notification`, `ui-3d-reveal`, `vfx-liquid-background`

## How Lyra builds it
HyperFrames (Apache-2.0, by HeyGen and contributors): plain HTML compositions
rendered to MP4 in headless Chrome.

```
export HYPERFRAMES_NO_TELEMETRY=1 DO_NOT_TRACK=1 HYPERFRAMES_SKIP_SKILLS=1   # no usage data sent
npx hyperframes@latest init film --non-interactive --example blank && cd film
npx hyperframes@latest add <block>        # for each block below; read its SKILL.md
npx hyperframes@latest snapshot           # stills for the owner to approve
npx hyperframes@latest render -o out/film.mp4 --browser-gpu   # GPU flag for 3D/WebGL blocks
```

Each block lands in `compositions/<block>/` with its own `SKILL.md` saying
what to change; include it in `index.html` with the snippet `add` prints.

Customise every block (words, brand colours, fonts, logo, screenshots,
data) — never ship a block with its sample content. Join scenes with one
family of transitions (catalog `transitions-*`), keep a single type system,
and check colours with `color-and-ux`. Snapshots (`hyperframes snapshot`)
go to the owner for approval before the full render.

## Ask the owner (one question at a time)
Length and format (16:9 for web/YouTube, 9:16 for Reels/TikTok, 1:1 feed),
logo and brand colours, the screenshots / footage / data to show (attach with
📎), voice-over or captions, music (their track, or none), and where it will
be posted.

## Quality
1080p minimum, 30 fps; every word readable for at least 1.5 s; safe margins
for social overlays; loudness −14 LUFS if there is audio; final check by
watching the render end to end and a contact sheet of frames.
