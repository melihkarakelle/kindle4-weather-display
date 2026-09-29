-- Editable settings (key/value), seeded with the values the Pi version used.
CREATE TABLE settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
INSERT INTO settings (key, value) VALUES
  ('location_query', 'Sturry,Canterbury,UK'),
  ('location_label', 'Sturry, Canterbury UK'),
  ('tide_rss', 'https://www.tidetimes.co.uk/rss/herne-bay-tide-times'),
  ('tide_label', 'Herne Bay — Tide Times'),
  ('weather_tasks', '8'),
  ('todoist_tasks', '16');

-- One row per Kindle screen ('weather' or 'todoist'), updated on every fetch.
CREATE TABLE devices (
  id TEXT PRIMARY KEY,
  last_seen INTEGER,              -- unix seconds of the last image fetch
  battery INTEGER,                -- % reported with ?batt=
  ip TEXT,
  cmd TEXT NOT NULL DEFAULT '',   -- shell script served at cmd.sh?dev=<id>
  cmd_updated INTEGER,            -- when the admin last saved cmd
  cmd_fetched INTEGER             -- when the device last pulled cmd.sh
);
INSERT INTO devices (id) VALUES ('weather'), ('todoist');

-- Latest data from each source, refreshed by the cron job.
CREATE TABLE cache (
  source TEXT PRIMARY KEY,        -- 'weather', 'tides', 'todoist'
  ts INTEGER NOT NULL,            -- unix seconds when fetched
  data TEXT,                      -- JSON
  error TEXT                      -- last error message, NULL when OK
);

-- Recent image fetches, for the admin page.
CREATE TABLE fetch_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  device TEXT NOT NULL,
  battery INTEGER,
  ip TEXT
);
CREATE INDEX fetch_log_ts ON fetch_log (ts);
