# upstream — running the real weather-cal server

This runs [chrisjtwomey/inkplate10-weather-cal](https://github.com/chrisjtwomey/inkplate10-weather-cal)
itself — its HTML/CSS page layouts, Chart.js and rough.js bars, Selenium and
headless Chromium — rather than our re-implementation in `../server`.

**The Google API adapter is replaced.** Upstream builds its map with Google Static Maps, and
`server.py` constructs `GoogleAPIService` unconditionally at startup:

```
ValueError: Invalid API key provided.
```

That makes a Google Cloud project with billing a hard requirement.
[`google_api_shim.py`](google_api_shim.py) provides the same class with the
same contract, backed by keyless OpenStreetMap tiles and Open-Meteo geocoding.
Local patches and adapters also customize page selection, charts, and generation retries.

Weather needs no key either: upstream ships an `openmeteo` provider.

## Run it

```bash
./upstream/run.sh            # build and start on :8081
docker logs -f nookcal
```

Then `http://localhost:8081/hourly.png` — also `today`, `daily`, `current`,
`tomorrow`.

**The Docker route is x86_64 only.** Upstream's published image is
`linux/amd64` and 1.4 GB. For the Pi, install natively instead — see below.

## Running it on the Raspberry Pi

```bash
# on the Pi
cd ~/hacking_nook && git pull
OSM_MAP_LABEL=Edmonton ./upstream/install-on-pi.sh
journalctl -u weather-cal -f
```

No Docker. Raspberry Pi OS ships `chromium` and `chromium-driver` in apt, so a
venv against those is both lighter and simpler than a container runtime on a
box with 425 MB of RAM. The installer:

- installs chromium, chromium-driver and the Python deps,
- raises swap to **2 GB** (`SWAP_MB=` to change) — Chromium needs more headroom
  than this Pi has in RAM, and swapping is much better than being OOM-killed,
- takes **Pillow and PyYAML from apt**, not pip: neither publishes armv7 wheels,
  and building them here takes the better part of an hour. The venv is created
  with `--system-site-packages` so they are visible,
- relaxes upstream's exact version pins, which have no armv7 wheels either,
- copies the map shim into the submodule checkout,
- writes `upstream/run/config.yaml` with **one page, not five** — every page is
  a separate Chromium run, and on this hardware that is the difference between
  half a minute and several,
- installs and starts a `weather-cal` systemd unit on **port 8082**.

`server.py` reads `config.yaml` from its working directory and has no
`--config` flag, which is why the unit runs from `upstream/run/`.

Note that the installer writes into `external/inkplate10-weather-cal/`, so the
submodule shows as dirty on the Pi. That is expected: upstream also writes its
rendered PNGs into `server/views/` there. The Pi is a deployment target, not a
place to edit from.

### Starting at boot

The installer enables the unit, so it comes up on its own. Two things matter on
a Wi-Fi Pi and are handled in the unit:

- **DNS lags the link.** `NetworkManager-wait-online` returns in about two
  seconds, but the renderer geocodes at startup and dies on `Temporary failure
  in name resolution`. An `ExecStartPre` waits (up to two minutes) for a name to
  resolve, then starts regardless.
- **`RestartSec=30`.** Long enough that a crash cannot spin, short enough that a
  boot-time failure is not a multi-minute outage.

The clock also matters: a Pi has no RTC, so the time is wrong until NTP syncs,
and page selection is by time of day. `After=time-sync.target` orders around it.

### Do not restart it mid-regeneration

A regeneration is several minutes of Chromium. `systemctl restart` on top of one
leaves two browsers competing, and Selenium's webdriver connection gives up
after 120 seconds — a timeout it does not expose as a setting. The unit sets
`TimeoutStopSec=90` and `RestartSec=120` so a dying run takes its children with
it and does not tight-loop, but the reliable move is to check first:

```bash
journalctl -u weather-cal -n 5     # idle looks like "Starting http server"
sudo systemctl stop weather-cal && sleep 5 && sudo systemctl start weather-cal
```

### Then point the panel at it

```bash
# server/config.json on the Pi
{ "mirror_url": "http://127.0.0.1:8082/hourly.png" }
sudo systemctl restart nookpanel
```

The panel server stops rendering and mirrors instead, keeping the last good
image if a render fails. The Nook needs no change — it still fetches
`http://<pi>:8000/panel.png`.

## Changing the map

Everything about the map is an environment variable, read by the shim. Set it
before `run.sh`, then restart the container.

| Variable | Default | What it does |
|---|---|---|
| `OSM_MAP_ZOOM` | `12` | 11 = whole metro, 12 = inner city, 13 = downtown, 14 = a few blocks |
| `OSM_MAP_CENTER` | *(geocoded from `location`)* | `"53.5461,-113.4938"` to frame it by hand |
| `OSM_MAP_STYLE` | `lineart` | See "Map styles" below |
| `OSM_MAP_LABEL` | *(unset)* | Place name on a black plate, `lineart` only. The page crops the map, so it is usually out of frame |
| `OSM_MAP_STRENGTH` | `0.70` | 0–1. Higher is more contrast; lower fades towards white |
| `OSM_MAP_SIZE` | `1200` | Square edge in pixels before the page scales it |
| `OSM_MAP_FILE` | *(unset)* | Your own image — see below |

```bash
OSM_MAP_ZOOM=13 OSM_MAP_CENTER="53.5444,-113.4909" ./upstream/run.sh
```

## Map styles

**`lineart`** (default) — thin black streets and solid black water on white,
drawn from raw OpenStreetMap geometry fetched through the
[Overpass API](https://overpass-api.de/). This is the printed-poster look, and
it is the best possible input for this panel: E Ink has 16 grey levels and
upstream dithers to 4, so a greyscale photo turns to noise, while pure black on
white has nothing to dither.

It exists because every black-and-white raster basemap that used to serve this
style is gone — Stamen Toner moved to Stadia and needs a key,
`tiles.wmflabs.org/bw-mapnik` no longer resolves, Tracestrack returns 403.

One Overpass query per location, cached to disk as JSON and then as a rendered
PNG. Overpass is a shared free service; do not point a loop at it. Edmonton at
zoom 12 is ~34,000 elements and takes about 13 seconds the first time, then
nothing.

**`dark`** / **`light`** — raster tiles from OpenStreetMap, greyscaled.
`dark` inverts them, which is what upstream's custom Google map style does.
Tunable with `OSM_MAP_STRENGTH`.

The tiles are cached inside the container, so a restart with the **same**
settings is instant and does not re-hit OpenStreetMap. Changing any setting
changes the cache key and fetches once more.

## Using your own picture instead of a map

Point `OSM_MAP_FILE` at any image — a screenshot from another map service, a
hand-drawn map, a photo, a logo, anything:

```bash
OSM_MAP_FILE=~/Pictures/my-map.png ./upstream/run.sh
```

`run.sh` mounts it into the container for you. The shim:

1. converts it to greyscale,
2. scales it to **cover** a square (so it never letterboxes),
3. centre-crops to `OSM_MAP_SIZE`.

So give it something roughly square, or expect the edges to be cropped. The
page then fades the bottom of it to white with its own CSS, and the badges sit
over the top-left — keep anything important out of those areas.

It is re-read whenever the file's modification time changes, so editing the
image and restarting is enough.

**Making a good one:** the panel has 16 grey levels and upstream dithers to 4,
so fine detail and smooth gradients turn to noise. Bold shapes survive; texture
does not. Line art beats photographs every time — which is why `lineart` is the
default rather than something you have to supply.

**Use something you have the right to use.** Map prints sold on stock sites and
print-on-demand shops are copyrighted artwork, and the watermarked previews are
not licensed for use. `lineart` produces the same look from OpenStreetMap data,
which is open (ODbL) and needs only attribution.

## Running it on the desktop instead

If you would rather not put Chromium on the Pi, run the container on a desktop
and have the Pi mirror it:

```json
// server/config.json on the Pi
{ "mirror_url": "http://<desktop-ip>:8081/hourly.png" }
```

The Pi fetches that on its refresh timer and keeps the last good copy, so the
panel goes stale rather than blank when the desktop is off. The trade-off is
that the image only updates while the desktop is running — which is why the
native Pi install above is the better answer for an always-on display.

## Attribution

Map data is © OpenStreetMap contributors, [ODbL](https://www.openstreetmap.org/copyright).
The page has no space for a credit line, which is fine for a private wall
display; if you ever publish a picture of the panel, credit it there.

## Keeping up with upstream

`external/inkplate10-weather-cal` is a submodule pinned to a commit, and the
Docker image is pulled from upstream's `:latest` tag. Our patch is one file
against a small, stable contract — `get_static_map_local_src(map_id, location)`
returning a path relative to `views/html/`. If upstream changes that signature,
the shim needs updating; nothing else here will notice.

## Generation failures

`retrying_server.py`, enabled by patch `0003`, retries a failed generation after
30 seconds and then 60 seconds (three attempts total). Retries refresh source data
and use the upstream rendering lock and atomic PNG writes. Existing page images
remain available. After three failures the normal scheduler/systemd recovery takes
over; shutdown interrupts the retry delay. Both native install/update scripts and
the Docker image install the adapter. The panel proxy retains its disk-cached last
good image while the renderer recovers.

Run failure-path tests with `python3 -m unittest discover -s tests` from the repo root.

## Adaptive Today and Tomorrow charts

Only the bottom chart in Today/Tomorrow changes. The hourly and daily pages keep
their layouts. Selection happens on each scheduled render, with no new Nook wakeups.

Priority (defaults chosen for this dashboard, not weather alerts):

1. **Precipitation** when any relevant hour has at least 40% probability, at least
   0.1 mm forecast precipitation, or a precipitation weather code (including snow
   and thunderstorms). Today checks from now through the next five hours; Tomorrow
   checks all of tomorrow's 06:00–21:00 hours. The chart retains the hatched chance bars.
2. **Wind** for sustained wind at least 30 km/h or gusts at least 45 km/h,
   or a cloudy hour (at least 60% cloud cover) with wind at least 20 km/h or
   gusts at least 35 km/h.
3. **UV** when the forecast peak is at least 3.
4. **Wind** for sustained wind at least 20 km/h or gusts at least 35 km/h.
5. **UV** on sunny days (a daylight hour at most 40% cloud cover) with nonzero UV.
6. **Temperature** for otherwise quiet weather, including cloudy calm days and nights.

Wind thresholds use km/h internally and the chart respects configured display
units. UV is suppressed at night. Unknown values appear as gaps, never invented
zeroes. The heading identifies the selected metric and gives a short explanation
(e.g. when precipitation is possible, UV peak, or maximum gusts).

Tomorrow fetches every hour before selection, then draws eight two-hour peak
buckets to fit the screen, including spikes between labels. Its chart is explicitly
labelled `2h peaks`. Today retains the existing upcoming forecast window.
`tomorrow_hourly` is invalidated with the other datasets on regeneration.

The added fields (`uv_index`, `cloud_cover`, `wind_gusts_10m`, `precipitation`) come
from the same [Open-Meteo forecast API](https://open-meteo.com/en/docs) request.
`smart_chart.py` is the local selection/rendering helper; patch `0004` wires it into
Today/Tomorrow and the provider. Native install/update and Docker apply the overlays.

Validation: `python3 -m unittest discover -s tests` tests selection and image recovery.
For provider/template integration, apply all patches to an isolated upstream copy,
copy `smart_chart.py` beside its `server.py`, then run with the weather-cal venv:

```bash
python tests/check_smart_renderer.py --server /tmp/patched-weather-cal/server \
    --previews /tmp/chart-previews
```

The optional preview step uses Chromium and checks the chart fits the 600×800 page.

UV and temperature use smooth, shape-preserving cubic lines with value markers.
The curves pass through the forecast values without inventing higher peaks or
negative UV, and break across missing data. Precipitation (rain/snow) and wind
retain hatched bars.

### Server generation interval

The local `retrying_server.py` adapter regenerates all configured pages every
30 minutes by default, independently of the upstream client wake schedule.
Change it under Program settings on port 8001 (15 minutes to 24 hours).
It reads `server_refresh_seconds` from the control API every 15 seconds, retains
the last interval during outages, and skips missed slots after slow renders.
The existing regeneration lead (120 seconds) is retained: a 30-minute interval
starts at :28 and :58. A running generation completes before another starts.
For containers or a nonstandard control port, set `NOOK_SETTINGS_URL` to the
reachable settings endpoint (default `http://127.0.0.1:8001/api/settings`).
The initial startup render and existing retry behavior remain in place.
