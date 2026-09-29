// The two Kindle screens, drawn onto a 600x800 Canvas.
// Coordinates are copied from the Pi-era weather_image.py / todoist_image.py.
import { Canvas, W, H } from "./canvas.js";

// wttr.in weather code -> icon (same table as WTTR_CODES in weather_image.py)
const WTTR = {
  113: "sun", 116: "sun_cloud", 119: "cloud", 122: "cloud", 143: "fog", 176: "rain_light",
  179: "snow", 182: "sleet", 185: "sleet", 200: "thunder", 227: "snow", 230: "snow", 248: "fog",
  260: "fog", 263: "rain_light", 266: "rain_light", 281: "sleet", 284: "rain", 293: "rain_light",
  296: "rain_light", 299: "rain", 302: "rain", 305: "rain_heavy", 308: "rain_heavy", 311: "sleet",
  314: "sleet", 317: "sleet", 320: "sleet", 323: "snow", 326: "snow", 329: "snow", 332: "snow",
  335: "snow", 338: "snow", 350: "sleet", 353: "rain_light", 356: "rain", 359: "rain_heavy",
  362: "sleet", 365: "sleet", 368: "snow", 371: "snow", 374: "sleet", 386: "thunder",
  389: "thunder", 392: "thunder", 395: "thunder",
};
// Weather Icons font codepoints
const WI = {
  sun: 0xf00d, sun_cloud: 0xf002, cloud: 0xf013, fog: 0xf014, rain_light: 0xf009,
  rain: 0xf008, rain_heavy: 0xf010, snow: 0xf00a, sleet: 0xf0b5, thunder: 0xf01e,
};
const wiGlyph = (code) => String.fromCodePoint(WI[WTTR[code] || "sun"]);

// Todoist priority (UI P1..P3) -> Font Awesome glyph; P4 gets a plain bullet.
const PRIORITY = { 1: 0xf005, 2: 0xf071, 3: 0xf111 };

// Typographic quotes etc. that are not in the atlas.
const clean = (s) =>
  String(s ?? "")
    .replace(/[‘’‚′]/g, "'")
    .replace(/[“”„″]/g, '"')
    .replace(/\s+/g, " ")
    .trim();

// ---- time (the server runs in UTC; the screens show UK local time) ----
const TZ = "Europe/London";
const part = (d, opts) => new Intl.DateTimeFormat("en-GB", { timeZone: TZ, ...opts }).format(d);
export const clock = (d) => part(d, { hour: "2-digit", minute: "2-digit", hour12: false });
const longDate = (d) =>
  `${part(d, { weekday: "long" })}, ${part(d, { day: "2-digit" })} ${part(d, { month: "long" })} ${part(d, { year: "numeric" })}`;
// "2026-09-29" -> "Tuesday"
const weekday = (iso) =>
  new Intl.DateTimeFormat("en-GB", { weekday: "long", timeZone: "UTC" }).format(new Date(`${iso}T12:00:00Z`));

function battery(c, pct, right = W - 8, top = 14) {
  if (pct == null) return;
  const label = `${pct}%`;
  const tw = c.textWidth(label, "regular@16");
  const iw = 22, ih = 12;
  const ix = Math.round(right - tw - 6 - iw);
  c.rect(ix, top, ix + iw, top + ih, { outline: 0 });
  c.rect(ix + iw, top + 3, ix + iw + 2, top + ih - 3, { fill: 0 });
  const fill = Math.floor(((iw - 3) * pct) / 100);
  if (fill > 0) c.rect(ix + 2, top + 2, ix + 2 + fill, top + ih - 2, { fill: 0 });
  c.text(right, top + ih / 2, label, "regular@16", "rm");
}

function raindrop(c, cx, cy, size = 14) {
  const r = Math.floor(size / 2);
  c.ellipse(cx - r, cy, cx + r, cy + 2 * r);
  c.polygon([[cx, cy - size], [cx - r, cy + r], [cx + r, cy + r]]);
}

// One task row: priority icon or bullet, then the title trimmed to fit.
function taskRow(c, t, cy, { margin, iconKey, textKey, textLeft, bullet }) {
  const g = PRIORITY[t.prio];
  if (g) c.text(margin, cy, String.fromCodePoint(g), iconKey, "lm");
  else c.ellipse(margin + bullet[0], cy - bullet[1], margin + bullet[2], cy + bullet[1]);
  c.text(textLeft, cy, c.fit(clean(t.title), textKey, W - textLeft - margin), textKey, "lm");
}

/** Weather + forecast + tides + Todoist (Kindle 1). */
export function renderWeather({ now, weather, tides, todoist, battery: batt, settings }) {
  const c = new Canvas();

  // Header: date, location, battery, refresh time
  c.text(W / 2, 24, longDate(now), "bold@32", "mm");
  c.text(W / 2, 50, clean(settings.location_label), "regular@20", "mm");
  battery(c, batt);
  c.text(W - 20, 50, clock(now), "regular@20", "rm");
  c.sep(62);

  if (!weather) {
    c.text(W / 2, 130, "Weather unavailable", "bold@28", "mm");
  } else {
    // Current conditions
    c.text(150, 108, `${weather.temp}°C`, "bold@72", "mm");
    c.icon(70, 168, wiGlyph(weather.code), "weather@52");
    // The condition sits left of the detail column (which starts near x=260):
    // shrink long ones ("Patchy rain nearby") and trim as a last resort.
    const desc = clean(weather.desc), maxDesc = 250 - 110;
    const descFont = c.textWidth(desc, "bold@24") <= maxDesc ? "bold@24" : "regular@18";
    c.text(110, 168, c.fit(desc, descFont, maxDesc), descFont, "lm");
    const RX = 420;
    c.text(RX, 84, `Feels ${weather.feels}°C`, "bold@24", "mm");
    c.text(RX, 114, `Humidity ${weather.humidity}%`, "bold@24", "mm");
    c.text(RX, 144, `Wind ${weather.windMph} mph ${weather.windDir}`, "bold@24", "mm");
    c.text(RX, 174, `Rise ${weather.sunrise}  Set ${weather.sunset}`, "bold@24", "mm");
  }
  c.sep(200);

  // 3-day forecast
  const FT = 200, colW = Math.floor(W / 3);
  (weather?.days || []).forEach((d, i) => {
    const cx = colW * i + Math.floor(colW / 2);
    c.text(cx, FT + 20, i === 0 ? "Today" : weekday(d.date), "bold@24", "mm");
    c.icon(cx, FT + 54, wiGlyph(d.code), "weather@34");
    c.text(cx, FT + 88, `${d.max}° / ${d.min}°`, "bold@28", "mm");
    // Drop + percentage centred as one group, so 2–3 digit values don't touch the drop.
    const rain = `${d.rain}%`, gap = 8, dropW = 14;
    const gx = cx - (dropW + gap + c.textWidth(rain, "bold@28")) / 2;
    raindrop(c, gx + dropW / 2, FT + 110, 14);
    c.text(gx + dropW + gap, FT + 116, rain, "bold@28", "lm");
    if (i < 2) c.line(colW * (i + 1), FT + 8, colW * (i + 1), FT + 136);
  });
  const FB = FT + 144;
  c.sep(FB);

  // Tides
  const TT = FB;
  c.text(W / 2, TT + 20, clean(settings.tide_label), "bold@28", "mm");
  if (tides?.length) {
    const n = Math.min(tides.length, 4), cw = Math.floor(W / n);
    tides.slice(0, n).forEach((t, i) => {
      const tcx = cw * i + Math.floor(cw / 2);
      c.text(tcx, TT + 46, t.kind === "High" ? "HIGH" : "LOW", "bold@24", "mm");
      c.text(tcx, TT + 74, t.time, "bold@28", "mm");
      c.text(tcx, TT + 98, `${t.height}m`, "regular@20", "mm");
      if (i < n - 1) c.line(cw * (i + 1), TT + 34, cw * (i + 1), TT + 110);
    });
  } else {
    c.text(W / 2, TT + 70, "Tide data unavailable", "regular@20", "mm");
  }
  const TB = TT + 118;
  c.sep(TB);

  // Todoist inbox
  const DT = TB;
  const tasks = todoist || null;
  c.text(W / 2, DT + 22, tasks?.length ? `Inbox — ${tasks.length} pending` : "Inbox", "bold@28", "mm");
  if (tasks?.length) {
    const max = Number(settings.weather_tasks) || 8;
    let ny = DT + 50;
    for (const t of tasks.slice(0, max)) {
      taskRow(c, t, ny + 17, {
        margin: 24, iconKey: "awesome@22", textKey: "bold@24", textLeft: 58, bullet: [4, 3, 10],
      });
      ny += 34;
      if (ny > H - 20) break;
    }
  } else {
    c.text(W / 2, DT + 90, tasks ? "Inbox is empty" : "Todoist unavailable", "regular@20", "mm");
  }
  return c;
}

/** Full-screen Todoist inbox (Kindle 2). */
export function renderTodoist({ now, todoist, battery: batt, settings }) {
  const c = new Canvas();
  const tasks = todoist || null;

  c.text(W / 2, 34, "Todoist Inbox", "bold@40", "mm");
  c.text(W / 2, 68, tasks ? `${tasks.length} pending` : "", "regular@20", "mm");
  c.text(12, 20, clock(now), "regular@22", "lm");
  battery(c, batt);
  c.sep(88);

  if (tasks?.length) {
    const max = Number(settings.todoist_tasks) || 16;
    let ny = 106;
    for (const t of tasks.slice(0, max)) {
      taskRow(c, t, ny + 22, {
        margin: 26, iconKey: "awesome@26", textKey: "bold@26", textLeft: 68, bullet: [6, 4, 14],
      });
      ny += 44;
      if (ny > H - 30) break;
    }
  } else {
    c.text(W / 2, H / 2, tasks ? "Inbox is empty" : "Todoist unavailable", "bold@28", "mm");
  }
  return c;
}
