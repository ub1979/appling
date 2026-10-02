"""color-and-ux palette checker and the photo-real helpers (cutout, frames)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

WORKFLOWS = (Path(__file__).resolve().parents[2] / "plugins" / "ultimate-builder" / "skills"
             / "ultimate-app-builder" / "references" / "workflows")
PALETTE = WORKFLOWS / "color-and-ux" / "scripts" / "palette.py"
CUTOUT = WORKFLOWS / "web-cinematic" / "scripts" / "cutout.py"
FRAMES = WORKFLOWS / "web-cinematic" / "scripts" / "frames.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, timeout=120)


def test_description_follows_the_skill_rule():
    text = (WORKFLOWS / "color-and-ux" / "SKILL.md").read_text()
    desc = re.search(r"^description: (.*)$", text, re.MULTILINE).group(1)
    assert len(desc) <= 60 and desc.endswith(".")


def test_palette_check_fails_faint_button_and_passes_a_fixed_one():
    bad = _run(str(PALETTE), "check", "bg=#ffffff", "text=#111111", "accent=#3b82f6", "on-accent=#ffffff")
    assert bad.returncode == 1 and "FAIL button label" in bad.stdout
    good = _run(str(PALETTE), "check", "bg=#ffffff", "text=#111111", "accent=#1d4ed8", "on-accent=#ffffff")
    assert good.returncode == 0, good.stdout


def test_palette_warns_when_signal_colours_look_alike_to_colour_blind_visitors():
    out = _run(str(PALETTE), "check", "bg=#ffffff", "success=#2e7d32", "danger=#c62828").stdout
    assert "look alike" in out


def test_palette_ramp_gets_darker_and_reaches_text_safe_shades():
    out = _run(str(PALETTE), "ramp", "#c8553d").stdout.splitlines()
    ratios = [float(re.search(r"on white\s+([\d.]+)", line).group(1)) for line in out]
    assert ratios == sorted(ratios) and len(ratios) == 11
    assert any("text-safe" in line for line in out)


def test_cutout_keys_green_everywhere_and_keeps_the_subject(tmp_path):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (200, 200), (0, 177, 64))
    draw = ImageDraw.Draw(img)
    draw.rectangle((60, 40, 140, 180), fill=(235, 235, 230))   # a white figure
    draw.rectangle((90, 120, 110, 180), fill=(0, 177, 64))     # green gap between "legs"
    src, out = tmp_path / "in.png", tmp_path / "out.png"
    img.save(src)
    assert _run(str(CUTOUT), str(src), str(out), "--bg", "green").returncode == 0
    alpha = Image.open(out).getchannel("A")
    assert alpha.getpixel((5, 5)) == 0          # background gone
    assert alpha.getpixel((100, 160)) < 30      # enclosed gap gone too
    assert alpha.getpixel((70, 60)) > 240       # subject kept


def test_cutout_from_top_keeps_dark_foreground(tmp_path):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (200, 200), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 80, 200, 200), fill=(120, 120, 120))  # ground
    draw.rectangle((0, 170, 200, 200), fill=(5, 5, 5))       # dark shadow touching the bottom
    src, out = tmp_path / "in.png", tmp_path / "out.png"
    img.save(src)
    assert _run(str(CUTOUT), str(src), str(out), "--bg", "black", "--from", "top").returncode == 0
    alpha = Image.open(out).getchannel("A")
    assert alpha.getpixel((100, 20)) == 0 and alpha.getpixel((100, 190)) > 240


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_frames_turns_a_clip_into_a_numbered_sequence(tmp_path):
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=24", "-t", "2",
                    "-pix_fmt", "yuv420p", str(clip)], check=True, timeout=60)
    out = tmp_path / "frames"
    assert _run(str(FRAMES), str(clip), str(out), "--count", "12", "--width", "160").returncode == 0
    listing = json.loads((out / "frames.json").read_text())
    assert listing["count"] == 12 and (out / "f_012.webp").is_file()
