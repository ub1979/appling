#!/usr/bin/env python3
"""Check a colour palette before it ships, or build a ramp from one colour.

    python palette.py check bg=#0b0d12 surface=#12151d text=#e7eaf0 muted=#8b93a7 \\
                            accent=#3b82f6 on-accent=#ffffff success=#22c55e danger=#ef4444
    python palette.py ramp "#3b82f6"           # 11 shades, 50…950, even in lightness
    python palette.py from-image hero.jpg      # 6 main colours of a picture

`check` measures every text/background pair that matters (WCAG 2.2: body text
4.5:1, large text and UI parts 3:1, aim for 7:1 on long reading), warns when
the accent fails as a button or link, and warns when two signal colours (for
example success and danger) look alike to colour-blind visitors. Exit code 1
means at least one hard failure. Role names it understands: bg, surface,
text, muted, accent, on-accent, link, border, success, warning, danger, info.

Standard library only (`from-image` needs Pillow).
"""

from __future__ import annotations

import math
import sys


def hex_to_rgb(value: str) -> tuple[float, float, float]:
    h = value.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"not a colour: {value}")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def rgb_to_hex(rgb) -> str:
    return "#" + "".join(f"{round(max(0, min(1, c)) * 255):02x}" for c in rgb)


def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gamma(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def luminance(rgb) -> float:
    r, g, b = (_lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# OKLab / OKLCH (Björn Ottosson) for even-looking ramps.
def to_oklab(rgb):
    r, g, b = (_lin(c) for c in rgb)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = (math.copysign(abs(v) ** (1 / 3), v) for v in (l, m, s))
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def from_oklab(lab):
    L, a, b = lab
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
           -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
           -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)
    return tuple(_gamma(max(0.0, min(1.0, c))) for c in rgb)


def ramp(base: str) -> list[tuple[str, str, float]]:
    L0, a0, b0 = to_oklab(hex_to_rgb(base))
    chroma, hue = math.hypot(a0, b0), math.atan2(b0, a0)
    steps = [(50, .97), (100, .93), (200, .87), (300, .79), (400, .70), (500, .62),
             (600, .54), (700, .46), (800, .38), (900, .30), (950, .23)]
    out = []
    for name, L in steps:
        c = chroma * (1 - abs(L - .6) * .9)  # less colourful near white and black
        rgb = from_oklab((L, c * math.cos(hue), c * math.sin(hue)))
        out.append((str(name), rgb_to_hex(rgb), contrast(rgb, (1, 1, 1))))
    return out


# Colour-vision simulation (Machado 2009, severity 1.0), in linear RGB.
CVD = {
    "protanopia": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
    "deuteranopia": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
    "tritanopia": ((1.255528, -0.076749, -0.178779), (-0.078411, 0.930809, 0.147602), (0.004733, 0.691367, 0.303900)),
}


def simulate(rgb, kind: str):
    lin = [_lin(c) for c in rgb]
    return tuple(_gamma(max(0.0, min(1.0, sum(m * v for m, v in zip(row, lin))))) for row in CVD[kind])


def delta_e(a, b) -> float:
    la, lb = to_oklab(a), to_oklab(b)
    return 100 * math.dist(la, lb)


TEXT_PAIRS = [("text", "bg", 4.5, "body text"), ("text", "surface", 4.5, "text on cards"),
              ("muted", "bg", 4.5, "secondary text"), ("muted", "surface", 4.5, "secondary text on cards"),
              ("on-accent", "accent", 4.5, "button label"), ("link", "bg", 4.5, "links"),
              ("accent", "bg", 3.0, "accent as UI (icons, focus, borders)"), ("border", "bg", 1.5, "dividers (soft is fine)")]
SIGNALS = ["success", "warning", "danger", "info", "accent"]


def check(roles: dict[str, str]) -> int:
    rgb = {k: hex_to_rgb(v) for k, v in roles.items()}
    hard = 0
    print("Contrast")
    for fg, bg, need, label in TEXT_PAIRS:
        if fg in rgb and bg in rgb:
            r = contrast(rgb[fg], rgb[bg])
            ok = r >= need
            hard += 0 if ok or fg == "border" else 1
            extra = "  (aim 7:1 for long reading)" if fg == "text" and ok and r < 7 else ""
            print(f"  {'PASS' if ok else 'FAIL'} {label:38} {roles[fg]} on {roles[bg]}: {r:.2f}:1 (needs {need}:1){extra}")
    for sig in ("success", "warning", "danger", "info"):
        if sig in rgb and "bg" in rgb:
            r = contrast(rgb[sig], rgb["bg"])
            if r < 3:
                hard += 1
                print(f"  FAIL {sig} as an icon or badge on bg: {r:.2f}:1 (needs 3:1)")
    present = [s for s in SIGNALS if s in rgb]
    warnings = 0
    for i, a in enumerate(present):
        for b in present[i + 1:]:
            for kind in CVD:
                d = delta_e(simulate(rgb[a], kind), simulate(rgb[b], kind))
                if d < 12:
                    warnings += 1
                    print(f"  WARN {a} and {b} look alike with {kind} (ΔE {d:.1f}) — add an icon or label, not colour alone")
                    break
    if "bg" in rgb and "surface" in rgb and contrast(rgb["bg"], rgb["surface"]) < 1.06:
        print("  WARN surface is almost identical to bg — cards will not separate; use a border or shadow")
    print(f"\n{'OK' if not hard else f'{hard} failure(s)'}; {warnings} warning(s)")
    return 1 if hard else 0


def from_image(path: str, n: int = 6) -> int:
    from PIL import Image

    im = Image.open(path).convert("RGB")
    im.thumbnail((200, 200))
    pal = im.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    colours = pal.getpalette()[: n * 3]
    counts = sorted(pal.getcolors(), reverse=True)
    for count, idx in counts:
        rgb = tuple(c / 255 for c in colours[idx * 3: idx * 3 + 3])
        L, a, b = to_oklab(rgb)
        print(f"{rgb_to_hex(rgb)}  share {count / sum(c for c, _ in counts):5.1%}  lightness {L:.2f}  chroma {math.hypot(a, b):.3f}")
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "check":
        return check(dict(arg.split("=", 1) for arg in rest))
    if cmd == "ramp":
        for name, hx, c in ramp(rest[0]):
            print(f"{name:>4} {hx}  on white {c:5.2f}:1  {'text-safe' if c >= 4.5 else 'UI-safe' if c >= 3 else ''}")
        return 0
    if cmd == "from-image":
        return from_image(rest[0])
    print(f"unknown command {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
