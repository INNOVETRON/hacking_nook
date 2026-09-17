# server — the thing that does the thinking

Renders an e-ink dashboard to a PNG and serves it over plain HTTP on the LAN.
Runs happily on a **Raspberry Pi Zero 2 W**; also runs on any laptop.

Plain HTTP is deliberate: Android 2.1 cannot do TLS 1.2 or SNI, so the Nook
would fail to fetch over HTTPS. Keep this on your own network.

## Run it

```bash
python3 -m pip install -r requirements.txt      # just Pillow
cp config.example.json config.json              # then edit lat/lon/timezone
python3 panel_server.py --config config.json
```

- `http://<host>:8000/panel.png` — what the Nook fetches
- `http://<host>:8001/` — settings dashboard (programs, schedules, server generation, displayer refresh)
- `http://<host>:8000/` — self-reloading preview page for your desktop browser
- `python3 panel_server.py --once out.png` — render one frame and exit

## Deploy to the Pi Zero 2 W

Clone the repo on the Pi and run the installer — it handles apt deps, the
systemd unit (written for whichever user runs it, in whichever directory the
clone lives) and starting the service:

```bash
git clone https://github.com/AfshinKI/hacking_nook.git ~/hacking_nook
~/hacking_nook/server/install-on-pi.sh
```

To update later:
```bash
cd ~/hacking_nook && git pull && sudo systemctl restart nookpanel
```

Pillow comes from **apt** (`python3-pil`), not pip: Raspberry Pi OS bookworm is
PEP 668 externally-managed, and compiling Pillow on a Zero 2 W takes about an
hour.

Give the Pi a **static IP or DHCP reservation** — the Nook stores a literal URL,
and you do not want to re-type it on an infrared touchscreen.

## Image failures

In renderer/mirror mode, failed downloads retry every 30 seconds (`retry_seconds`).
Only complete PNGs replace the last good image, which is saved atomically under
`server/.cache/` and restored after restart. The server never substitutes a local
dashboard. Without any saved image it returns HTTP 503 with `Retry-After`, allowing
the Nook to retain its own previous image. Successful fetches return to the normal
`refresh_seconds` interval; the Nook's wake interval is controlled separately by `device_refresh_seconds`.

## Config

| Key | Meaning |
|---|---|
| `latitude`, `longitude` | Where the weather and the map come from |
| `location_name` | Free text; used by the `simple` layout |
| `timezone` | IANA name, e.g. `Europe/London` |
| `units` | `metric` or `imperial` |
| `layout` | `hourly`, `today` or `simple` — see below |
| `map_zoom` | 10 = region, 11 = metro (default), 12 = city centre |
| `map_strength` | How dark the map is, 0–1. Higher is punchier |
| `landscape` | `false` → 600×800 portrait (native). `true` → rotated to 800×600 |
| `refresh_seconds` | Proxy image check interval (or local Pillow render interval) |
| `server_refresh_seconds` | Weather-cal image generation interval, 900–86400 seconds; default 1800 |
| `port` | HTTP port |

`config.json` is gitignored — it is yours, and future versions will hold tokens.

## Layouts

**`today`** — modelled on Chris Twomey's
[inkplate10-weather-cal](https://github.com/chrisjtwomey/inkplate10-weather-cal):
a pale city map bleeding into white, a big outlined weather icon straddling the
fade, then date, temperature and conditions in rounded hand-lettering, with an
oversized ghost of the icon watermarked into the bottom corner.

**`hourly`** — the reference project's hourly page at our resolution: a dark
city map with date, temperature and condition badges down the left, over a
nine-hour table of icons, times, temperatures, wind arrows and a hatched
precipitation chart.

**`simple`** — the original dense view: clock, current conditions, three-day
table. More numbers, less atmosphere.

Switch with `"layout"` in the config, or `--layout` for a one-off render.

## Modules

| File | Does |
|---|---|
| `panel_server.py` | HTTP, config, the refresh timer, mirroring |
| `pagechoice.py` | Which page to show: time of day, and weather advisories |
| `weather.py` | Open-Meteo client and WMO code phrases |
| `mapview.py` | Tile fetch, greyscale, fade-to-white, disk cache |
| `icons.py` | Weather icons, drawn — no icon font or asset pack |
| `layouts.py` | The two page designs |
| `fonts.py` | Font lookup with fallbacks |

## Serving the weather-cal pages, and which one

With `renderer_url` set, this server stops drawing pages itself and serves the
ones the weather-cal renderer produces. **Both run on the same Pi** — that URL
is `http://127.0.0.1:8082`, a loopback fetch, not a network dependency. Nothing
outside the Pi is involved once deployed.

The split earns its keep twice over: the renderer redraws every 30 minutes by default (several
minutes of Chromium), while this process decides which page to show on every
refresh; and a render that fails or produces a damaged file never reaches the
panel.

It picks the page on every refresh:

| Time | Page | Why |
|---|---|---|
| 06:00 | `hourly` | Before you leave: what the next nine hours do |
| 09:30 | `today` | The ambient default, and the longest stretch of the day |
| 17:00 | `daily` | End of the day: the week ahead |
| 21:00 | `tomorrow` | Before bed: what you are waking up to |

Override the times with `page_schedule`; each key is the time that page starts.

**Advisories.** If something is about to change that you would want to know
before going out, it switches to `hourly` regardless of the clock, because that
is the page that says *when*:

- precipitation starting — currently dry, and ≥ 50% within the window
- rain turning to snow, or snow to rain
- a thunderstorm
- crossing freezing
- a temperature swing of 8°+ across the window
- wind rising past 40 km/h

A gradual drift is deliberately *not* an advisory: cloud thickening, or two
degrees over six hours, is what the day view already shows. Interrupting for
that is noise.

Advisories are suppressed outside `advisory_from`/`advisory_to` (06:00–22:00 by
default) — nobody is heading out at 03:00, and the overnight `tomorrow` page is
more useful then. Set `"advisories": false` to follow the clock alone.

### Keep the previous image

Each fetched page is fully decoded before it is served, so a truncated or
half-written render is rejected rather than displayed. On any failure the
**previous good image keeps being served**, with its age logged. If there is no
previous image in memory, it restores the last good PNG from disk. On a first-ever
start with no cached image, it returns HTTP 503 and retries after 30 seconds.
The Nook keeps its own previous image; no substitute dashboard is generated.

Thresholds are all overridable: `advisory_hours`, `precip_probability`,
`precip_dry_probability`, `temp_swing`, `wind_speed`.

## Design notes

- Output is 8-bit greyscale (`L`), pure black on white. The panel has 16 grey
  levels and very little contrast headroom; anti-aliased black text on white is
  the only thing that reads well from across a room.
- Nothing moves, nothing animates. A full e-ink refresh takes ~800 ms and
  flashes the screen inverse.
- Weather is [Open-Meteo](https://open-meteo.com/): no API key, no account.
- The map is OpenStreetMap raster tiles, greyscaled and lightened. It is fetched
  **once per location** and cached in `.cache/` — the map never changes, so this
  stays within OSM's tile usage policy and makes every later render instant.
  CARTO's `light_all` would match the reference more closely but now requires an
  API key, and Wikimedia's tiles 403 third parties.
- The upstream project renders **HTML in headless Chrome** (Chart.js + rough.js
  for the sketchy bars) against AccuWeather/OpenWeatherMap and Google Static
  Maps. None of that fits here: Chromium will not fit in a Pi Zero 2 W's 425 MB
  alongside anything else, and all three services want API keys. The designs are
  ported to Pillow instead, against keyless Open-Meteo and OSM.
- The hourly precipitation bars scale to the wettest hour in the window, with a
  floor of 40%, so a dry day still draws a chart rather than a flat line. Every
  bar carries its true percentage.
- Icons are drawn, not downloaded: a silhouette is dilated to make a heavy
  outline, so the union of a cloud's lobes gets one clean edge instead of seams.
  Chunky outlines survive 16 grey levels far better than detailed pictograms.
- The server keeps serving the last good render if a fetch fails, so a flaky
  network shows stale weather rather than an error screen.

## Where this is going

Next additions, in order: a calendar column (ICS/CalDAV feed), then optional
Home Assistant entities, then per-device layouts. See
[../docs/04-project-ideas.md](../docs/04-project-ideas.md).

## Remote settings and future programs

The same process opens a second HTTP listener on `settings_port` (default 8001).
Port 8000 remains the image/preview service; 8082 remains weather-cal. The control
port is intended for the trusted LAN and has no login. Do not expose it publicly.

The dashboard offers one selected Weather & forecast card with radio selection,
render enable switches, start times in the configured timezone, and an advisory
switch. Each enabled render needs a unique start time. The last slot wraps over
midnight. Disabled Hourly cannot be selected by a weather advisory. Disabling a
render affects display selection, not upstream generation cost.

Displayer options set `device_refresh_seconds` (60–86400, default 3600). This is
independent of proxy `refresh_seconds` and the server generation interval.
Program settings sets `server_refresh_seconds` (15 minutes–24 hours, default 30
minutes). The weather-cal adapter polls this setting every 15 seconds and
regenerates all configured pages serially, starting two minutes before each
interval boundary. Changes apply to the next future slot; an active render
finishes normally. Slow runs skip missed slots. Control service outages retain
the last known interval. The image proxy can take up to five more minutes to
pick up completed images.
`X-Nook-Refresh-Seconds` is returned on image responses, even 503; APK 0.2 persists
it before scheduling its next alarm. Existing APKs ignore the header. All devices
using this image endpoint share the setting. A sleeping device cannot receive an
immediate push.

`GET /api/settings` returns schema version 1 and the program catalog.
`POST /api/settings` takes a JSON object containing `active_program`,
`device_refresh_seconds`, `server_refresh_seconds`, `enabled_pages`,
`page_schedule`, and `advisories`. Older callers may omit
`server_refresh_seconds` to preserve its current value.
Invalid values return 400, cross-origin browser writes 403, non-JSON 415, and
persistence failures 500. Valid settings are atomically saved to the existing
config file, preserving unrelated keys, then published in memory. The page worker
wakes immediately; until its fetch finishes, the last good image remains served.
Only the dashboard-exposed settings are hot-reloaded; ports/renderer URLs require
a restart. Back up config.json before manual edits.

`settings.py` owns the versioned catalog and validation, `pagechoice.py` owns
weather scheduling, and `panel_server.py` owns image delivery and recovery.
Future clock/calendar programs should add a stable catalog ID and a server-side
adapter producing a validated PNG, with namespaced program settings and cache
keys. The APK contract stays image + refresh header. Program switching must
finish a valid first render before replacing the cached image. Future orientation
belongs in the adapter's output; do not add layout work to the APK. Per-device
settings will require device IDs and separate profiles; v1 intentionally shares
one displayer profile. No future program is advertised as selectable yet.

### Reset display

The **Reset display** button in Your displayer sends an ADB reboot to the Nook.
Wake it with the n button first: a sleeping or powered-off Nook has no Wi-Fi
connection and cannot receive a remote reboot. The dashboard shows a failure
when connection, timeout, or reboot fails; it never queues a reboot for later.
A successful response means ADB accepted the command, not that boot has finished.

Install `adb` on the server (included by `install-on-pi.sh`) and set
`"nook_adb_address": "192.0.2.78:5555"` in its config.json, then restart
nookpanel. Replace this documentation-only IP with the actual Nook address; the example leaves it blank to avoid
rebooting an unintended device. No root or sudo is needed for the server's ADB.
The address is server-configured and cannot be supplied by the browser.

`POST /api/display/reset` takes `{}` with `Content-Type: application/json`.
It uses the same origin checks as settings writes. Connection/state/reboot
commands have 8/4/5-second timeouts. Unreachable devices return 503, simultaneous
requests and repeats within 30 seconds of success return 409, and success returns
200 with a message. All commands select the configured device explicitly.

### Simple Weather program

Select **Simple Weather** with the second radio button in the control center.
It uses the approved portrait concept B: month/day/weekday, a bold outlined
weather icon, large current temperature, and four upcoming hourly forecasts with
rain chance and wind. The footer shows the observation source/time. In Edmonton,
current temperature uses ECCC Blatchford observations; forecast icons and hourly
values use Open-Meteo.

This program stays on its single page, independent of the original program's
schedule and weather advisories. Switching back restores the existing schedule.
Server generation and displayer intervals remain shared. The renderer prepares
`simple-weather.png` alongside its scheduled pages (one additional Chromium render
per generation). A failed fetch retains the last good image, and disk caches are
separate for the two programs. No APK update is required.

### Adaptive displayer refresh

Displayer options offers Fixed or Adaptive for Simple Weather. Fixed remains
backward-compatible and is always used for other programs. Adaptive defaults:
15-minute minimum, two-hour daytime maximum, midnight–06:00 quiet hours.
Simple Weather's Program settings exposes temperature delta (3°C), precipitation
chance (50%), and wind speed delta (20 km/h). Thresholds use Celsius/km/h even
when artwork uses imperial units. Condition-category changes also shorten sleep;
sun/moon changes alone do not.

Each Simple Weather PNG embeds its displayed temperature and the next 24 forecast
hours in a PNG text chunk. `/panel.png` computes `X-Nook-Refresh-Seconds` from the
exact bytes it serves, never from an unrelated newer forecast. This metadata is
published atomically with the pixels and survives proxy disk caching and restart.
No device changes are needed. The dashboard previews the interval that would be
sent on the next fetch; it is not a report of the sleeping device's alarm.

Stable daytime weather allows up to two hours (and no later than image creation
plus the maximum). A 3°C change relative to the displayed reading, precipitation
starting/stopping, a condition change or significant wind change wakes sooner.
Imminent changes cap the interval at 30 minutes, with a 15-minute lead for
conditions/precipitation/wind. Quiet-hour boundaries can be closer than the minimum.
Missing, malformed or stale metadata uses the minimum interval, bounded by the next
quiet-hour boundary. Images older than the server generation interval plus 15
minutes (at most 90 minutes) cannot authorize a long sleep.

Overnight images show the first four forecast hours at/after the configured morning
wake time and a `NEXT UPDATE` label. Only a fresh overnight image with all four
morning forecasts and the matching wake time can authorize sleep until morning.
The renderer anticipates quiet-hour boundaries by five minutes; during transitions
or outages the Nook may make an additional short retry. Elapsed times use UTC
while quiet hours follow the configured local timezone, including DST.

Server generation stays independent (30 minutes by default). A 15-minute fetch
may reuse the preceding image; set server generation to 15 minutes if you want
freshly generated images at that frequency. Quiet hours intentionally suppress
weather-triggered wakes. A sleeping Nook cannot learn about an unexpected weather
change until its next fetch. Manual wakes still fetch normally.

Display activity is available at `/api/display/status` and on the control room.
Only successful `/panel.png` or `/panel` deliveries to the NookPanel client count;
previews and failed requests do not. The next fetch estimate uses the interval
actually sent with the last image, so changing settings does not move that estimate.
Delivery confirms the server finished writing the image, not that the device
finished displaying it. Events are grouped in the configured timezone and stored
atomically in `server/.cache/display-fetches.json`. Today and yesterday are shown;
tracking begins at deployment, with no invented historical events. Display options
now live inside Your display, including the existing Reset display action.
