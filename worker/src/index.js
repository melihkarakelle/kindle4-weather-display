// Kindle Display — renders the e-ink screens for two jailbroken Kindle 4 NTs
// and provides an admin page. Replaces the Raspberry Pi scripts.
//
// Kindle endpoints (the daemons call these over the LAN):
//   GET weather.png?batt=NN   Kindle 1 screen
//   GET todoist.png?batt=NN   Kindle 2 screen
//   GET cmd.sh?dev=<id>       remote shell command for that device
import page from "./page.html";
import daemonTemplate from "./kindle_daemon.sh";
import { encodePng } from "./png.js";
import { renderWeather, renderTodoist } from "./layouts.js";
import { fetchWeather, fetchTides, fetchTodoist } from "./sources.js";

const DEVICES = { "weather.png": "weather", "todoist.png": "todoist" };
const STALE_AFTER = 30 * 60; // data older than this is refreshed on demand

const now = () => Math.floor(Date.now() / 1000);
const json = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json; charset=utf-8" } });

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/^\/+/, "");
    const method = request.method;

    if (method === "GET" && (path === "" || path === "index.html")) {
      return new Response(page, { headers: { "content-type": "text/html; charset=utf-8" } });
    }

    if (method === "GET" && DEVICES[path]) return screen(DEVICES[path], request, url, env, ctx);

    if (method === "GET" && path === "cmd.sh") {
      const dev = url.searchParams.get("dev");
      const row = dev && (await env.DB.prepare("SELECT cmd FROM devices WHERE id = ?").bind(dev).first());
      if (!row) return new Response("", { status: 404 });
      await env.DB.prepare("UPDATE devices SET cmd_fetched = ? WHERE id = ?").bind(now(), dev).run();
      return new Response(row.cmd, { headers: { "content-type": "text/plain; charset=utf-8" } });
    }

    // The Kindle daemon itself, filled in for one device. Used by the
    // "update daemon" remote command so the Kindles can be upgraded in place.
    if (method === "GET" && path === "daemon.sh") {
      const dev = url.searchParams.get("dev");
      if (!Object.values(DEVICES).includes(dev)) return new Response("", { status: 404 });
      // The Kindle fetches this over the LAN, so the address it used is the one to bake in.
      const host = request.headers.get("x-forwarded-host") || request.headers.get("host") || url.host;
      const server = `http://${host}${request.headers.get("x-forwarded-prefix") || ""}`;
      return new Response(daemonTemplate.replaceAll("__DEV__", dev).replaceAll("__SERVER__", server), {
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }

    // A remote command reports back with: wget -q -O /dev/null "$SERVER/report?dev=$DEV&msg=..."
    // (BusyBox wget cannot POST, so it is a GET with the text in the query.)
    if (method === "GET" && path === "report") {
      const dev = url.searchParams.get("dev");
      const msg = (url.searchParams.get("msg") || "").slice(0, 2000);
      const r = await env.DB.prepare("UPDATE devices SET report = ?, report_ts = ? WHERE id = ?").bind(msg, now(), dev).run();
      return new Response(r.meta.changes ? "ok\n" : "unknown device\n", { status: r.meta.changes ? 200 : 404 });
    }

    if (method === "GET" && path === "api/status") return json(await status(env));
    if (method === "POST" && path === "api/settings") return saveSettings(request, env);
    if (method === "POST" && path === "api/cmd") return saveCmd(request, env);
    if (method === "POST" && path === "api/refresh") return json(await refresh(env, true));

    return json({ error: "not found" }, 404);
  },

  async scheduled(event, env, ctx) {
    ctx.waitUntil(refresh(env, false));
  },
};

// ---- data ----

async function getSettings(env) {
  const { results } = await env.DB.prepare("SELECT key, value FROM settings").all();
  return Object.fromEntries(results.map((r) => [r.key, r.value]));
}

async function getCache(env) {
  const { results } = await env.DB.prepare("SELECT * FROM cache").all();
  const out = {};
  for (const r of results) out[r.source] = { ts: r.ts, error: r.error, data: r.data ? JSON.parse(r.data) : null };
  return out;
}

// Fetch every source; keep the previous data when one fails so the screen
// shows the last good values rather than going blank.
async function refresh(env, force) {
  const s = await getSettings(env);
  const cache = await getCache(env);
  const jobs = {
    weather: () => fetchWeather(s.location_query),
    tides: () => fetchTides(s.tide_rss),
    todoist: () => fetchTodoist(env.TODOIST_TOKEN),
  };
  const report = {};
  await Promise.all(
    Object.entries(jobs).map(async ([source, job]) => {
      try {
        const data = await job();
        await env.DB.prepare(
          "INSERT INTO cache (source, ts, data, error) VALUES (?1, ?2, ?3, NULL) " +
            "ON CONFLICT(source) DO UPDATE SET ts = ?2, data = ?3, error = NULL"
        )
          .bind(source, now(), JSON.stringify(data))
          .run();
        report[source] = "ok";
      } catch (e) {
        await env.DB.prepare(
          "INSERT INTO cache (source, ts, data, error) VALUES (?1, ?2, NULL, ?3) " +
            "ON CONFLICT(source) DO UPDATE SET error = ?3"
        )
          .bind(source, cache[source]?.ts || 0, String(e.message || e))
          .run();
        report[source] = String(e.message || e);
      }
    })
  );
  return { force, report };
}

// ---- Kindle screens ----

async function screen(dev, request, url, env, ctx) {
  let cache = await getCache(env);
  const oldest = Math.min(...["weather", "tides", "todoist"].map((k) => cache[k]?.ts || 0));
  if (now() - oldest > STALE_AFTER) {
    await refresh(env, false); // first run or the cron has stalled
    cache = await getCache(env);
  }

  const dbDev = await env.DB.prepare("SELECT * FROM devices WHERE id = ?").bind(dev).first();
  let battery = dbDev?.battery ?? null;

  // A real device fetch carries ?batt=; the admin preview does not.
  const b = url.searchParams.get("batt");
  if (b !== null && /^\d{1,3}$/.test(b)) {
    battery = Math.min(Number(b), 100);
    const ip = request.headers.get("x-forwarded-for")?.split(",")[0].trim() || "";
    await env.DB.batch([
      env.DB.prepare("UPDATE devices SET last_seen = ?, battery = ?, ip = ? WHERE id = ?").bind(now(), battery, ip, dev),
      env.DB.prepare("INSERT INTO fetch_log (ts, device, battery, ip) VALUES (?, ?, ?, ?)").bind(now(), dev, battery, ip),
      env.DB.prepare("DELETE FROM fetch_log WHERE ts < ?").bind(now() - 7 * 86400),
    ]);
  }

  const args = {
    now: new Date(),
    settings: await getSettings(env),
    weather: cache.weather?.data,
    tides: cache.tides?.data,
    todoist: cache.todoist?.data,
    battery,
  };
  const canvas = dev === "weather" ? renderWeather(args) : renderTodoist(args);
  const png = await encodePng(canvas.px, canvas.w, canvas.h);
  return new Response(png, { headers: { "content-type": "image/png", "cache-control": "no-store" } });
}

// ---- admin API ----

async function status(env) {
  const [settings, cache, devices, log] = await Promise.all([
    getSettings(env),
    getCache(env),
    env.DB.prepare("SELECT * FROM devices ORDER BY id = 'weather' DESC, id").all(),
    env.DB.prepare("SELECT * FROM fetch_log ORDER BY ts DESC LIMIT 30").all(),
  ]);
  const sources = {};
  for (const [k, v] of Object.entries(cache)) {
    sources[k] = { ts: v.ts, error: v.error, count: Array.isArray(v.data) ? v.data.length : v.data ? 1 : 0 };
  }
  return {
    now: now(),
    settings,
    sources,
    devices: devices.results,
    log: log.results,
    todoistToken: Boolean(env.TODOIST_TOKEN),
  };
}

const SETTING_KEYS = ["location_query", "location_label", "tide_rss", "tide_label", "weather_tasks", "todoist_tasks"];

async function saveSettings(request, env) {
  const body = await request.json().catch(() => null);
  if (!body || typeof body !== "object") return json({ error: "JSON body expected" }, 400);
  const stmts = [];
  for (const k of SETTING_KEYS) {
    if (!(k in body)) continue;
    const v = String(body[k]).trim();
    if ((k === "weather_tasks" || k === "todoist_tasks") && !/^\d{1,2}$/.test(v))
      return json({ error: `${k} must be a number` }, 400);
    stmts.push(env.DB.prepare("UPDATE settings SET value = ? WHERE key = ?").bind(v, k));
  }
  if (stmts.length) await env.DB.batch(stmts);
  return json({ ok: true, refresh: await refresh(env, true) });
}

async function saveCmd(request, env) {
  const body = await request.json().catch(() => null);
  if (!body?.dev) return json({ error: "dev required" }, 400);
  // Normalise line endings: the Kindle's /bin/sh chokes on CRLF.
  const cmd = String(body.cmd ?? "").replace(/\r\n?/g, "\n");
  const r = await env.DB.prepare("UPDATE devices SET cmd = ?, cmd_updated = ? WHERE id = ?")
    .bind(cmd, now(), body.dev)
    .run();
  if (!r.meta.changes) return json({ error: "unknown device" }, 404);
  return json({ ok: true });
}
