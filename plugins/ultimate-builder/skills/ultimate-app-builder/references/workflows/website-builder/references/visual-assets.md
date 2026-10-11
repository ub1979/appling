# Pictures, screenshots and AI images

## Order of preference

1. **The owner's real product screens** — the strongest picture on any
   product site. Capture at 2× scale, crop to the part that tells the
   story, frame in simple browser or phone chrome drawn in CSS/SVG.
2. **The owner's photos and video** (`assets/uploads/` when attached in chat).
3. **AI pictures** with `.lyra/kit/imagine` — only after the owner said
   yes for this project; each picture uses their ChatGPT plan allowance.
4. **Designed placeholders** — gradients, shapes, type compositions — plus
   a list in the report of exactly which pictures the owner should supply.

Never hot-link images, never use stock without a licence the owner holds,
never present an AI picture as a real product, place, customer or employee.

## AI pictures with imagine

```
.lyra/kit/imagine "PROMPT" --out assets/hero.png --aspect landscape
.lyra/kit/imagine "same scene, camera 20° lower" --out assets/hero-2.png --ref assets/hero.png
```

Write prompts as a photo or art-direction brief:

- **Subject and use**: what it shows and where it sits on the page ("hero
  background, text sits on the left third").
- **Style**: medium (editorial photograph, 3D render, flat illustration,
  isometric), era, references in words, never a living artist's name.
- **Camera and light**: lens, angle, light quality ("50 mm, eye level,
  soft window light from the right").
- **Palette**: the site's token colours by hex.
- **Composition**: negative space for text, aspect, crop.
- **Exclusions**: "no text, no logos, no watermark, no people" as needed.

Make one key picture first, then pass it with `--ref` to keep the series
consistent (same light, same palette, same camera).

Record each in `assets/ASSETS.md`:

```
| File | Prompt | Used in | AI? |
|---|---|---|---|
| assets/hero.png | "…" | Home hero | yes |
```

## Good uses of AI pictures on professional sites

- Abstract textures and backgrounds in the brand palette.
- Illustrations for use cases and empty states, as one consistent set.
- Mood photography for a new company when no shoot exists — labelled
  internally as AI and replaceable later.
- Cut-out objects for parallax layers (see `web-cinematic`).

Avoid: AI people as "our team" or "customers", AI screenshots of software,
AI logos of real companies.

## Optimisation

- Convert to WebP (or AVIF) at the size actually displayed; give `srcset`
  for 1× and 2×.
- Every `<img>` has `width`, `height`, and meaningful `alt` (empty `alt=""`
  for decoration).
- Hero image ≤ 250 KB and preloaded; everything below the fold
  `loading="lazy"`.
- Icons as inline SVG from one set; do not mix icon families.
