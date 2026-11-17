#!/usr/bin/env python3
"""Turn a video into a numbered WebP frame sequence for a scroll-scrubbed hero.

    python frames.py input.mp4 public/frames [--count 120] [--width 1600]
                     [--quality 72] [--start 0] [--end 0]

Frames are taken evenly across the clip (or between --start and --end
seconds), scaled to --width, and saved as f_001.webp, f_002.webp, … plus a
frames.json listing them. Aim for 90–150 frames at 1600 px wide: smooth to
scrub, and usually 4–8 MB in total. Needs ffmpeg and Pillow.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


def duration(video: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("video", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--count", type=int, default=120)
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--quality", type=int, default=72)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=0.0)
    args = ap.parse_args(argv)
    if shutil.which("ffmpeg") is None:
        print("ffmpeg is not installed (macOS: brew install ffmpeg)", file=sys.stderr)
        return 2
    total = duration(args.video)
    end = args.end or total
    span = max(0.1, end - args.start)
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(args.start), "-t", str(span), "-i", str(args.video),
                        "-vf", f"fps={args.count / span},scale={args.width}:-2", f"{tmp}/p_%04d.png"], check=True)
        pngs = sorted(Path(tmp).glob("p_*.png"))[: args.count]
        names = []
        for i, png in enumerate(pngs, 1):
            name = f"f_{i:03d}.webp"
            Image.open(png).convert("RGB").save(args.out / name, quality=args.quality, method=6)
            names.append(name)
    (args.out / "frames.json").write_text(json.dumps({"count": len(names), "frames": names}, indent=1))
    size = sum((args.out / n).stat().st_size for n in names) / 1e6
    print(f"{len(names)} frames → {args.out} ({size:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
