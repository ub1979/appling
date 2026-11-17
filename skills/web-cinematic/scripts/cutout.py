#!/usr/bin/env python3
"""Cut a subject out of a plain background so it can float in a parallax layer.

    python cutout.py in.png out.png [--bg white|black|green|auto] [--tolerance 38]
                                    [--from all|top|bottom|sides] [--feather 1.2]
                                    [--max-width 1800]

The background is whatever plain colour touches the picture's edges (ask the
image model for "on a plain pure white background", or chroma green for white
subjects). It is flood-filled from the edges, so dark or light areas *inside*
the subject stay solid; `--from top` starts only from the top edge (a landscape
whose black sky should go but whose dark foreground shadows must stay).
Chroma green is keyed everywhere, gaps between arms and legs included, and
its spill is pulled out. Edges are softened and the result is saved as PNG or
WebP with transparency (by the out extension).

Glowing subjects on black (planets, fire, light trails) look better left on
black and blended on the page with `mix-blend-mode: screen` than cut out.

Needs only Pillow.
"""

from __future__ import annotations

import argparse
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter

SENTINEL = (255, 0, 254)
BACKGROUNDS = {"white": (255, 255, 255), "black": (0, 0, 0), "green": (0, 177, 64)}


def _edge_seeds(w: int, h: int, edges: str = "all", step: int = 24):
    for x in range(0, w, step):
        if edges in ("all", "top"):
            yield (x, 0)
        if edges in ("all", "bottom"):
            yield (x, h - 1)
    for y in range(0, h, step):
        if edges in ("all", "sides"):
            yield (0, y)
            yield (w - 1, y)


def _green_alpha(rgb: Image.Image, tolerance: int) -> Image.Image:
    """Alpha from how green each pixel is: g - max(r, b), ramped softly."""
    r, g, b = rgb.split()
    excess = ImageChops.subtract(g, ImageChops.lighter(r, b))
    lo, hi = max(8, tolerance // 3), max(20, tolerance)
    return excess.point(lambda v: 255 if v <= lo else 0 if v >= hi else round(255 * (hi - v) / (hi - lo)))


def _close(a, b, tol: int) -> bool:
    return all(abs(int(p) - int(q)) <= tol for p, q in zip(a, b))


def cutout(src: Image.Image, bg: str = "auto", tolerance: int = 38, feather: float = 1.2,
           edges: str = "all") -> Image.Image:
    rgb = src.convert("RGB")
    w, h = rgb.size
    if bg == "auto":
        corners = [rgb.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
        target = tuple(sum(c[i] for c in corners) // 4 for i in range(3))
    else:
        target = BACKGROUNDS[bg]
    green = bg == "green" or (bg == "auto" and target[1] > target[0] + 40 and target[1] > target[2] + 40)
    if green:
        alpha = _green_alpha(rgb, tolerance)
        if feather > 0:
            alpha = alpha.filter(ImageFilter.GaussianBlur(feather * .6))
        return _despill(rgb, alpha)
    work = rgb.copy()
    for seed in _edge_seeds(w, h, edges):
        px = work.getpixel(seed)
        if px != SENTINEL and _close(px, target, tolerance + 20):
            ImageDraw.floodfill(work, seed, SENTINEL, thresh=tolerance)
    # Background = filled pixels.
    r, g, b = work.split()
    is_bg = ImageChops.multiply(
        ImageChops.multiply(r.point(lambda v: 255 if v == SENTINEL[0] else 0),
                            g.point(lambda v: 255 if v == SENTINEL[1] else 0)),
        b.point(lambda v: 255 if v == SENTINEL[2] else 0))
    alpha = ImageChops.invert(is_bg)
    # Shrink one pixel to drop the halo, then soften the edge.
    alpha = alpha.filter(ImageFilter.MinFilter(3))
    if feather > 0:
        alpha = alpha.filter(ImageFilter.GaussianBlur(feather))
    out = rgb.copy()
    out.putalpha(alpha)
    return out


def _despill(rgb: Image.Image, alpha: Image.Image) -> Image.Image:
    # Green may not exceed the brighter of red and blue.
    rr, gg, bb = rgb.split()
    gg = ImageChops.darker(gg, ImageChops.lighter(rr, bb))
    out = Image.merge("RGB", (rr, gg, bb))
    out.putalpha(alpha)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--bg", default="auto", choices=["auto", *BACKGROUNDS])
    ap.add_argument("--tolerance", type=int, default=38)
    ap.add_argument("--feather", type=float, default=1.2)
    ap.add_argument("--from", dest="edges", default="all", choices=["all", "top", "bottom", "sides"])
    ap.add_argument("--max-width", type=int, default=1800)
    args = ap.parse_args(argv)
    img = Image.open(args.src)
    if img.width > args.max_width:
        img = img.resize((args.max_width, round(img.height * args.max_width / img.width)), Image.LANCZOS)
    result = cutout(img, args.bg, args.tolerance, args.feather, args.edges)
    if args.out.lower().endswith(".webp"):
        result.save(args.out, quality=82, method=6)
    else:
        result.save(args.out, optimize=True)
    kept = sum(result.getchannel("A").histogram()[129:]) / (result.width * result.height)
    print(f"saved {args.out} ({result.width}x{result.height}), subject covers {kept:.0%} of the picture")
    return 0


if __name__ == "__main__":
    sys.exit(main())
