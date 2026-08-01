#!/usr/bin/env python3
"""
Kindle Display - Todoist-only Image Generator
Renders the full Todoist Inbox (task count + task list with checkboxes)
into a 600x800 B&W PNG for a second Kindle 4 NT.
Shares todoist_token.txt with weather_image.py.
"""

import os
import sys
from datetime import datetime

import requests
from PIL import Image, ImageDraw, ImageFont

# ── CONFIG ───────────────────────────────────────────────────────────
TODOIST_TOKEN_FILE = os.path.join(os.path.dirname(__file__), "todoist_token.txt")
MAX_TASKS = 16   # kac gorev gosterilsin (tum ekran)
# ─────────────────────────────────────────────────────────────────────

KINDLE_W, KINDLE_H = 600, 800
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "kindle_todoist.png")

_FONT_BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]
_FONT_MEDIUM_CANDIDATES = [
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
]
_FONT_AWESOME_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "fa-solid.ttf"),
    "/usr/share/fonts/truetype/fa-solid.ttf",
]

def _first_existing(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None

FONT_BOLD    = _first_existing(_FONT_BOLD_CANDIDATES)
FONT_MEDIUM  = _first_existing(_FONT_MEDIUM_CANDIDATES)
FONT_AWESOME = _first_existing(_FONT_AWESOME_CANDIDATES)

# Priority ikonlari (Font Awesome Solid glyph'leri), UI priority'ye gore
# UI P1=en yuksek/acil, P4=varsayilan
PRIORITY_ICONS = {
    1: chr(0xF005),  # star — en yuksek (acil)
    2: chr(0xF071),  # triangle-exclamation — yuksek
    3: chr(0xF111),  # circle — orta
    # 4: ikon yok (varsayilan)
}


def load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def sep(draw, y, margin=20, thickness=2):
    draw.line([(margin, y), (KINDLE_W-margin, y)], fill=0, width=thickness)


def _todoist_token():
    try:
        with open(TODOIST_TOKEN_FILE) as f:
            t = f.read().strip()
            return t or None
    except Exception:
        return None


def read_battery():
    """battery_todoist.txt'den pil yuzdesini okur (serve_image.py yazar)."""
    try:
        with open(os.path.join(os.path.dirname(__file__), "battery_todoist.txt")) as f:
            v = int(f.read().strip())
            if 0 < v <= 100:
                return v
    except Exception:
        pass
    return None


def fetch_todoist_inbox():
    """Todoist Inbox'taki bekleyen gorevleri ceker.
    Doner: (toplam_sayi, [gorev basliklari])"""
    token = _todoist_token()
    if not token:
        return (0, [])
    hdr = {"Authorization": f"Bearer {token}"}
    base = "https://api.todoist.com/api/v1"
    pr = requests.get(f"{base}/projects", headers=hdr, timeout=12)
    pr.raise_for_status()
    pdata = pr.json()
    projs = pdata.get("results", pdata) if isinstance(pdata, dict) else pdata
    inbox_id = next((p["id"] for p in projs
                     if p.get("is_inbox_project") or p.get("name") == "Inbox"), None)
    tr = requests.get(f"{base}/tasks", headers=hdr, timeout=12)
    tr.raise_for_status()
    tdata = tr.json()
    tasks = tdata.get("results", []) if isinstance(tdata, dict) else tdata
    inbox = [t for t in tasks
             if t.get("project_id") == inbox_id and not t.get("checked")]
    # Oncelige gore sirala: API priority 4=en yuksek (UI P1) once gelsin
    inbox.sort(key=lambda t: -t.get("priority", 1))
    # (baslik, ui_priority) dondur. API 4->UI 1, API 3->UI 2, API 2->UI 3, API 1->UI 4
    items = [(t.get("content", "").strip(), 5 - t.get("priority", 1)) for t in inbox]
    return (len(inbox), items)


def generate_image(total, titles):
    img  = Image.new("L", (KINDLE_W, KINDLE_H), color=255)
    draw = ImageDraw.Draw(img)
    now  = datetime.now()

    fb_40 = load_font(FONT_BOLD, 40)
    fb_28 = load_font(FONT_BOLD, 28)
    fb_26 = load_font(FONT_BOLD, 26)
    fm_20 = load_font(FONT_MEDIUM, 20)

    # ── HEADER ───────────────────────────────────────────────────
    draw.text((KINDLE_W//2, 34), "Todoist Inbox", fill=0, font=fb_40, anchor="mm")
    sub = f"{total} pending" if total != 1 else "1 pending"
    draw.text((KINDLE_W//2, 68), sub, fill=0, font=fm_20, anchor="mm")

    # Sol ust: uretim zamani (guncel mi anlamak icin)
    fm_16 = load_font(FONT_MEDIUM, 16)
    fm_22 = load_font(FONT_MEDIUM, 22)
    draw.text((12, 20), now.strftime("%H:%M"), fill=0, font=fm_22, anchor="lm")

    # Sag ust: pil gostergesi (ikon + %)
    batt = read_battery()
    if batt is not None:
        bt = f"{batt}%"
        tb = draw.textbbox((0, 0), bt, font=fm_16)
        tw = tb[2] - tb[0]
        bx_right = KINDLE_W - 8
        by = 14
        ico_w, ico_h = 22, 12
        ix = bx_right - tw - 6 - ico_w
        iy = by
        draw.rectangle([(ix, iy), (ix + ico_w, iy + ico_h)], outline=0, width=1)
        draw.rectangle([(ix + ico_w, iy + 3), (ix + ico_w + 2, iy + ico_h - 3)], fill=0)
        fill_w = int((ico_w - 3) * batt / 100.0)
        if fill_w > 0:
            draw.rectangle([(ix + 2, iy + 2), (ix + 2 + fill_w, iy + ico_h - 2)], fill=0)
        draw.text((bx_right, by + ico_h // 2), bt, fill=0, font=fm_16, anchor="rm")

    sep(draw, 88)

    margin = 26
    if titles:
        ny = 106
        row_h = 44
        fa_icon = load_font(FONT_AWESOME, 26) if FONT_AWESOME else None
        for item in titles[:MAX_TASKS]:
            task, prio = item if isinstance(item, tuple) else (item, 4)
            cy = ny + row_h // 2
            # Priority ikonu (checkbox yok — app'ten isaretlenince listeden duser)
            glyph = PRIORITY_ICONS.get(prio)
            if glyph and fa_icon:
                draw.text((margin, cy), glyph, fill=0, font=fa_icon, anchor="lm")
            else:
                draw.ellipse([(margin+6, cy-4), (margin+14, cy+4)], fill=0)
            # Gorev basligi — tek satira sigacak sekilde kirp
            text_left = margin + 42
            avail = KINDLE_W - text_left - margin
            line = task
            while draw.textbbox((0, 0), line, font=fb_26)[2] > avail and len(line) > 4:
                line = line[:-2]
            if line != task:
                line = line.rstrip() + "…"
            draw.text((text_left, cy), line, fill=0, font=fb_26, anchor="lm")
            ny += row_h
            if ny > KINDLE_H - 30:
                break
    elif total == 0:
        draw.text((KINDLE_W//2, KINDLE_H//2), "Inbox is empty",
                  fill=100, font=fb_28, anchor="mm")
    else:
        draw.text((KINDLE_W//2, KINDLE_H//2), "Todoist unavailable",
                  fill=100, font=fb_28, anchor="mm")

    img_bw = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG).convert("L")
    # Gece modu: weather_image.py'nin yazdigi night.flag'i oku
    if _is_night():
        from PIL import ImageOps
        img_bw = ImageOps.invert(img_bw)
        print("Night mode: inverted")
    img_bw.save(OUTPUT_PATH)
    print(f"Saved: {OUTPUT_PATH}")
    return OUTPUT_PATH


def _is_night():
    try:
        with open(os.path.join(os.path.dirname(__file__), "night.flag")) as f:
            return f.read().strip() == "1"
    except Exception:
        return False


def main():
    print("Fetching Todoist Inbox...")
    total, titles = 0, []
    try:
        total, titles = fetch_todoist_inbox()
        print(f"Inbox: {total} pending")
    except Exception as e:
        print(f"Todoist fetch failed: {e}", file=sys.stderr)
    generate_image(total, titles)


if __name__ == "__main__":
    main()
