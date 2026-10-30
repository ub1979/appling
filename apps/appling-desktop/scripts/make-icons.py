"""Generate installer icons matching the Appling UI's purple A mark."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "icons"
ICONS.mkdir(exist_ok=True)
SIZE = 1024
image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
pixels = image.load()
for y in range(80, 944):
    for x in range(80, 944):
        t = (x + y - 160) / 1728
        pixels[x, y] = (int(109 + 34 * t), int(92 + 15 * t), 245, 255)

mask = Image.new("L", (SIZE, SIZE))
ImageDraw.Draw(mask).rounded_rectangle((80, 80, 944, 944), radius=220, fill=255)
image.putalpha(mask)
font = None
for candidate in (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
):
    if Path(candidate).exists():
        font = ImageFont.truetype(candidate, 635)
        break
if font is None:
    raise RuntimeError("Install Arial Bold or DejaVu Sans Bold to regenerate icons")
draw = ImageDraw.Draw(image)
bounds = draw.textbbox((0, 0), "A", font=font)
draw.text(((SIZE - (bounds[2] - bounds[0])) / 2 - bounds[0],
           (SIZE - (bounds[3] - bounds[1])) / 2 - bounds[1] - 32),
          "A", font=font, fill="white")
image.save(ICONS / "icon.png")
image.save(ICONS / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
image.save(ICONS / "icon.icns")
