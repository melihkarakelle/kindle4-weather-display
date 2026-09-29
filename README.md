# Kindle 4 NT Weather & Todoist Display

Turn an old **Kindle 4 Non-Touch (firmware 4.1.4)** into a battery-friendly, WiFi-connected
e-ink information display. A small server renders a 600×800 black-and-white PNG with the local
weather, a 3-day forecast, tide times and your Todoist Inbox. The Kindle wakes up on a timer,
downloads the image, draws it on its e-ink screen and goes back into deep sleep — so a single
charge lasts a long time. A second Kindle can show a full-screen Todoist list.

![Kindle weather display](docs/screenshot.png)

*Weather, 3-day forecast, tide times and a configurable bottom panel on one 600×800 e-ink
screen, with a battery indicator in the top-right corner. (The screenshot shows an older RSS
news panel; the current code shows your Todoist Inbox there.)*

## How it works

```
┌────────────────────────────┐   HTTP (LAN)    ┌─────────────────────────────┐
│ Server: Cloudflare Worker  │ ───────────────▶│ Kindle 4 NT (jailbroken)    │
│ (wrangler dev on a home    │  weather.png    │                             │
│  server, see worker/)      │  todoist.png    │ kindle_daemon.sh:           │
│                            │  cmd.sh         │  • WiFi on → wget image     │
│ • cron: fetch weather,     │  daemon.sh      │  • run remote command       │
│   tides, Todoist → D1      │                 │  • eips -f -g  (draw)       │
│ • draws the PNG itself     │ ◀───────────────│  • WiFi off                 │
│ • admin page               │   ?batt=NN      │  • RTC alarm + suspend      │
└────────────────────────────┘                 └─────────────────────────────┘
```

1. **The server** is a Cloudflare Worker (`worker/`). A cron job caches weather
   ([wttr.in](https://wttr.in)), tides and Todoist in D1. When a Kindle asks for its image the
   Worker draws it on the spot — a tiny pure-JavaScript PNG encoder plus a pre-rendered bitmap
   font atlas, no native image library — and serves an admin page with live previews.
2. **The Kindle** runs a daemon that, on a timer, briefly turns on WiFi, downloads its PNG
   (passing its battery level), runs any pending remote command, draws the image with `eips`,
   turns WiFi off, sets an RTC wake alarm and enters deep sleep
   (`echo mem > /sys/power/state`). A cron "watchdog" restarts the daemon on boot or if it dies.

The e-ink screen keeps showing the last image while the device sleeps, so the display is
always populated even though the CPU is off most of the time.

> **Plain HTTP on the LAN is required.** The Kindle's BusyBox `wget` cannot do HTTPS, so run
> the Worker locally with `wrangler dev` (or behind any LAN reverse proxy), not only on
> Cloudflare's public edge.

> The first version of this project rendered the image with Python/Pillow on a Raspberry Pi.
> Those scripts are kept in [`pi-legacy/`](pi-legacy/) for reference.

### Battery indicator

The server can't know a Kindle's battery level, so each time the daemon fetches its image it
reads the battery (`lipc-get-prop com.lab126.powerd battLevel`) and appends it to the request:
`GET weather.png?batt=85`. The server stores it per device, draws a battery icon with the
percentage in the corner, and shows it on the admin page (the on-device `eips` text mode
can't even render a `%`). If it always reads 0, check the admin page's status report: a fully
drained battery reports 0 everywhere (and resets the clock) until it has charged a while.

### Remote commands

The Kindles sleep almost all the time, so SSH is rarely reachable. Instead, the admin page has
a script box per device. The daemon fetches `cmd.sh?dev=<id>` on every wake and runs it once
when its content changes. Commands get `$SERVER` and `$DEV` in their environment. Built-in
templates: update the daemon from the server (`daemon.sh?dev=<id>`), change the interval,
restart, reboot, and **send a status report** — a command can report back with
`wget -q -O /dev/null "$SERVER/report?dev=$DEV&msg=..."` (BusyBox `wget` cannot POST) and the
text appears under the device card.

---

## Part 1 — Jailbreak the Kindle

> ⚠️ **Done at your own risk.** Jailbreaking is reversible, but a wrong firmware/package
> can brick the device.

### Firmware compatibility

This project targets the **Kindle 4 Non-Touch (K4NT, model D01100, "2012")** on firmware
**4.1.x** (tested on **4.1.4**). The `kindle-k4-jailbreak` package supports the K4NT
firmware range up to 4.1.4. **Check your firmware first**
(*Home → Menu → Settings → Menu → Device Info*, or read the bottom of the Settings screen)
and pick the matching package version. Other models (Touch, Paperwhite, etc.) and other
firmwares need different jailbreaks — do not use these files on them.

The authoritative, always-current instructions and downloads live on the MobileRead wiki —
**read these before starting**, as package names and supported firmwares change over time:

- **MobileRead — Kindle 4 NT Hacking wiki:** https://wiki.mobileread.com/wiki/Kindle4NTHacking
- Jailbreak thread (`kindle-k4-jailbreak`) and **USBNetwork** hack are linked from that wiki.

### Steps

You need two community packages (both linked from the wiki above):
- **`kindle-k4-jailbreak-*`** — the jailbreak itself
- **`usbnet-*` (USBNetwork)** — gives you SSH access

**1. Install the jailbreak (via diagnostics mode):**

1. Extract the jailbreak archive and read its bundled `README` (it lists the exact files
   for your firmware).
2. Connect the Kindle via USB; it mounts as a drive. Copy the jailbreak files to the root
   of the drive — typically **`data.tar.gz`**, **`ENABLE_DIAGS`**, and the
   **`diagnostic_logs/`** folder. **Safely eject.**
3. Boot into diagnostics: **Menu → Settings → Menu → Restart**. The screen may freeze
   briefly (normal); the Kindle reboots **into the diagnostics menu** because of
   `ENABLE_DIAGS`.
4. In the diagnostics menu, navigate with the **5-way controller** (the on-screen
   "FW Left/Right/Up/Down" labels mean the directions on the 5-way pad):
   - Select **`D) Exit, Reboot or Disable Diags`**
   - Then **`R) Reboot System`**
   - Confirm **`Q) To continue`** (press the 5-way **Left** when prompted)
5. The Kindle reboots and runs the jailbreak. When it finishes you'll see a new
   **"You are Jailbroken"** book at the top of your library. ✅

**2. Install USBNetwork the same way** (copy its files, reboot into diagnostics, `D → R → Q`).

**3. Verify dev commands:** after both are installed, the search box should accept the
developer commands `;debugOn` and `~` (e.g. `~usbNetwork`) used below.

After this you have:
- A writable root filesystem (via remount, see below)
- The ability to enable an SSH-capable USB-Ethernet or WiFi network interface

---

## Part 2 — Get a shell (SSH)

The USBNetwork hack exposes the Kindle as a USB-Ethernet device and/or over WiFi.

### Enabling USBNetwork

In the Kindle search box type the developer command to toggle USB networking
(commonly `~usbNetwork`). When active, the Kindle appears as a network interface on
your computer.

On the host (macOS example — interface name and IP are yours to choose):

```bash
sudo ifconfig en9 192.168.15.201 netmask 255.255.255.0 up
ssh root@192.168.15.244     # the Kindle's USB-net IP
```

### Root password

The default root password is derived from the device serial number. Use the community
calculator at **https://www.sven.de/kindle/** (paste your serial, it returns the
password). Typical results look like `fiona____`. The serial is on the back of the device
and under *Settings → Device Info*. The calculator lists several candidates; the one that
worked on our devices is `fiona` + characters 8–10 of the serial's MD5:

```bash
printf '%s\n' YOUR_SERIAL | md5 | cut -c 8-10     # Linux: md5sum
```

> **USB vs WiFi:** over USB networking the SSH server does not check the password at all,
> so any password seems to "work". Over WiFi (`K3_WIFI="true"`) it is checked — a wrong
> password only shows up there. Each Kindle has its own password.

### SSH over WiFi (recommended once configured)

Once the Kindle is on your WiFi, you can usually SSH straight to its WiFi IP:

```bash
ssh root@<kindle-wifi-ip>
```

> **Gotcha:** On many K4NT setups **ICMP ping is blocked but SSH (port 22) is open.**
> Don't conclude "the device is offline" from a failed ping — test the port instead:
> ```bash
> nc -z -G 2 <kindle-wifi-ip> 22 && echo "SSH open"
> ```

### Making the root filesystem writable

The root filesystem is mounted read-only and reverts to read-only on every boot:

```bash
mount -o remount,rw /
# ... make changes ...
sync
```

Persistent, always-writable locations:
- `/mnt/us/` — the user partition (FAT32, also visible over USB) — **put your scripts here**
- `/var/local/` — ext3, survives reboots

---

## Part 3 — Know your Kindle environment

This is BusyBox-based and minimal. Things that bite you:

| Topic | Note |
|-------|------|
| `eips` (draw to e-ink) | Full path `/usr/sbin/eips`, **not on PATH**. Use `eips -f -g file.png` for a *full* refresh (no ghosting). After drawing, **`sleep 5` before suspend** or the write is left half-finished and leaves artifacts. |
| `wget` | BusyBox 1.7.2 — **no `--timeout`**. Use only `wget -q -O out url`. |
| WiFi control | `lipc-set-prop com.lab126.wifid enable 1` (on) / `0` (off). After enabling, **`sleep 8`** before downloading or you get "Network unreachable". |
| Missing tools | No `setsid`, `nohup`, `od`. `timeout` segfaults. A backgrounded script dies on SIGHUP — start it with **`trap '' HUP`** at the top. |
| `reboot` | Not on PATH; use `/sbin/reboot`. |
| Crontab | `/etc/crontab/root`. cron auto-starts on boot (`S90cron`). It only *reads* the file, so a read-only root FS is fine. |
| Suspend / RTC wake | `echo mem > /sys/power/state` for deep sleep. Set the wake alarm via **`/sys/class/rtc/rtc1/wakealarm`** (note `rtc1`, not `rtc0`). `lipc-set-prop ... rtcWakeup` does **not** work from userspace. |
| Screensaver | `lipc-set-prop com.lab126.powerd preventScreenSaver 1` stops the OS from drawing its own sleep image over yours. |

---

## Part 4 — Set up the server (Cloudflare Worker)

The server lives in [`worker/`](worker/). It needs Node.js, `wrangler` and — once, to build the
font atlas — Python 3 with Pillow. It can run on any always-on machine on your network.

```bash
cd worker
npm install -g wrangler        # or use npx wrangler
pip3 install pillow
```

### Build the font atlas

Workers cannot rasterise TrueType fonts, so every glyph the screens need is pre-rendered into
`src/atlas.json` by `tools/make_atlas.py`. Put the two icon fonts in `worker/assets/`:

```bash
mkdir -p assets
curl -L -o assets/weathericons.ttf \
  https://github.com/erikflowers/weather-icons/raw/master/font/weathericons-regular-webfont.ttf
curl -L -o assets/fa-solid.ttf \
  https://github.com/FortAwesome/Font-Awesome/raw/6.x/webfonts/fa-solid-900.ttf
python3 tools/make_atlas.py     # uses Arial on macOS or FreeSans on Linux (apt install fonts-freefont-ttf)
```

The atlas and fonts are not committed (the text font is a system font). Re-run the script
whenever you change fonts, sizes or add characters (e.g. another language).

### Configure and run

```bash
echo "TODOIST_TOKEN=your_todoist_api_token" > .dev.vars      # Todoist → Settings → Integrations → Developer
npx wrangler d1 migrations apply kindle --local
npx wrangler dev --ip 0.0.0.0 --port 8787
```

Open `http://<server-ip>:8787/` for the admin page. Location, tide feed and task counts are
edited there (they are seeded in `migrations/0001_init.sql`). Data sources, all free:
[wttr.in](https://wttr.in) (weather, no key), a tidetimes.co.uk RSS feed (leave empty to hide
tides) and the [Todoist API v1](https://developer.todoist.com/).

The `*/10` cron in `wrangler.jsonc` refreshes the cache. Plain `wrangler dev` does not fire
crons by itself; either run it with `--test-scheduled` and call
`curl "http://localhost:8787/__scheduled?cron=*/10+*+*+*+*"` from the host's crontab, or rely on
the built-in fallback — a screen request refreshes data that is older than 30 minutes.

> **The admin page has no login.** Keep the server on your LAN (or behind something like
> Cloudflare Access). The Kindle endpoints must stay reachable over plain HTTP on the LAN.

Endpoints:

| Path | Used by | Purpose |
|------|---------|---------|
| `/` | you | admin page: previews, battery, last contact, settings, remote commands |
| `weather.png?batt=NN` | Kindle 1 | weather + forecast + tides + Todoist |
| `todoist.png?batt=NN` | Kindle 2 | full-screen Todoist Inbox |
| `daemon.sh?dev=<id>` | Kindle | the daemon, with the server address filled in |
| `cmd.sh?dev=<id>` | Kindle | pending remote command |
| `report?dev=<id>&msg=…` | Kindle | report text from a remote command |

---

## Part 5 — Install the Kindle daemon

The daemon is served by the server, already configured for the address you fetch it from.
On the Kindle (over SSH), with `SERVER` set to your server:

```sh
SERVER=http://192.168.X.X:8787
wget -q -O /mnt/us/kindle_daemon.sh "$SERVER/daemon.sh?dev=weather"   # dev=todoist for a Todoist screen
chmod +x /mnt/us/kindle_daemon.sh
```

Copy `kindle_watchdog.sh.example` from this repo to `/mnt/us/kindle_watchdog.sh`.

What the daemon does each cycle:
1. Turn WiFi on, wait, read the battery level, `wget` its PNG with `?batt=NN`.
2. Fetch `cmd.sh` and run it once if it changed (with `$SERVER` and `$DEV` set).
3. `eips -c` (clear) → `sleep 2` → `eips -f -g` (full draw) → `sleep 5` (let e-ink settle).
4. Turn WiFi off.
5. Set an RTC alarm for `INTERVAL` seconds (default 1800 = 30 min), then
   `echo mem > /sys/power/state` (deep sleep).
6. On wake, repeat.

If the server is unreachable, `wget` gives up after 25 s, the last image stays on screen and
the daemon tries again next cycle. A single-instance lock (`/tmp/kindle_daemon.pid`) stops the
watchdog from starting a second copy.

### Install the watchdog in cron

Because cron is paused during suspend, the watchdog's job is to (re)start the daemon on
**boot** and after a **crash**. Make the root FS writable and edit the crontab:

```sh
mount -o remount,rw /
# add this line to /etc/crontab/root:
* * * * * /bin/sh /mnt/us/kindle_watchdog.sh
sync
```

### Start it the first time

```sh
chmod +x /mnt/us/kindle_watchdog.sh
/bin/sh /mnt/us/kindle_watchdog.sh        # starts the daemon now
tail -f /mnt/us/kindle_display.log        # watch it work
```

The image should appear within a few seconds, and the device shows up as online on the admin
page. From then on, change things through the admin page's remote commands instead of SSH.

---

## File reference

| File | Where | Purpose |
|------|-------|---------|
| `worker/src/index.js` | server | routes, cron refresh, admin API |
| `worker/src/layouts.js` | server | the two screen layouts |
| `worker/src/canvas.js`, `png.js` | server | drawing primitives and PNG encoder |
| `worker/src/sources.js` | server | wttr.in, tide RSS and Todoist fetchers |
| `worker/src/kindle_daemon.sh` | server → Kindle | daemon template served at `daemon.sh` |
| `worker/src/page.html` | server | admin page |
| `worker/tools/make_atlas.py` | build | renders the font atlas |
| `kindle_watchdog.sh.example` | Kindle `/mnt/us/` | cron-driven boot/crash restart |
| `pi-legacy/` | — | the original Raspberry Pi + Pillow version |

Logs on the Kindle: `/mnt/us/kindle_display.log` (events), `/mnt/us/daemon_debug.log`
(stdout/stderr, including remote command output).

### Second screen: a Todoist-only display

A second Kindle can show just your Todoist Inbox, full-screen: install the daemon with
`daemon.sh?dev=todoist`. It shows the render time top-left and its battery top-right. Tasks are
sorted by priority; P1–P3 get a star, warning or dot icon (Font Awesome), others a bullet.

---

## Troubleshooting

**The screen shows the OS sleep image instead of mine.**
Make sure the daemon runs `preventScreenSaver 1` and that *it* (not the OS) controls
suspend. The daemon does this on startup.

**Black smudges / ghosting after an update.**
The device suspended before the e-ink write finished. Keep the `sleep 5` after
`eips -f -g`, and use `-f` (full refresh).

**Daemon dies right after starting.**
A backgrounded script gets SIGHUP when its launcher exits. Ensure the first line after
the shebang is `trap '' HUP`.

**Can't SSH in — device "disappears."**
It's asleep most of the time by design. Use the admin page's **remote commands** instead
(including the status report). If you really need a shell: reboot and grab the short window
after boot, or wake it from the device (power button, then exit the menu). Test port 22, not
ping — ICMP is blocked. As a last resort, plug it in over USB: in USB storage mode you can edit
`/Volumes/Kindle/kindle_daemon.sh` directly, no password needed.

**SSH over WiFi stopped working after a reboot.**
Check `/mnt/us/usbnet/`: if the file is named `DISABLED_auto`, rename it to `auto` and set
`K3_WIFI="true"` in `/mnt/us/usbnet/etc/config`, otherwise sshd isn't started at boot.

**`wget: Network unreachable`.**
WiFi wasn't ready. Keep the `sleep 8` after enabling WiFi. Also confirm the Kindle and the
server are on the same network (a second router or SSID often means a different subnet) and
that `curl http://<server>/weather.png` returns `200`.

**Verify the Kindle is actually fetching.**
The admin page shows each device's last contact, battery and IP, plus a log of recent
fetches. A device that hasn't fetched for 45 minutes is flagged.

**Battery always shows 0 %.**
Send the "status report" remote command. If `lipc-get-prop` and the gas gauge both say 0 and
the Kindle's clock is wrong, the battery was fully drained — leave it on the charger.

---

## Battery & power notes

- Constantly-on (no suspend) lasts roughly a day — fine if the Kindle stays on a charger.
- The suspend + RTC-wake loop in this project lets it sleep between updates, dramatically
  extending runtime; longer `INTERVAL` = longer battery life.
- E-ink itself draws power only while *changing* the image, so a 30-minute interval means
  very few refreshes per day.

---

## Credits & references

- **Kindle 4 NT jailbreak, USBNetwork & diagnostics steps** — the MobileRead community:
  [Kindle4NTHacking wiki](https://wiki.mobileread.com/wiki/Kindle4NTHacking)
- **Root password calculator** — [sven.de/kindle](https://www.sven.de/kindle/)
- **Weather data** — [wttr.in](https://github.com/chubin/wttr.in)
- **Weather icons** — [erikflowers/weather-icons](https://github.com/erikflowers/weather-icons)
- **Priority icons** — [Font Awesome Free](https://fontawesome.com) (solid)
- **Tasks** — [Todoist API](https://developer.todoist.com/)

## License

MIT — do whatever you like, no warranty.
