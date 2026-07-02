#!/usr/bin/env python3
"""
Kindle Display - Weather Image Generator
Renders weather + 3-day forecast + tides + news into a 600x800 B&W PNG for a Kindle 4 NT.
Edit the CONFIG block below for your location and feeds.
"""

import os
import sys
import math
import re
import html
from datetime import datetime

import requests
from PIL import Image, ImageDraw, ImageFont

# ── CONFIG ───────────────────────────────────────────────────────────
# Weather location (used by wttr.in)
LOCATION_QUERY = "Sturry,Canterbury,UK"      # query for wttr.in
LOCATION_LABEL = "Sturry, Canterbury UK"     # printed at the top of the screen

# Tide RSS feed (set to "" to disable the tide section)
TIDE_RSS   = "https://www.tidetimes.co.uk/rss/herne-bay-tide-times"
TIDE_LABEL = "Herne Bay — Tide Times"

# Bottom panel: Todoist Inbox tasks.
# Put your API token (Todoist -> Settings -> Integrations -> Developer) in
# a file named todoist_token.txt next to this script (git-ignored). Leave
# the file absent to disable the panel.
TODOIST_TOKEN_FILE = os.path.join(os.path.dirname(__file__), "todoist_token.txt")
# ─────────────────────────────────────────────────────────────────────

KINDLE_W, KINDLE_H = 600, 800
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "kindle_weather.png")

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
_WEATHER_ICON_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "weathericons.ttf"),
    "/usr/share/fonts/truetype/weathericons.ttf",
]

def _first_existing(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None

FONT_BOLD    = _first_existing(_FONT_BOLD_CANDIDATES)
FONT_MEDIUM  = _first_existing(_FONT_MEDIUM_CANDIDATES)
FONT_WEATHER = _first_existing(_WEATHER_ICON_CANDIDATES)

# Weather Icons Unicode glyphs (erikflowers/weather-icons)
WI = {
    "sun":        "",  # wi-day-sunny
    "sun_cloud":  "",  # wi-day-cloudy
    "cloud":      "",  # wi-cloudy
    "fog":        "",  # wi-fog
    "rain_light": "",  # wi-showers
    "rain":       "",  # wi-rain
    "rain_heavy": "",  # wi-storm-showers
    "snow":       "",  # wi-snow
    "sleet":      "",  # wi-sleet
    "thunder":    "",  # wi-thunderstorm
}

WTTR_CODES = {
    113: ("Sunny",           "sun"),
    116: ("Partly Cloudy",   "sun_cloud"),
    119: ("Cloudy",          "cloud"),
    122: ("Overcast",        "cloud"),
    143: ("Mist",            "fog"),
    176: ("Patchy Rain",     "rain_light"),
    179: ("Patchy Snow",     "snow"),
    182: ("Sleet",           "sleet"),
    185: ("Icy Drizzle",     "sleet"),
    200: ("Thunderstorm",    "thunder"),
    227: ("Blowing Snow",    "snow"),
    230: ("Blizzard",        "snow"),
    248: ("Fog",             "fog"),
    260: ("Icy Fog",         "fog"),
    263: ("Light Drizzle",   "rain_light"),
    266: ("Drizzle",         "rain_light"),
    281: ("Fr. Drizzle",     "sleet"),
    284: ("Heavy Drizzle",   "rain"),
    293: ("Light Rain",      "rain_light"),
    296: ("Light Rain",      "rain_light"),
    299: ("Mod. Rain",       "rain"),
    302: ("Rain",            "rain"),
    305: ("Heavy Rain",      "rain_heavy"),
    308: ("Very Hvy Rain",   "rain_heavy"),
    311: ("Light Sleet",     "sleet"),
    314: ("Mod. Sleet",      "sleet"),
    317: ("Light Sleet",     "sleet"),
    320: ("Mod. Sleet",      "sleet"),
    323: ("Patchy Snow",     "snow"),
    326: ("Light Snow",      "snow"),
    329: ("Patchy Snow",     "snow"),
    332: ("Mod. Snow",       "snow"),
    335: ("Heavy Snow",      "snow"),
    338: ("Heavy Snow",      "snow"),
    350: ("Ice Pellets",     "sleet"),
    353: ("Lt. Showers",     "rain_light"),
    356: ("Showers",         "rain"),
    359: ("Hvy Showers",     "rain_heavy"),
    362: ("Lt. Sleet",       "sleet"),
    365: ("Sleet Showers",   "sleet"),
    368: ("Lt. Snow Shwr",   "snow"),
    371: ("Mod. Snow Shwr",  "snow"),
    374: ("Ice Pellet Shwr", "sleet"),
    386: ("Thundery Rain",   "thunder"),
    389: ("Hvy Thunder",     "thunder"),
    392: ("Thundery Snow",   "thunder"),
    395: ("Hvy Snow Thdr",   "thunder"),
}


def _draw_raindrop(draw, cx, cy, size=14):
    """Su damlası: tepe üçgen + alt yarım daire"""
    r = size // 2
    draw.ellipse([(cx - r, cy), (cx + r, cy + 2*r)], fill=0)
    draw.polygon([(cx, cy - size), (cx - r, cy + r), (cx + r, cy + r)], fill=0)


def draw_icon(draw, icon_type, cx, cy, size=46):
    """Weather Icons TTF ile ikon çiz; font yoksa basit fallback."""
    glyph = WI.get(icon_type)
    if FONT_WEATHER and glyph:
        font = ImageFont.truetype(FONT_WEATHER, size)
        # Glyphin bounding box'ını al, tam ortalanmış şekilde çiz
        bbox = font.getbbox(glyph)
        gw = bbox[2] - bbox[0]
        gh = bbox[3] - bbox[1]
        draw.text((cx - gw//2 - bbox[0], cy - gh//2 - bbox[1]), glyph, fill=0, font=font)
    else:
        # Fallback: basit daire
        r = max(7, size // 4)
        draw.ellipse([(cx-r, cy-r), (cx+r, cy+r)], outline=0, width=2)


def fetch_weather():
    url = f"https://wttr.in/{LOCATION_QUERY}?format=j1"
    r = requests.get(url, timeout=20, headers={"User-Agent": "kindle-display/1.0"})
    r.raise_for_status()
    return r.json()


def fetch_tides():
    """Fetch tide times from a tidetimes.co.uk RSS feed."""
    if not TIDE_RSS:
        return []
    r = requests.get(TIDE_RSS, timeout=15, headers={"User-Agent": "kindle-display/1.0"})
    r.raise_for_status()
    # The second <description> tag holds the tide data
    descs = re.findall(r'<description>(.*?)</description>', r.text, re.DOTALL)
    if len(descs) < 2:
        return []
    text = html.unescape(descs[1])           # &lt; → <
    text = re.sub(r'<[^>]+>', '', text)      # strip HTML tags
    # Format: "Low Tide:05:14 (1.15m)" or "High Tide:11:37 (4.63m)"
    tides = re.findall(r'(High|Low) Tide:\s*(\d{2}:\d{2})\s*\((\d+\.\d+)m\)', text)
    return tides  # [("Low","05:14","1.15"), ("High","11:37","4.63"), ...]


def _todoist_token():
    """todoist_token.txt'den API token'ini okur (yoksa None)."""
    try:
        with open(TODOIST_TOKEN_FILE) as f:
            t = f.read().strip()
            return t or None
    except Exception:
        return None


def fetch_todoist_inbox():
    """Todoist Inbox'taki bekleyen gorevleri ceker.
    Doner: (toplam_sayi, [ilk birkac gorev basligi])"""
    token = _todoist_token()
    if not token:
        return (0, [])
    hdr = {"Authorization": f"Bearer {token}"}
    base = "https://api.todoist.com/api/v1"
    # Inbox project_id'yi bul
    pr = requests.get(f"{base}/projects", headers=hdr, timeout=12)
    pr.raise_for_status()
    pdata = pr.json()
    projs = pdata.get("results", pdata) if isinstance(pdata, dict) else pdata
    inbox_id = next((p["id"] for p in projs
                     if p.get("is_inbox_project") or p.get("name") == "Inbox"), None)
    # Gorevleri cek
    tr = requests.get(f"{base}/tasks", headers=hdr, timeout=12)
    tr.raise_for_status()
    tdata = tr.json()
    tasks = tdata.get("results", []) if isinstance(tdata, dict) else tdata
    inbox = [t for t in tasks
             if t.get("project_id") == inbox_id and not t.get("checked")]
    titles = [t.get("content", "").strip() for t in inbox]
    return (len(inbox), titles)


def load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def wrap_text(draw, text, font, max_width):
    """Metni max genislige gore satirlara boler."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def sep(draw, y, margin=20, thickness=2):
    draw.line([(margin, y), (KINDLE_W-margin, y)], fill=0, width=thickness)


def read_battery():
    """serve_image.py'nin yazdigi battery.txt'den pil yuzdesini okur."""
    try:
        with open(os.path.join(os.path.dirname(__file__), "battery.txt")) as f:
            v = int(f.read().strip())
            if 0 < v <= 100:
                return v
    except Exception:
        pass
    return None


def generate_image(data, tides=None, todoist=None):
    img  = Image.new("L", (KINDLE_W, KINDLE_H), color=255)
    draw = ImageDraw.Draw(img)

    now     = datetime.now()
    current = data["current_condition"][0]
    weather = data["weather"]

    fb_32  = load_font(FONT_BOLD,   32)
    fb_28  = load_font(FONT_BOLD,   28)
    fb_24  = load_font(FONT_BOLD,   24)
    fm_22  = load_font(FONT_MEDIUM, 22)
    fm_20  = load_font(FONT_MEDIUM, 20)
    fm_18  = load_font(FONT_MEDIUM, 18)
    fb_88  = load_font(FONT_BOLD,   88)

    # ── HEADER ───────────────────────────────────────────────────
    # Ust: tarih (buyuk bold), alt: konum (kucuk)
    draw.text((KINDLE_W//2, 24), now.strftime("%A, %d %B %Y"),
              fill=0, font=fb_32, anchor="mm")
    draw.text((KINDLE_W//2, 50), LOCATION_LABEL,
              fill=0, font=fm_20, anchor="mm")

    # Pil gostergesi — sag ust kose (kucuk pil ikonu + yuzde)
    batt = read_battery()
    if batt is not None:
        fm_16 = load_font(FONT_MEDIUM, 16)
        bt = f"{batt}%"
        # Metin sag kenara hizali
        tb = draw.textbbox((0, 0), bt, font=fm_16)
        tw = tb[2] - tb[0]
        bx_right = KINDLE_W - 8
        by = 14   # ust kenardan ~14px (2px asagi ayari icin buradan oynanir)
        # Pil ikonu (govde + uc)
        ico_w, ico_h = 22, 12
        ix = bx_right - tw - 6 - ico_w
        iy = by
        draw.rectangle([(ix, iy), (ix + ico_w, iy + ico_h)], outline=0, width=1)
        draw.rectangle([(ix + ico_w, iy + 3), (ix + ico_w + 2, iy + ico_h - 3)], fill=0)
        # Doluluk cubugu
        fill_w = int((ico_w - 3) * batt / 100.0)
        if fill_w > 0:
            draw.rectangle([(ix + 2, iy + 2), (ix + 2 + fill_w, iy + ico_h - 2)], fill=0)
        # Yuzde metni ikonun sagina
        draw.text((bx_right, by + ico_h // 2), bt, fill=0, font=fm_16, anchor="rm")

    # Refresh saati — konum yazisi ile ayni yatay hizada (y=50), ayni font, sag kose
    draw.text((KINDLE_W - 20, 50), now.strftime("%H:%M"),
              fill=0, font=fm_20, anchor="rm")

    sep(draw, 62)

    # ── CURRENT ──────────────────────────────────────────────────
    temp_c   = int(current["temp_C"])
    feels_c  = int(current["FeelsLikeC"])
    humidity = int(current["humidity"])
    wind_mph = int(current["windspeedMiles"])
    wind_dir = current["winddir16Point"]
    pressure = int(current["pressure"])
    wcode    = int(current["weatherCode"])
    desc     = current["weatherDesc"][0]["value"]
    t_max    = weather[0]["maxtempC"]
    t_min    = weather[0]["mintempC"]
    t_rain   = weather[0]["hourly"][4]["chanceofrain"]
    sunrise  = weather[0]["astronomy"][0]["sunrise"]
    sunset   = weather[0]["astronomy"][0]["sunset"]
    icon_t   = WTTR_CODES.get(wcode, ("?","sun"))[1]

    # Layout: sol %45 = sıcaklık+ikon+hi/lo, sağ %55 = detaylar
    LEFT_CX  = 150
    RIGHT_CX = 420

    fb_72 = load_font(FONT_BOLD, 72)
    fb_36 = load_font(FONT_BOLD, 36)

    # Büyük sıcaklık
    draw.text((LEFT_CX, 108), f"{temp_c}°C", fill=0, font=fb_72, anchor="mm")

    # İkon + hava durumu aciklamasi (Clear vb.) — sicakligin altinda yan yana
    draw_icon(draw, icon_t, 70, 168, size=52)
    draw.text((110, 168), desc, fill=0, font=fb_24, anchor="lm")

    # Sağ kolon — detaylar, hepsi bold ve büyük
    draw.text((RIGHT_CX,  84), f"Feels {feels_c}°C",               fill=0, font=fb_24, anchor="mm")
    draw.text((RIGHT_CX, 114), f"Humidity {humidity}%",             fill=0, font=fb_24, anchor="mm")
    draw.text((RIGHT_CX, 144), f"Wind {wind_mph} mph {wind_dir}",   fill=0, font=fb_24, anchor="mm")
    draw.text((RIGHT_CX, 174), f"Rise {sunrise}  Set {sunset}",     fill=0, font=fb_24, anchor="mm")

    sep(draw, 200)

    # ── 3-DAY FORECAST ───────────────────────────────────────────
    FORE_TOP = 200

    col_w3 = KINDLE_W // 3
    # Gun adlari: ilk sutun "Today", sonrakiler gercek gun adi (tekrar olmasin)
    dy_names = []
    for i, day in enumerate(weather[:3]):
        if i == 0:
            dy_names.append("Today")
        else:
            try:
                dy_names.append(datetime.strptime(day["date"], "%Y-%m-%d").strftime("%A"))
            except Exception:
                dy_names.append("")

    for i, day in enumerate(weather[:3]):
        cx      = col_w3 * i + col_w3 // 2
        d_max   = day["maxtempC"]
        d_min   = day["mintempC"]
        d_rain  = day["hourly"][4]["chanceofrain"]
        d_code  = int(day["hourly"][4]["weatherCode"])
        d_itype = WTTR_CODES.get(d_code, ("?","sun"))[1]
        d_desc  = day["hourly"][4]["weatherDesc"][0]["value"]

        # Gün adı
        draw.text((cx, FORE_TOP + 20), dy_names[i], fill=0, font=fb_24, anchor="mm")
        # İkon (desc satiri kaldirildi, ikon yeterli)
        draw_icon(draw, d_itype, cx, FORE_TOP + 54, size=34)
        # Sıcaklık — büyük bold tek satır
        draw.text((cx, FORE_TOP + 88), f"{d_max}° / {d_min}°", fill=0, font=fb_28, anchor="mm")
        # Yağmur — küçük damla + büyük bold yazı
        drop_x = cx - 30
        drop_y = FORE_TOP + 116
        _draw_raindrop(draw, drop_x, drop_y, size=14)
        draw.text((cx + 10, FORE_TOP + 116), f"{d_rain}%", fill=0, font=fb_28, anchor="mm")

        if i < 2:
            draw.line([(col_w3*(i+1), FORE_TOP + 8),(col_w3*(i+1), FORE_TOP + 136)],
                      fill=0, width=1)

    FORE_BOT = FORE_TOP + 144
    sep(draw, FORE_BOT)

    # ── TIDE TIMES ───────────────────────────────────────────────
    TIDE_TOP = FORE_BOT
    draw.text((KINDLE_W//2, TIDE_TOP + 20), TIDE_LABEL,
              fill=0, font=fb_28, anchor="mm")

    if tides:
        # Maksimum 4 gelgit göster, eşit aralıklı sütunlar (oksuz, kompakt)
        n = min(len(tides), 4)
        col_w = KINDLE_W // n
        for i, (hilo, t, h) in enumerate(tides[:n]):
            tcx = col_w * i + col_w // 2
            label = "HIGH" if hilo == "High" else "LOW"
            draw.text((tcx, TIDE_TOP + 46), label, fill=0, font=fb_24, anchor="mm")
            draw.text((tcx, TIDE_TOP + 74), t,     fill=0, font=fb_28, anchor="mm")
            draw.text((tcx, TIDE_TOP + 98), f"{h}m", fill=0, font=fm_20, anchor="mm")
            if i < n - 1:
                draw.line([(col_w*(i+1), TIDE_TOP+34), (col_w*(i+1), TIDE_TOP+110)],
                          fill=0, width=1)
    else:
        draw.text((KINDLE_W//2, TIDE_TOP + 70), "Tide data unavailable",
                  fill=100, font=fm_20, anchor="mm")

    TIDE_BOT = TIDE_TOP + 118
    sep(draw, TIDE_BOT)

    # ── TODOIST INBOX (alt bosluk) ───────────────────────────────
    TODO_TOP = TIDE_BOT
    margin   = 24
    total, titles = todoist if todoist else (0, [])

    # Baslik: "Todoist Inbox — N pending"
    if total > 0:
        head = f"Inbox — {total} pending"
    else:
        head = "Inbox"
    draw.text((KINDLE_W//2, TODO_TOP + 22), head, fill=0, font=fb_28, anchor="mm")

    if titles:
        ny = TODO_TOP + 50
        for idx, task in enumerate(titles[:5]):
            # Onay kutusu (bos)
            box = 26
            by0 = ny
            draw.rectangle([(margin, by0), (margin + box, by0 + box)], outline=0, width=2)
            # Gorev basligi — bold, tek satira sigacak sekilde kirp
            text_left = margin + box + 14
            avail = KINDLE_W - text_left - margin
            line = task
            while draw.textbbox((0, 0), line, font=fb_24)[2] > avail and len(line) > 4:
                line = line[:-2]
            if line != task:
                line = line.rstrip() + "…"
            draw.text((text_left, by0 + box // 2), line, fill=0, font=fb_24, anchor="lm")
            ny += box + 14
            if ny > KINDLE_H - 30:
                break
    elif total == 0:
        draw.text((KINDLE_W//2, TODO_TOP + 90), "Inbox is empty",
                  fill=100, font=fm_20, anchor="mm")
    else:
        draw.text((KINDLE_W//2, TODO_TOP + 90), "Todoist unavailable",
                  fill=100, font=fm_20, anchor="mm")

    img_bw = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG).convert("L")
    img_bw.save(OUTPUT_PATH)
    print(f"Saved: {OUTPUT_PATH}")
    return OUTPUT_PATH


def main():
    print(f"Fetching weather for {LOCATION_LABEL}...")
    try:
        data = fetch_weather()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    print("Fetching tide times...")
    tides = []
    try:
        tides = fetch_tides()
        print(f"Tides: {tides}")
    except Exception as e:
        print(f"Tide fetch failed (non-fatal): {e}", file=sys.stderr)
    print("Fetching Todoist Inbox...")
    todoist = (0, [])
    try:
        todoist = fetch_todoist_inbox()
        print(f"Inbox: {todoist[0]} pending")
        for t in todoist[1][:4]:
            print(" -", t)
    except Exception as e:
        print(f"Todoist fetch failed (non-fatal): {e}", file=sys.stderr)
    generate_image(data, tides, todoist)


if __name__ == "__main__":
    main()
