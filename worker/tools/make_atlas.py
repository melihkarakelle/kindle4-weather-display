#!/usr/bin/env python3
"""
Build-time font atlas generator for the Kindle Worker.

The Worker cannot run a TrueType rasteriser, so every glyph it needs is
rendered here (Pillow) into a 1-bit bitmap and written to src/atlas.json.
At runtime the Worker only copies pixels.

Run on the Mac whenever a font, size or character set changes:

    python3 tools/make_atlas.py
"""

import base64
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
OUT = os.path.join(APP, "src", "atlas.json")

# Fonts: logical name -> candidate paths (first existing wins)
FONTS = {
    "bold": [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ],
    "regular": [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ],
    "weather": [
        os.path.join(APP, "assets", "weathericons.ttf"),
    ],
    "awesome": [
        os.path.join(APP, "assets", "fa-solid.ttf"),
    ],
}

# Sizes needed per font (from weather_image.py / todoist_image.py)
SIZES = {
    "bold": [24, 26, 28, 32, 36, 40, 72, 88],
    "regular": [16, 18, 20, 22],
    "weather": [34, 52, 54],
    "awesome": [22, 26],
}

# Text characters: ASCII printable + Turkish + degree/bullet/ellipsis/dashes
TEXT_CHARS = (
    "".join(chr(c) for c in range(0x20, 0x7F))
    + "°·…—–"
    + "ğĞüÜşŞıİöÖçÇ"
)

# Icon glyphs (private use area) — only the ones actually drawn
# Same codepoints as WI in the old weather_image.py
WEATHER_GLYPHS = [
    0xF00D,  # sun
    0xF002,  # sun_cloud
    0xF013,  # cloud
    0xF014,  # fog
    0xF009,  # rain_light
    0xF008,  # rain
    0xF010,  # rain_heavy
    0xF00A,  # snow
    0xF0B5,  # sleet
    0xF01E,  # thunder
]
AWESOME_GLYPHS = [
    0xF005,  # star       — priority 1
    0xF071,  # triangle-exclamation — priority 2
    0xF111,  # circle     — priority 3
]


def first_existing(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def render_glyph(font, ch):
    """Render one character to a 1-bit bitmap.

    Returns a dict with w, h, left, top, adv and "bits": base64 of the packed
    bitmap — each row is ceil(w/8) bytes, most significant bit = leftmost pixel.
    (Plain integer bitmasks would overflow JSON's 53-bit number precision for
    the big 72/88 px glyphs.)
    """
    # Measure first; some glyphs have negative bearings.
    bbox = font.getbbox(ch)
    if bbox is None:
        return None
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    advance = font.getlength(ch)
    if w <= 0 or h <= 0:
        # Whitespace: no pixels, but the advance still matters.
        return {"w": 0, "h": 0, "left": 0, "top": 0, "adv": round(advance, 2), "bits": ""}

    img = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(img)
    d.text((-x0, -y0), ch, fill=255, font=font)

    stride = (w + 7) // 8
    packed = bytearray(stride * h)
    px = img.load()
    for y in range(h):
        for x in range(w):
            if px[x, y] >= 128:      # threshold: the Kindle screen is 1-bit anyway
                packed[y * stride + x // 8] |= 0x80 >> (x % 8)

    return {"w": w, "h": h, "left": x0, "top": y0, "adv": round(advance, 2),
            "bits": base64.b64encode(bytes(packed)).decode("ascii")}


def build():
    atlas = {"fonts": {}}
    total = 0

    for name, candidates in FONTS.items():
        path = first_existing(candidates)
        if not path:
            print(f"WARN: font '{name}' not found, skipping", file=sys.stderr)
            continue

        if name in ("weather", "awesome"):
            chars = [chr(c) for c in (WEATHER_GLYPHS if name == "weather" else AWESOME_GLYPHS)]
        else:
            chars = list(TEXT_CHARS)

        for size in SIZES[name]:
            font = ImageFont.truetype(path, size)
            key = f"{name}@{size}"
            glyphs = {}
            for ch in chars:
                g = render_glyph(font, ch)
                if g is not None:
                    glyphs[ch] = g
                    total += 1
            # Ascent/descent let the Worker do baseline and "mm" anchoring.
            ascent, descent = font.getmetrics()
            atlas["fonts"][key] = {"ascent": ascent, "descent": descent, "glyphs": glyphs}
            print(f"  {key}: {len(glyphs)} glyphs")

        print(f"{name}: {path}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(atlas, f, separators=(",", ":"), ensure_ascii=False)

    size_kb = os.path.getsize(OUT) / 1024
    print(f"\nWrote {OUT} — {total} glyphs, {size_kb:.0f} KB")


if __name__ == "__main__":
    build()
