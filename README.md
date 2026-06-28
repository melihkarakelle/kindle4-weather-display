# Kindle 4 NT Weather & News Display

Turn an old **Kindle 4 Non-Touch (firmware 4.1.4)** into a battery-friendly, WiFi-connected
e-ink information display. A Raspberry Pi (or any always-on Linux box) generates a single
600×800 black-and-white PNG containing the local weather, a 3-day forecast, tide times and
the latest news headlines. The Kindle wakes up on a timer, downloads the image, draws it on
its e-ink screen, and goes back into deep sleep — so a single charge lasts a long time.

![Kindle weather display](docs/screenshot.png)

*Weather, 3-day forecast, tide times and the latest headlines on one 600×800 e-ink screen,
with a battery indicator in the top-right corner.*

## How it works

```
┌──────────────┐   HTTP :8765    ┌─────────────────────────────┐
│ Raspberry Pi │ ───────────────▶│ Kindle 4 NT (jailbroken)    │
│              │   weather.png   │                             │
│ weather_image│                 │ kindle_daemon.sh:           │
│   .py (cron) │                 │  • WiFi on → wget image     │
│              │                 │  • eips -f -g  (draw)       │
│ serve_image  │                 │  • WiFi off                 │
│   .py (HTTP) │                 │  • RTC alarm + suspend      │
└──────────────┘                 │  • wake after N minutes     │
                                 └─────────────────────────────┘
```

1. **The Pi** runs a small script (`weather_image.py`) on a cron schedule that fetches data
   from public APIs and renders one PNG. A tiny HTTP server (`serve_image.py`) serves it.
2. **The Kindle** runs a daemon that, on a timer, briefly turns on WiFi, downloads the PNG
   (passing its current battery level), draws it with `eips`, turns WiFi off, sets an RTC
   wake alarm, and enters deep sleep (`echo mem > /sys/power/state`). A cron "watchdog"
   restarts the daemon on boot or if it dies.

The e-ink screen keeps showing the last image while the device sleeps, so the display is
always populated even though the CPU is off most of the time.

### Battery indicator

The image is rendered on the Pi, which can't know the Kindle's battery level. So each time
the daemon fetches the image it reads its own battery (`lipc-get-prop com.lab126.powerd
battLevel`) and appends it to the request: `GET /weather.png?batt=85`. The server saves that
value to `battery.txt`, and the next render draws a small battery icon (with a fill bar) and
the percentage in the top-right corner. This way the level shown is always the Kindle's real
charge, drawn with a proper font (the on-device `eips` text mode can't even render a `%`).

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
and under *Settings → Device Info*.

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

## Part 4 — Set up the image server (Raspberry Pi)

Any always-on Linux machine works. You need Python 3 and Pillow.

```bash
sudo apt update
sudo apt install -y python3-pip fonts-freefont-ttf
pip3 install pillow requests
```

Create a project directory and copy these files into it:

```
weather_image.py     # fetches data, renders kindle_weather.png
serve_image.py       # HTTP server on :8765 serving /weather.png
weathericons.ttf     # icon font (erikflowers/weather-icons)
```

### Configure your location and data sources

Edit the `CONFIG` block at the top of `weather_image.py`:

```python
LOCATION_QUERY = "YourTown,YourRegion,Country"   # used for wttr.in
LOCATION_LABEL = "Your Town, Country"            # printed on screen

TIDE_RSS   = "https://www.tidetimes.co.uk/rss/your-port-tide-times"  # "" to disable
TIDE_LABEL = "Your Port — Tide Times"

BBC_RSS    = "https://feeds.bbci.co.uk/news/rss.xml"
```

Data sources used (all free, no API key):
- **Weather:** [wttr.in](https://wttr.in) JSON (`https://wttr.in/<location>?format=j1`)
- **Tides:** a tidetimes.co.uk RSS feed (the script parses the second `<description>`
  block and HTML-unescapes it). Use your nearest port's feed, or set `TIDE_RSS = ""`
  to hide the tide section.
- **News:** any RSS feed (`<item><title>` is parsed).

### Get the weather icon font

```bash
curl -L -o weathericons.ttf \
  https://github.com/erikflowers/weather-icons/raw/master/font/weathericons-regular-webfont.ttf
```

The renderer maps weather codes to glyphs in this font, so icons look crisp on e-ink.

### Test the renderer

```bash
python3 weather_image.py
# → writes kindle_weather.png  (open it to check the layout)
```

### Run the HTTP server as a service

`serve_image.py` serves `kindle_weather.png` at `http://<pi>:8765/weather.png`
(and logs each request to `access.log`, handy for debugging the Kindle).

Create `/etc/systemd/system/kindle-server.service`:

```ini
[Unit]
Description=Kindle image HTTP server
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/USER/kindle_display/serve_image.py
Restart=always
User=USER

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now kindle-server
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8765/weather.png   # → 200
```

### Regenerate the image on a schedule

Add to the Pi's crontab (`crontab -e`) — every 10 minutes:

```cron
*/10 * * * * cd /home/USER/kindle_display && python3 weather_image.py >> render.log 2>&1
```

> The image is regenerated more often than the Kindle fetches it — that's fine, the Kindle
> always gets the latest one.

---

## Part 5 — Install the Kindle daemon

The repo ships `*.example` templates. Copy them, fill in your values, and push them
to `/mnt/us/` on the Kindle:

```bash
cp kindle_daemon.sh.example   kindle_daemon.sh
cp kindle_watchdog.sh.example kindle_watchdog.sh
# edit kindle_daemon.sh (see below), then copy both to the Kindle's /mnt/us/
```

| File | Purpose |
|------|---------|
| `kindle_daemon.sh` | the main loop: download → draw → sleep → wake |
| `kindle_watchdog.sh` | restarts the daemon on boot / if it crashes |

### Configure the daemon

Edit the CONFIG block at the top of `kindle_daemon.sh`:

```sh
PI_IP="192.168.X.X"      # your image server's IP
PI_PORT="8765"
INTERVAL=1800            # seconds between updates (1800 = 30 min)
WIFI_WAIT=8              # seconds to wait after enabling WiFi
```

What the daemon does each cycle:
1. Turn WiFi on, wait, read the battery level, `wget` the PNG with `?batt=NN`.
2. `eips -c` (clear) → `sleep 2` → `eips -f -g` (full draw) → `sleep 5` (let e-ink settle).
3. Turn WiFi off.
4. Set RTC alarm for `INTERVAL` seconds, then `echo mem > /sys/power/state` (deep sleep).
5. On wake, repeat.

It also keeps a **single-instance lock** (`/tmp/kindle_daemon.pid`) and, on first start,
stays awake for **120 seconds** before the first suspend — a maintenance window so you can
SSH in and make changes before the device starts disappearing into sleep.

### Install the watchdog in cron

Because cron is paused during suspend, the watchdog's job is to (re)start the daemon on
**boot** and after any **crash**. Make the root FS writable and edit the crontab:

```sh
mount -o remount,rw /
# add this line to /etc/crontab/root:
* * * * * /bin/sh /mnt/us/kindle_watchdog.sh
sync
```

`kindle_watchdog.sh` checks the PID file every minute and starts
`kindle_daemon.sh` if it isn't running.

### Start it the first time

```sh
chmod +x /mnt/us/kindle_daemon.sh /mnt/us/kindle_watchdog.sh
/bin/sh /mnt/us/kindle_watchdog.sh        # starts the daemon now
tail -f /mnt/us/kindle_display.log        # watch it work
```

You should see the weather image appear within a few seconds.

---

## File reference

| File | Where | Purpose |
|------|-------|---------|
| `weather_image.py` | Pi | Fetch weather/tide/news, render `kindle_weather.png` |
| `serve_image.py` | Pi | HTTP server on `:8765`, serves the PNG, logs access |
| `weathericons.ttf` | Pi | Weather glyph font (erikflowers/weather-icons) |
| `kindle_daemon.sh` | Kindle `/mnt/us/` | Main download → draw → suspend loop |
| `kindle_watchdog.sh` | Kindle `/mnt/us/` | Cron-driven boot/crash restart |

Logs on the Kindle: `/mnt/us/kindle_display.log` (events),
`/mnt/us/daemon_debug.log` (stdout/stderr).

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
It's asleep most of the time by design. SSH only works during a wake window. Either wait
for the next cycle, use the 120 s first-boot maintenance window, or wake it from the
device (power button, then exit the menu). Remember to test port 22, not ping.

**`wget: Network unreachable`.**
WiFi wasn't ready. Keep the `sleep 8` after enabling WiFi. Also confirm the Kindle and the
Pi are on the same network and the server returns `200` for `/weather.png`.

**Verify the Kindle is actually fetching.**
On the Pi, check the request log:
```bash
grep <kindle-ip> ~/kindle_display/access.log | tail
```

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

## License

MIT — do whatever you like, no warranty.
