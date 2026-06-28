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

# News RSS feed
BBC_RSS = "https://feeds.bbci.co.uk/news/rss.xml"
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


def fetch_top_news(count=2):
    """BBC News RSS'den en son haber basliklarini ceker."""
    r = requests.get(BBC_RSS, timeout=12, headers={"User-Agent": "kindle-display/1.0"})
    r.raise_for_status()
    items = re.findall(r'<item>(.*?)</item>', r.text, re.DOTALL)
    out = []
    for it in items:
        tm = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', it, re.DOTALL)
        if tm:
            out.append(html.unescape(tm.group(1).strip()))
        if len(out) >= count:
            break
    return out


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


def generate_image(data, tides=None, news=None):
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
    draw.text((KINDLE_W//2, 24), LOCATION_LABEL, fill=0, font=fb_32, anchor="mm")
    draw.text((KINDLE_W//2, 50), now.strftime("%A, %d %B %Y  %H:%M"),
              fill=0, font=fm_20, anchor="mm")
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
    sunrise  = weather[0]["astronomy"][0]["sunrise"]
    sunset   = weather[0]["astronomy"][0]["sunset"]
    icon_t   = WTTR_CODES.get(wcode, ("?","sun"))[1]

    # Layout: sol %45 = sıcaklık+ikon+hi/lo, sağ %55 = detaylar
    LEFT_CX  = 150
    RIGHT_CX = 420

    fb_72 = load_font(FONT_BOLD, 72)
    fb_36 = load_font(FONT_BOLD, 36)

    # Büyük sıcaklık
    draw.text((LEFT_CX, 112), f"{temp_c}°C", fill=0, font=fb_72, anchor="mm")

    # İkon — sıcaklığın altında, büyük
    draw_icon(draw, icon_t, 72, 174, size=54)

    # Hi / Lo — ikonun sağında
    draw.text((168, 158), f"{t_max}°", fill=0, font=fb_36, anchor="mm")
    draw.text((168, 196), f"{t_min}°", fill=0, font=fb_36, anchor="mm")

    # Sağ kolon — detaylar, hepsi bold ve büyük
    desc_font = fb_24 if len(desc) > 14 else fb_28
    draw.text((RIGHT_CX,  77), desc,                               fill=0, font=desc_font, anchor="mm")
    draw.text((RIGHT_CX, 104), f"Feels {feels_c}°C",               fill=0, font=fb_24, anchor="mm")
    draw.text((RIGHT_CX, 132), f"Humidity {humidity}%",             fill=0, font=fb_24, anchor="mm")
    draw.text((RIGHT_CX, 160), f"Wind {wind_mph} mph {wind_dir}",   fill=0, font=fb_24, anchor="mm")
    draw.text((RIGHT_CX, 188), f"Rise {sunrise}  Set {sunset}",     fill=0, font=fm_20, anchor="mm")
    draw.text((RIGHT_CX, 212), f"Pressure {pressure} hPa",          fill=0, font=fm_20, anchor="mm")

    sep(draw, 228)

    # ── 3-DAY FORECAST ───────────────────────────────────────────
    FORE_TOP = 228

    col_w3 = KINDLE_W // 3
    try:
        d2 = datetime.strptime(weather[2]["date"], "%Y-%m-%d").strftime("%A")
    except Exception:
        d2 = "Day 3"
    dy_names = ["Today", "Tomorrow", d2]

    for i, day in enumerate(weather[:3]):
        cx      = col_w3 * i + col_w3 // 2
        d_max   = day["maxtempC"]
        d_min   = day["mintempC"]
        d_rain  = day["hourly"][4]["chanceofrain"]
        d_code  = int(day["hourly"][4]["weatherCode"])
        d_itype = WTTR_CODES.get(d_code, ("?","sun"))[1]
        d_desc  = day["hourly"][4]["weatherDesc"][0]["value"]

        # Gün adı
        draw.text((cx, FORE_TOP + 22), dy_names[i], fill=0, font=fb_24, anchor="mm")
        # İkon
        draw_icon(draw, d_itype, cx, FORE_TOP + 58, size=34)
        # Açıklama — büyük bold
        d_desc_font = fm_18 if len(d_desc) > 12 else fb_24
        draw.text((cx, FORE_TOP + 92), d_desc, fill=0, font=d_desc_font, anchor="mm")
        # Sıcaklık — büyük bold tek satır
        draw.text((cx, FORE_TOP + 122), f"{d_max}° / {d_min}°", fill=0, font=fb_28, anchor="mm")
        # Yağmur — küçük damla + büyük bold yazı
        drop_size = 14
        drop_x = cx - 30
        drop_y = FORE_TOP + 150
        _draw_raindrop(draw, drop_x, drop_y, size=drop_size)
        draw.text((cx + 10, FORE_TOP + 150), f"{d_rain}%", fill=0, font=fb_28, anchor="mm")

        if i < 2:
            draw.line([(col_w3*(i+1), FORE_TOP + 10),(col_w3*(i+1), FORE_TOP + 172)],
                      fill=0, width=1)

    FORE_BOT = FORE_TOP + 180
    sep(draw, FORE_BOT)

    # ── TIDE TIMES ───────────────────────────────────────────────
    TIDE_TOP = FORE_BOT
    draw.text((KINDLE_W//2, TIDE_TOP + 20), TIDE_LABEL,
              fill=0, font=fb_28, anchor="mm")

    if tides:
        # Maksimum 4 gelgit göster, eşit aralıklı sütunlar
        n = min(len(tides), 4)
        col_w = KINDLE_W // n
        for i, (hilo, t, h) in enumerate(tides[:n]):
            tcx = col_w * i + col_w // 2
            label = "HIGH" if hilo == "High" else "LOW"
            label_font = fb_24
            # Dalga ikonu: HIGH için yukarı üçgen, LOW için aşağı üçgen
            arrow_y = TIDE_TOP + 56
            aw = 20
            if hilo == "High":
                draw.polygon([(tcx, arrow_y - aw), (tcx - aw, arrow_y + aw//2),
                               (tcx + aw, arrow_y + aw//2)], fill=0)
            else:
                draw.polygon([(tcx, arrow_y + aw), (tcx - aw, arrow_y - aw//2),
                               (tcx + aw, arrow_y - aw//2)], fill=0)
            draw.text((tcx, TIDE_TOP + 90), label, fill=0, font=label_font, anchor="mm")
            draw.text((tcx, TIDE_TOP + 118), t, fill=0, font=fb_28, anchor="mm")
            draw.text((tcx, TIDE_TOP + 144), f"{h}m", fill=0, font=fm_22, anchor="mm")
            if i < n - 1:
                draw.line([(col_w*(i+1), TIDE_TOP+44), (col_w*(i+1), TIDE_TOP+160)],
                          fill=0, width=1)
    else:
        draw.text((KINDLE_W//2, TIDE_TOP + 100), "Tide data unavailable",
                  fill=100, font=fm_20, anchor="mm")

    TIDE_BOT = TIDE_TOP + 170
    sep(draw, TIDE_BOT)

    # ── BREAKING NEWS (alt bosluk) ───────────────────────────────
    NEWS_TOP = TIDE_BOT
    margin   = 24
    # Baslik satiri: ikon + "BBC NEWS"
    draw.text((KINDLE_W//2, NEWS_TOP + 22), "BBC NEWS", fill=0, font=fb_28, anchor="mm")

    if news:
        ny = NEWS_TOP + 50
        max_w = KINDLE_W - 2 * margin - 40
        for idx, headline in enumerate(news[:2]):
            # Numara dairesi
            draw.ellipse([(margin, ny), (margin + 34, ny + 34)], fill=0)
            draw.text((margin + 17, ny + 17), str(idx+1), fill=255, font=fm_22, anchor="mm")
            # Baslik — bold, sarmali (max 2 satir)
            text_left = margin + 48
            lines = wrap_text(draw, headline, fb_24, KINDLE_W - text_left - margin)
            ty = ny + 2
            for line in lines[:2]:
                draw.text((text_left, ty), line, fill=0, font=fb_24, anchor="lm")
                ty += 30
            ny = ty + 14
            if ny > KINDLE_H - 30:
                break
    else:
        draw.text((KINDLE_W//2, NEWS_TOP + 80), "News unavailable",
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
    print("Fetching BBC News...")
    news = []
    try:
        news = fetch_top_news(2)
        for h in news:
            print(" -", h)
    except Exception as e:
        print(f"News fetch failed (non-fatal): {e}", file=sys.stderr)
    generate_image(data, tides, news)


if __name__ == "__main__":
    main()
