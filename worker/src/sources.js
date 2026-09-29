// Data sources. Each returns plain JSON that the layouts render.
// Ported from the Pi scripts weather_image.py / todoist_image.py.

const UA = { "User-Agent": "kindle-display/2.0" };

export async function fetchWeather(query) {
  const r = await fetch(`https://wttr.in/${encodeURIComponent(query)}?format=j1`, { headers: UA });
  if (!r.ok) throw new Error(`wttr.in HTTP ${r.status}`);
  const d = await r.json();
  const c = d.current_condition[0];
  const days = d.weather.slice(0, 3);
  return {
    temp: Number(c.temp_C),
    feels: Number(c.FeelsLikeC),
    humidity: Number(c.humidity),
    windMph: Number(c.windspeedMiles),
    windDir: c.winddir16Point,
    code: Number(c.weatherCode),
    desc: c.weatherDesc[0].value,
    sunrise: days[0].astronomy[0].sunrise,
    sunset: days[0].astronomy[0].sunset,
    days: days.map((day) => {
      const noon = day.hourly[4]; // 12:00 slot, as before
      return {
        date: day.date,
        max: Number(day.maxtempC),
        min: Number(day.mintempC),
        rain: Number(noon.chanceofrain),
        code: Number(noon.weatherCode),
      };
    }),
  };
}

const ENTITIES = { "&lt;": "<", "&gt;": ">", "&amp;": "&", "&quot;": '"', "&#39;": "'", "&apos;": "'" };
const unescape = (s) => s.replace(/&(lt|gt|amp|quot|apos|#39);/g, (m) => ENTITIES[m]);

export async function fetchTides(rssUrl) {
  if (!rssUrl) return [];
  const r = await fetch(rssUrl, { headers: UA });
  if (!r.ok) throw new Error(`tides HTTP ${r.status}`);
  const xml = await r.text();
  // The second <description> holds the tide list (the first describes the feed).
  const descs = [...xml.matchAll(/<description>([\s\S]*?)<\/description>/g)].map((m) => m[1]);
  if (descs.length < 2) return [];
  const text = unescape(descs[1]).replace(/<[^>]+>/g, " ");
  return [...text.matchAll(/(High|Low) Tide:\s*(\d{2}:\d{2})\s*\((\d+\.\d+)m\)/g)].map((m) => ({
    kind: m[1],
    time: m[2],
    height: m[3],
  }));
}

export async function fetchTodoist(token) {
  if (!token) throw new Error("TODOIST_TOKEN missing in .dev.vars");
  const headers = { Authorization: `Bearer ${token}` };
  const base = "https://api.todoist.com/api/v1";

  const pr = await fetch(`${base}/projects`, { headers });
  if (!pr.ok) throw new Error(`todoist projects HTTP ${pr.status}`);
  const pd = await pr.json();
  const projects = Array.isArray(pd) ? pd : pd.results || [];
  const inbox = projects.find((p) => p.is_inbox_project || p.name === "Inbox");

  const tasks = [];
  let cursor = null;
  do {
    const url = new URL(`${base}/tasks`);
    if (inbox) url.searchParams.set("project_id", inbox.id);
    url.searchParams.set("limit", "200");
    if (cursor) url.searchParams.set("cursor", cursor);
    const tr = await fetch(url, { headers });
    if (!tr.ok) throw new Error(`todoist tasks HTTP ${tr.status}`);
    const td = await tr.json();
    tasks.push(...(Array.isArray(td) ? td : td.results || []));
    cursor = Array.isArray(td) ? null : td.next_cursor;
  } while (cursor);

  const open = tasks.filter((t) => !t.checked && (!inbox || t.project_id === inbox.id));
  // API priority 4 = UI P1 (highest). Stable sort keeps Todoist's order within a priority.
  open.sort((a, b) => (b.priority || 1) - (a.priority || 1));
  return open.map((t) => ({ title: (t.content || "").trim(), prio: 5 - (t.priority || 1) }));
}
