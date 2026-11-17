# Template: Announcement (video)

Big news in 6–15 seconds: a headline that lands, one detail, your brand. For [BRAND / NEWS — one line].

## Scenes
1. The news resolves on a split-flap board ("NOW LIVE", "WE'RE HIRING")
2. The headline slams in and holds — the whole announcement in one line
3. Flash through white into the one supporting detail: a date, a number,
   a product screen or a notification that lands
4. Logo close with the call to action (link, date, "available today")

## Blocks to start from (HyperFrames registry)
`split-flap-board`, `flash-through-white`, `macos-notification`, `logo-outro`
(blocks), `headline-slam` (component)

## How Appling builds it
The `video-builder` skill applies. HyperFrames (Apache-2.0, by HeyGen and
contributors): plain HTML compositions rendered to MP4 in headless Chrome.

```
export HYPERFRAMES_NO_TELEMETRY=1 DO_NOT_TRACK=1 HYPERFRAMES_SKIP_SKILLS=1   # no usage data sent
npx hyperframes@latest init film --non-interactive --example blank && cd film
npx hyperframes@latest add <name>         # for each block/component above; read its SKILL.md
npx hyperframes@latest snapshot           # stills for the owner to approve
npx hyperframes@latest render -o out/announcement.mp4
```

Blocks land in `compositions/<block>/` and are included with the snippet
`add` prints; components land in `compositions/components/` and are pasted
into the scene that uses them.

Make it work as a loop: the last frame should cut cleanly back to the first.
Deliver 16:9 (website, LinkedIn, YouTube) and 1:1 (feed) — and 9:16 when the
owner posts to Reels or Stories — re-laid out for each size, not cropped.
Customise every block (words, brand colours, fonts, logo); never ship sample
content. Only real news: dates, numbers and names the owner confirmed.

## Ask the owner (one question at a time)
The news in one sentence, the one supporting detail (date, number, screen),
the call to action and link, the formats and where it will be posted, logo,
brand colours and fonts, and music or a sound sting (their own, or none).

## Quality
1080p minimum (1920 × 1080, 1080 × 1080, 1080 × 1920), 30 fps; the headline
readable for ≥ 2 s from the moment it lands; safe margins for platform
overlays; loudness −14 LUFS if there is audio; checked as a contact sheet and
by watching every format end to end.
