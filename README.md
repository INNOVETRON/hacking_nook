<div align="center">

# hacking_nook

**A 2011 Nook Simple Touch, turned into a wall dashboard.**

A Raspberry Pi draws the page. The Nook fetches it, displays it, and sleeps.
No cloud, no subscription, no API keys.

<img src="docs/images/page-today.png" width="260" alt="Today view: a line-art map of the city, the temperature, and a chance-of-precipitation chart">

</div>

---

## The hardware

<table>
<tr>
<td width="50%" align="center">
<img src="docs/images/nook-photo.jpg" width="300" alt="Nook Simple Touch e-reader"><br>
<b>Nook Simple Touch</b><br>
<sub>~$30 used · 6" e-ink, 800×600<br>Android 2.1 · weeks on a charge</sub>
</td>
<td width="50%" align="center">
<img src="docs/images/pi-photo.jpg" width="300" alt="Raspberry Pi Zero 2 W board"><br>
<b>Raspberry Pi Zero 2 W</b><br>
<sub>512 MB RAM · draws the pages<br>Any Pi works; this is the tight case</sub>
</td>
</tr>
</table>

> Stock photographs, not this build, Credits at the bottom.

## The pages

Four views. Which one shows depends on the time of day, and on whether the
weather is about to do something you should know about.

<table>
<tr>
<td align="center"><img src="docs/images/page-today.png" width="180" alt="Today"><br><b>today</b><br><sub>09:30 – 17:00</sub></td>
<td align="center"><img src="docs/images/page-hourly.png" width="180" alt="Hourly"><br><b>hourly</b><br><sub>06:00 – 09:30</sub></td>
<td align="center"><img src="docs/images/page-daily.png" width="180" alt="Daily"><br><b>daily</b><br><sub>17:00 – 21:00</sub></td>
<td align="center"><img src="docs/images/page-tomorrow.png" width="180" alt="Tomorrow"><br><b>tomorrow</b><br><sub>21:00 – 06:00</sub></td>
</tr>
</table>

**If the weather is about to turn, it switches to `hourly` regardless of the
clock** — rain or snow starting, rain turning to snow, a thunderstorm, crossing
freezing, a big temperature swing, wind picking up. Those are the times you want
to know *when*, and `hourly` is the page that says so.

A gradual drift does not interrupt. Cloud thickening, or two degrees over six
hours, is what the day view already shows.

**`today` and `tomorrow` each carry a chance-of-precipitation chart** across the
lower half — the next nine hours, and tomorrow's daytime.

## How it fits together

```
Raspberry Pi                                     Nook Simple Touch
┌──────────────────────────────────────┐         ┌──────────────────┐
│ weather-cal  :8082                   │         │ NookPanel app    │
│   draws 4 pages, once an hour        │  wifi   │   fetches every  │
│              │                       │ ──────► │   5 min, shows   │
│              ▼                       │         │   it fullscreen, │
│ nookpanel    :8000                   │         │   then sleeps    │
│   picks the page, serves the PNG     │         └──────────────────┘
└──────────────────────────────────────┘
```

Both services run **on the Pi**. Nothing else is involved once deployed.

- **weather-cal** is [chrisjtwomey/inkplate10-weather-cal](https://github.com/chrisjtwomey/inkplate10-weather-cal)
  run as-is, with one file swapped so the map comes from OpenStreetMap instead
  of Google Static Maps. It renders HTML in headless Chromium — slow, hence
  hourly.
- **nookpanel** decides which page to show, on every refresh. Fast, hence every
  5 minutes. If a render fails it keeps serving the last good image; if there
  has never been one, it draws a simpler page itself. **The panel never goes
  blank.**
- **NookPanel**, the app, is ours — built for Android 2.1, which nothing modern
  can target.

Everything restarts on boot — see [Auto-start](#auto-start) below.

## Set up the Pi

Raspberry Pi OS, any model. Tested on a Zero 2 W.

```bash
sudo apt install -y git
git clone --recurse-submodules https://github.com/AfshinKI/hacking_nook.git ~/hacking_nook
cd ~/hacking_nook

OSM_MAP_LABEL="Edmonton" ./upstream/install-on-pi.sh   # renderer (~10 min)
./server/install-on-pi.sh                               # panel server
```

That works as-is — the example config is Edmonton, so copy-paste gives you a
running panel. **For your own city**, edit the two files and restart:

```bash
nano server/config.json          # latitude, longitude, timezone
nano upstream/run/config.yaml    # location:, timezone:
sudo systemctl restart weather-cal nookpanel
```

Check it:

```bash
journalctl -u weather-cal -f
curl -o test.png http://localhost:8000/panel.png
```

### If the install stops on the first line

```
E: dpkg was interrupted, you must manually run 'sudo dpkg --configure -a'
```

A previous apt run on that Pi was interrupted, so every `apt-get` fails until
it is repaired. The installer now runs `dpkg --configure -a` itself before
touching apt, but on an older checkout, or if it fails for another reason:

```bash
sudo dpkg --configure -a       # can take several minutes on a Zero
sudo apt-get check             # should print nothing
```

then re-run the installer. It is safe to run more than once.

> Give the Pi a **DHCP reservation**. The Nook stores a literal URL, and typing
> one on an infrared touchscreen is miserable.

### Sharing a Pi with other services

Nothing here assumes a dedicated Pi. It uses **two ports, 8000 and 8082**, and
nothing else — no global Python packages (the renderer gets its own venv), no
changes to anything already installed.

```bash
ss -tlnp | grep -E ':8000|:8082'     # check they are free first
```

To move them, set `port` in `server/config.json` and `server.port` in
`upstream/run/config.yaml`, then point `renderer_url` at the new renderer port.

The one thing that is not free is **memory**. Chromium is the whole cost, and
the installer raises swap to 2 GB for it. On a 512 MB Pi already running
something substantial, expect the renderer to be slow rather than to fail —
each page takes about 40 seconds.

## Auto-start

Both installers register systemd units and enable them, so nothing needs doing
by hand. To confirm:

```bash
systemctl is-enabled weather-cal nookpanel     # both: enabled
systemctl is-active  weather-cal nookpanel     # both: active
```

If either says `disabled`:

```bash
sudo systemctl enable --now weather-cal nookpanel
```

### What happens after a power cut

| | |
|---|---|
| ~15 s | Pi boots, both units start |
| ~20 s | Panel serves a page it draws itself — the renderer is not up yet |
| ~3 min | Renderer finishes its four pages |
| ~5 min | Panel picks them up on its next refresh |

**The panel is never blank**, and no one has to touch anything. The first
couple of minutes show a simpler locally-drawn page.

### Wi-Fi is slower than systemd thinks

`NetworkManager-wait-online` reports the network up as soon as the link
associates — about two seconds on this Pi — which on Wi-Fi is well before DNS
resolves. The renderer geocodes your location at startup, so it used to die on
the first `Temporary failure in name resolution` and, with a long restart delay,
leave the renderer down for minutes.

The unit now waits for a name to actually resolve before starting:

```ini
ExecStartPre=/bin/sh -c 'for i in $(seq 1 60); do getent hosts api.open-meteo.com >/dev/null 2>&1 && exit 0; sleep 2; done; exit 0'
```

Bounded at two minutes, and it exits 0 either way, so a genuinely offline boot
still starts and retries rather than blocking forever.

### If it does not come back

```bash
systemctl status weather-cal nookpanel
journalctl -u weather-cal -b --no-pager | head -40    # this boot, from the top
systemd-analyze blame | head                          # what was slow
```

Do **not** `systemctl restart weather-cal` while it is mid-regeneration — two
Chromiums compete and Selenium times out at 120 s. Check for
`Starting http server` first, then `stop`, wait, `start`. Or just run
`./upstream/refresh-on-pi.sh`, which sequences it properly.

## Set up the Nook

1. **Root it** with NookManager from an SD card — [docs/02-rooting.md](docs/02-rooting.md).
   Run *Backup* from its menu before *Root*.
2. **Build and install the app.** Needs Docker on any x86_64 machine, once:
   ```bash
   cd app && make image && make debug
   adb install -r bin/NookPanel-debug.apk
   ```
3. **Point it at the Pi** over adb, not the touchscreen:
   ```bash
   ./tools/push-config.sh http://<pi-ip>:8000/panel.png 3600
   ```
4. It starts itself on boot and ignores touch. Open `http://<pi-ip>:8001/`
   for program schedules and displayer refresh settings. Changes arrive on the
   next fetch. `./tools/screenshot.sh out.png` captures the display.

The Android 2.1 traps — and there are several — are in
[docs/06-our-own-app.md](docs/06-our-own-app.md).

## Change what it shows

| Want to | Where |
|---|---|
| Different page times | `page_schedule` in `server/config.json` |
| Turn off weather alerts | `"advisories": false` |
| Zoom or move the map | `OSM_MAP_ZOOM`, `OSM_MAP_CENTER` — [upstream/README.md](upstream/README.md) |
| Use your own map picture | `OSM_MAP_FILE=/path/to.png` |
| Skip weather-cal entirely | unset `renderer_url`; `server/` draws simpler pages itself |

## Layout

```
app/         NookPanel — our Android 2.1 client
server/      picks and serves the page; can also draw its own
upstream/    weather-cal: the OSM map shim, patches, Pi installer
tools/       flash an SD card, push config, screenshot the panel
docs/        how it was built, and a full lab log
external/    upstream projects as submodules — never edited in place
```

The [lab log](docs/99-lab-log.md) records what actually happened, including the
dead ends. Start at [docs/README.md](docs/README.md).

## Third-party code and data

Nothing is vendored — upstream projects are submodules, so this repo carries
only pointers and our own code.

| What | Licence |
|---|---|
| `inkplate10-weather-cal` — run, plus patches in `upstream/patches/` | MIT, © 2023 Chris Twomey |
| `trmnl-nook-simple-touch`, `Nook-weather-NWS` — reference | MIT |
| `nook-dashboard`, `NookManager` — reference | no licence stated upstream |
| Map data in the sample images and at runtime | © OpenStreetMap contributors, [ODbL](https://www.openstreetmap.org/copyright) |
| `app/res/drawable-*/ic_launcher.png` — Android SDK template | Apache-2.0 |
| Comic Neue — installed from Debian, not vendored | SIL OFL |
| [`docs/images/nook-photo.jpg`](https://commons.wikimedia.org/wiki/File:Nook_Simple_Touch.jpg) — Tthaas | CC BY-SA 3.0 |
| [`docs/images/pi-photo.jpg`](https://commons.wikimedia.org/wiki/File:Raspberry_Pi_Zero_2_W_--_2024_--_0008.jpg) — Anil Öztas | CC BY 4.0 |

Rooting images and device backups are **not** in this repo, and must not be.
