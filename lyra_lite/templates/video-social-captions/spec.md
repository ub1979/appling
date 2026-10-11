# Template: Social Captions Reel (video)

A vertical reel told in bold, word-by-word captions that work muted. For [BRAND / TOPIC — one line].

## Scenes
1. Hook in the first second: one bold claim or number, slammed in
2. 3–5 fast beats, one caption line each, the spoken word highlighted
3. The payoff: the result, a before/after or the product on screen
4. Follow / call to action card
5. Logo close

## Blocks to start from (HyperFrames registry)
`caption-pill-karaoke`, `caption-kinetic-slam`, `caption-emoji-pop` (components),
`tiktok-follow`, `logo-outro` (blocks)

## How Appling builds it
The `video-builder` skill applies. HyperFrames (Apache-2.0, by HeyGen and
contributors): plain HTML compositions rendered to MP4 in headless Chrome.

```
export HYPERFRAMES_NO_TELEMETRY=1 DO_NOT_TRACK=1 HYPERFRAMES_SKIP_SKILLS=1   # no usage data sent
npx hyperframes@latest init film --non-interactive --example blank && cd film
npx hyperframes@latest add <name>         # for each block/component above; read its SKILL.md
npx hyperframes@latest snapshot           # stills for the owner to approve
npx hyperframes@latest render -o out/reel.mp4
```

Blocks land in `compositions/<block>/` and are included with the snippet
`add` prints; components land in `compositions/components/` and are pasted
into the scene that uses them. The canvas is 1080 × 1920.

Captions come from the owner's script or voice-over: time each word to the
audio (or to a reading pace of about 2.5 words a second when there is no
voice), one caption style for the whole reel, the current word in the accent
colour. Customise every block (words, brand colours, fonts, handle, logo);
never ship sample content. Join beats with hard cuts or one transition family.

## Ask the owner (one question at a time)
The topic and the one thing viewers should do, the script or a voice-over
recording (attach with 📎), the platform(s) and their handle, brand colours,
fonts and logo, any clips or screenshots to show behind the captions, and
music (their track, or none).

## Quality
1080 × 1920, 30 fps; captions ≥ 48 px, ≤ 2 lines, high contrast on a pill or
shadow; text and key action kept out of the top ~14% and bottom ~20% (platform
buttons) and ~6% from each side; every line readable for ≥ 1.5 s; loudness
−14 LUFS if there is audio; checked as a contact sheet and by watching the
render end to end, muted and with sound.
