# 99 — Lab log

Append-only. One entry per session. Record what was *actually done*, what broke,
and the exact commands — future-us will not remember.

Template:

```
## YYYY-MM-DD — <what we tried>
Device: BNRV3xx, FW x.x.x, rooted via <method>
Goal:
Did:
Result:
Broke / gotchas:
Next:
```

---

## 2026-09-06 — Project kickoff (no hardware touched)
Device: not yet identified — need model + firmware from Settings → Device Info
Goal: survey the ecosystem, decide an approach, set up the repo
Did: web research (see [01-research-landscape.md](01-research-landscape.md)),
created this repo, docs, the `nook-nst` skill, and submodules under `external/`
Result: plan is Phoenix phase 4 root → server-rendered 800×600 dashboard →
our own API-7 client. Native Linux / postmarketOS ruled out (no port exists).
Broke: nothing. XDA blocks scripted fetching, so the Phoenix thread must be read
manually in a browser.
Next: read Settings → Device Info on the actual Nook and fill in model +
firmware here; download the matching Phoenix phase-4 image; make a backup.

## 2026-09-06 — Toolchain proven, NookPanel v0.1, server rendering
Device: **BNRV300, FW 1.2.2** (confirmed by owner). Not yet rooted, not yet
visible over USB.
Goal: stand up both halves of the "server renders, Nook displays" design without
needing the device.
Did:
- Checked USB: `lsusb` shows **no vendor 2080 device** and `lsblk` shows no ~2 GB
  volume, so the Nook is not enumerating. `adb` is also not installed on the
  workstation. See [07-hardware-checklist.md](07-hardware-checklist.md).
- Built a pinned **2014 ADT bundle container** (`app/tools/Dockerfile`) and
  proved an API-7 APK builds: 45 KB, `aapt dump badging` reports
  `sdkVersion:'7' targetSdkVersion:'7'`.
- Wrote **NookPanel v0.1** (`app/`): fullscreen fetch-and-display, settings
  screen, tap menu.
- Wrote the **dashboard server** (`server/panel_server.py`): Open-Meteo weather,
  no API key, renders 600×800 greyscale PNG, ~20 KB. Verified a live render.
Result: both halves work on the workstation. Only the device is blocking.
Broke / gotchas:
- ADT bundle files unpack root-only → `chmod -R a+rX` in the Dockerfile, else
  running the container as your UID fails with "Permission denied".
- JDK 8 required; newer JDKs break the 2014 Ant scripts.
- A `docker run -v $PWD/app:...` against a non-existent path creates it **owned
  by root**. Create host directories before mounting.
Next:
1. Work out why the Nook is not enumerating over USB (charge-only cable?).
2. `sudo apt install android-tools-adb`.
3. Source a 2–32 GB microSD card — **hard blocker for rooting**.
4. Download `NST_Phase4_122.zip` from the Phoenix Project thread.

## 2026-09-06 — Server live on the Pi Zero 2 W
Host: `pi2` → **raspi-dev**, 192.168.4.42, Raspbian bookworm (armv7l),
Python 3.11, 425 MB RAM, 24 GB free.
Goal: get the dashboard server running as a service on the Pi.
Did:
- Surveyed the Pi first. It already runs an unrelated service of its own on
  **port 5050**. Our server uses 8000, so **there was no need to disable
  anything** — both run side by side.
- The repo is public, so the Pi clones over **HTTPS**; its `id_rsa` is not
  registered with GitHub and does not need to be.
- Wrote `server/install-on-pi.sh` (idempotent) instead of the hardcoded systemd
  unit, and ran it: installs `python3-pil` + `fonts-dejavu-core` from apt,
  generates the unit for the invoking user and clone path, enables and starts it.
- Config set for **Edmonton** (53.5461, -113.4938, America/Edmonton, metric).
Result: `curl http://192.168.4.42:8000/panel.png` → **HTTP 200, 19,755 bytes,
600×800 8-bit greyscale, 42 ms**. Live local weather and correct local time.
The Pi's own service on 5050 still answers 200.
Broke / gotchas:
- Pillow must come from **apt**, not pip — bookworm is PEP 668
  externally-managed, and compiling Pillow on a Zero 2 W takes ~an hour.
- `server/config.json` is gitignored, so `git pull` on the Pi will never clobber
  the local settings.
Next:
- Give the Pi a **DHCP reservation** for 192.168.4.42. The Nook stores a literal
  URL and re-typing it on an infrared touchscreen is miserable.
- Still blocked on the Nook itself: USB enumeration, adb, and a microSD card.
Update the Pi with:
```
cd ~/hacking_nook && git pull && sudo systemctl restart nookpanel
```

## 2026-09-06 — Nook enumerating; user data backed up
Device: BNRV300, FW 1.2.2, **not rooted**, connected over USB.
Goal: get the device visible and preserve anything we could lose.
Did:
- `lsusb` now shows `ID 2080:0003 Barnes & Noble NOOK Simple Touch`. The earlier
  invisibility was the cable/connection, as suspected.
- Two volumes appear: `/dev/sdc` 240 MB `NOOK` (internal user partition) and
  `/dev/sdd` 1.8 GB `NOOGIE` (the 2 GB microSD in the device).
- The SD card is labelled `NOOGIE` — the classic NST rooting image — but holds
  only `System Volume Information`. Previously used with noogie, since wiped.
  **Free to reuse.**
- Copied both volumes to `backups/2026-09-06/` (41 MB + 40 KB, gitignored).
  Includes `.devicesalt` and `.adobe-digital-editions/activation.xml`, which are
  device-identity files worth keeping.
- Wrote `tools/flash-sd.sh`: refuses non-removable, non-USB, partition-rather-
  than-disk, and >64 GiB targets, and requires retyping the device name.
Result: device confirmed healthy and stock; user data safe.
Broke / gotchas:
- **The rooting image cannot be fetched automatically.** `doozan.com` returns
  404, GitHub has no release assets, and the 1.2.2-capable images are XDA
  attachments / in-post Dropbox links behind Cloudflare and a login.
- Building NookManager from source is also a dead end: its readme requires a
  **32-bit Linux host** and `build.sh` downloads a 2013 Buildroot from dead URLs.
- `adb` still not installed locally (needs sudo). Not urgent — stock NST has ADB
  disabled anyway; it only matters after rooting.
Next:
1. **Download a 1.2.2-capable rooting image by hand** into `downloads/`.
2. Move the SD card into the USB card reader.
3. `./tools/flash-sd.sh downloads/<image>.img /dev/sdX`
4. Power the Nook off, insert card, power on, take the full backup from the
   tool's own menu *before* rooting.

## 2026-09-06 — NookManager 1.2.2 image obtained and verified
Goal: get a rooting image that works on FW 1.2.2.
Decision: **NookManager in-place root**, not Phoenix phase 4. This device has the
owner's library, its own B&N registration and an Adobe DE activation; Phoenix
restores someone else's CWM image and would wipe all three. Phoenix stays as the
fallback if NookManager fails.
Did:
- Plain HTTP clients get 403 from XDA (Cloudflare). The in-app browser loaded the
  thread fine, which surfaced smjohn1's Dropbox link.
- Downloaded `downloads/NookManager1.2.2.img`, 67,092,480 bytes,
  sha256 `f33aca9eb9bc256e07399500c2a939815ca421ae090db265bbb98a5b63cc0253`.
- Verified without mounting (no sudo) by walking the FAT32 root directory in
  Python: unpartitioned FAT32, label `NookManager`, containing
  `custom/ files/ hooks/ menu/ scripts/` — an exact match for doozan's upstream
  tree in `external/NookManager/NookManager/` — plus `MLO` (OMAP first-stage
  bootloader) and `BOOT.SCR`.
Result: image in hand and plausible. Not yet written to the card.
Next:
1. Move the SD card from the Nook into the USB card reader.
2. `lsblk` to identify it, then
   `./tools/flash-sd.sh downloads/NookManager1.2.2.img /dev/sdX`.
3. Nook **powered off** → insert card → power on.
4. **Backup first** from NookManager's own menu, then Root, then enable ADB.

## 2026-09-06 — NookManager hangs at "loading..."; root-caused
Symptom: card written with `tools/flash-sd.sh`, Nook boots, shows the
**NookManager splash and "loading..."**, then nothing. Ever.
Did:
- Ruled out a bad write: the card came back labelled `NookManager` with `MLO`,
  `boot.scr`, `uImage`, `uRamdisk`, and the `custom/ files/ hooks/ menu/
  scripts/` tree all present and correct.
- Extracted the boot ramdisk to read what runs after the splash: stripped the
  64-byte u-boot header off `uRamdisk`, `gunzip`, `cpio -idm`.
- `init.rc` starts `/sbin/system_ready`, which does
  `mount -t vfat -o ro /dev/block/mmcblk1p1 /sdcard`, rsyncs the SD's scripts to
  `/tmp/sdcache`, then runs `/tmp/sdcache/hooks/system_ready` — the hook that
  draws the menu.
- Parsed sector 0 of the downloaded image: boot signature `55aa`, OEM id
  `mkdosfs`, **all four MBR partition entries zero**. It is a bare FAT32
  *filesystem* image, not a whole-disk image.
Root cause: written to the whole disk, the card has no `mmcblk1p1`. The mount
fails silently, `/tmp/sdcache` stays empty, the menu hook never runs, and e-ink
holds the last frame — so a fully-booted device looks frozen.
u-boot boots anyway because `fatload mmc 0` reads a filesystem at sector 0.
`scripts/format_unused_sdcard` corroborates the intended layout: p1 = NookManager,
p2 = created later in free space for `backup.full.gz`.
Fix: `tools/flash-sd.sh` now detects a missing partition table, writes an MBR
(`63,131040,c,*` — 63 MiB FAT32 LBA, bootable) and dd's the filesystem into
**p1**. On this 2 GB card that leaves ~1.75 GB free, ample for the backup.
Also worth knowing: `init.rc` sets `persist.service.adb.enable 1` and runs
`adbd`, so **NookManager itself serves ADB over USB**. That is the way to tell
"hung" from "booted but not drawing" next time — check `adb devices`.
Next: re-flash with the fixed script, boot, expect the "Enable Wireless?" prompt.

## 2026-09-06 — Rooted, app installed, dashboard rendering on the panel
Device: BNRV300, FW 1.2.2, **rooted** via NookManager 1.2.2 (after the
partition-table fix). Wi-Fi 192.168.4.78.
Result: **end-to-end working.** The Pi renders, the Nook fetches and displays.
Did:
- Confirmed root: `adb shell id` → `uid=0(root)`. adbd runs as root
  (`ro.secure=0`), so no `su` dance is needed for tooling.
- NookManager also installed ReLaunch (`com.harasoft.relaunch`), ADBKonnect,
  Superuser (`com.noshufou.android.su`) and **NTMM** (`org.nookmods.ntmm`).
- Nook pings the Pi; Pi's log shows `192.168.4.78 "GET /panel.png" 200`.
- Wrote `tools/screenshot.sh` — Android 2.1 has no `screencap`, so it dd's
  `/dev/graphics/fb0` (600x1600 virtual = two 600x800 pages, 16 bpp RGB565,
  stride 1200) and converts the first page with Pillow.
- Wrote `tools/push-config.sh` to set the image URL over adb instead of typing
  it on the infrared touchscreen.
- Enabled ADB over Wi-Fi: `adb tcpip 5555` → `adb connect 192.168.4.78:5555`.
Gotchas, all of which cost time:
- **Android 2.1's toolbox is threadbare.** No `ls -ld`, no `mkdir -p`, no
  `am force-stop`; `chown` wants `user.group`. Use `/system/xbin/busybox` for
  anything touching the filesystem, and `busybox pkill` instead of force-stop.
- **`adb shell "cat > file"` hangs forever** — adb never forwards EOF, so cat
  waits for input that cannot arrive. Write locally and `adb push`.
- **`INSTALL_PARSE_FAILED_INCONSISTENT_CERTIFICATES` on every reinstall.** The
  container regenerated `~/.android/debug.keystore` each build. Fixed by
  mounting a persistent `app/.androidhome`. It must be mounted at
  **`/home/ubuntu`** specifically: Ant's DebugKeyProvider asks the JVM for
  `user.home`, which comes from `/etc/passwd` (uid 1000 = `ubuntu`) and ignores
  `$HOME`. `keytool` also will not create `.android/`, so the Makefile does.
- **A docker `-v` against a non-existent host path creates it owned by root.**
  Bit us twice now.
- **"USB Mode" hides everything.** Connect the Nook to a PC and B&N's fullscreen
  USB activity comes to the front, pausing our app — so it stops fetching, by
  design. Verify over Wi-Fi ADB with the cable out, or on a charger.
App fix: `onResume` used to refetch unconditionally, so anything stealing focus
(the USB dialog, repeatedly) triggered a fetch and an e-ink refresh — 3 requests
in 30 s against a 300 s interval. It now only fetches if the current image is
actually older than the interval.
Next:
1. Unplug USB, confirm the panel displays unattended.
2. v0.2 deep sleep — see [06-our-own-app.md](06-our-own-app.md).
3. Still open: was a full backup taken from NookManager's menu before rooting?

## 2026-09-06 — "where is the app?" — the stock home has no app drawer
Symptom: NookPanel installed and running, but invisible in the Nook's own
application list.
Cause: not a bug. `com.bn.nook.home` only lists B&N content — there is no
general app drawer, so sideloaded APKs never appear. That is precisely why
NookManager ships **ReLaunch** (`com.harasoft.relaunch`, launcher activity
`com.harasoft.relaunch.Main`).
Did: added `BootReceiver` (`RECEIVE_BOOT_COMPLETED`) so the panel starts itself
after boot when a URL is configured — the right behaviour for a wall display,
and it sidesteps the launcher question entirely.
Verified: reinstall succeeded **in place** (the persistent keystore fix holds),
app relaunched, Pi logged the fetch, and a framebuffer capture shows the
dashboard with the tap menu over it.
Note: `adb` over Wi-Fi drops out when the device sleeps; `adb connect` then
blocks rather than failing fast. Wrap it in `timeout`.

## 2026-09-06 — Panel redesigned after inkplate10-weather-cal
Goal: match the look of Chris Twomey's
[inkplate10-weather-cal](https://github.com/chrisjtwomey/inkplate10-weather-cal)
(the dashboard from the Tom's Hardware piece).
Did: split the renderer into `weather / mapview / icons / layouts / fonts` and
added a `today` layout — pale city map fading to white, big outlined weather
icon straddling the fade, date / temperature / conditions in rounded
hand-lettering, oversized ghost icon watermarked into the bottom corner. The old
dense view is still there as `layout: "simple"`.
Findings:
- **CARTO `light_all` now requires an API key** — anonymous tiles come back as a
  watermarked "API KEY REQUIRED" image, which silently looks like a rendering
  bug. **Wikimedia** (`maps.wikimedia.org/osm-intl`) returns **403** to third
  parties. Standard **OpenStreetMap** tiles still work keyless, so we greyscale
  and lighten those instead. Fetched **once per location** and cached in
  `server/.cache/`, which keeps us inside OSM's usage policy.
- **Icons are drawn, not downloaded.** Draw the silhouette into a mask, dilate
  it for the outline, then paint white inside and black in the ring — that gives
  one clean edge around the *union* of a cloud's lobes instead of visible seams.
  Chunky outlines also survive 16 grey levels far better than detail.
  Watch the dilation: it eats roughly `2 * stroke` of any gap, which merged the
  fog bars and turned snowflakes into blobs until they were respaced.
- **Font:** `fonts-comic-neue` is the closest rounded hand-lettered face in
  Debian. `fonts-humor-sans` has no `all.deb` under the pool path guessed, so it
  was skipped. For local dev without root, `dpkg-deb -x` the .deb into
  `~/.local/share/fonts`.
Deployed: Pi pulled, `fonts-comic-neue` installed, service restarted, and the
Nook fetched the new image (`192.168.4.78 "GET /panel.png" 200`).
Gotcha: **`adb tcpip 5555` does not survive a reboot.** After the power-cycle
test the port was closed. Re-enable by plugging USB and running `adb tcpip 5555`
again, or use **ADBKonnect** on the device.
Next: look at it on the actual panel — `map_zoom` and the lightening factor in
`mapview.py` are the two knobs if the map reads as mud or as invisible.

## 2026-09-06 — Hourly layout; the map was washed out because OSM is light-themed
Ask: match the reference project's **hourly** page, and fix the pale map.
Did: added `external/inkplate10-weather-cal` as a submodule and read
`server/views/hourly.py` + `detailed.css` for the real layout rules.

**Why "use the repo directly" does not work here.** Upstream renders **HTML in
headless Chrome** — Chart.js and rough.js draw the sketchy precipitation bars —
against AccuWeather/OpenWeatherMap plus Google Static Maps. Chromium will not
fit in a Pi Zero 2 W's 425 MB alongside anything else, and all three services
want API keys. So the *design* is ported to Pillow against keyless Open-Meteo
and OSM, following upstream's rules exactly:
- hour labels on every second column; temperatures and wind speeds suppressed
  when they repeat the previous column
- wind arrow size `16 + 14 * min(kmh/80, 1) ** 0.5`, rotated `(deg + 180) % 360`
  because Open-Meteo reports where the wind comes *from*
- precipitation labels only on even columns, skipped when repeated, and hidden
  above 80% where they would clip

**Root cause of the washed-out map:** OSM's standard layer is *light-themed* —
land and buildings are essentially white and only thin lines are dark. No tone
curve fixes that, because darkening the land darkens the roads with it, and
`autocontrast` is a no-op since road labels already reach black. **Inverting**
gives exactly what the reference's custom dark Google style does: dark land and
water, light roads and labels. Now `map_style` ("light"/"dark") plus a
`map_strength` knob, defaulting to 0.70 for `hourly` and 0.55 for `today`.

Other notes:
- The fade mask is left+bottom for `hourly`, to clear a white margin for the
  overlaid badges. The left edge uses a **square-root** falloff — the quadratic
  used at the bottom keeps the map dark until the last few columns.
- Precipitation bars scale to the wettest hour in the window with a **floor of
  40%**, so a dry day still draws a chart instead of a flat line. Every bar
  carries its true percentage, so nothing is hidden.
- `wind_arrow` draws at 4x and downsamples: PIL has no anti-aliased polygons.
Deployed and verified: Pi renders `hourly` in ~1.5 s, 101 KB.

## 2026-09-06 — Running the real upstream server, with one file swapped
Decision: use upstream's own renderer rather than our port, patching out its
only hard blocker. Measured facts that shaped it:
- Upstream renders **HTML in headless Chromium via Selenium**; the published
  image `ghcr.io/chrisjtwomey/inkplate10-weather-cal-server` is **linux/amd64
  only and 1.4 GB**, so it cannot run on the Pi Zero 2 W (armv7l, 425 MB).
- **Weather needs no key**: upstream ships an `openmeteo` provider. Its config
  loader still requires a `weather.apikey` to be present — a placeholder does.
- **Google Static Maps is a hard requirement.** `server.py:206` constructs
  `GoogleAPIService(cfg.google_apikey)` unconditionally and dies with
  `ValueError: Invalid API key provided.` before rendering anything.
Did: `upstream/google_api_shim.py` replaces `google/api.py` with the same class
and the same contract — `get_static_map_local_src(map_id, location)` writes a
PNG under `views/html/map-cache/` and returns the path relative to
`views/html/` — backed by OSM tiles and Open-Meteo geocoding. Our
`server/mapview.py` is copied into the image as `nook_mapview.py`, so the tile
code is shared rather than duplicated. `upstream/Dockerfile` layers both onto
upstream's image; nothing else is modified.
Result: all five pages render at 600×800 with no API keys at all.
Findings:
- `image.width/height` are configurable, so it renders **natively** at our
  resolution — no resize step needed.
- Upstream quantises to **4 grey levels with Floyd–Steinberg** by default
  (`epd_server/quantise.py`). The NST has 16, so there is headroom if the
  dithering ever looks too noisy.
- `hourly.py` sizes the wind arrows in raw `vw` while the rest of the layout
  uses `--inner-vw`. When `innerWidth != width` those diverge and the table
  overflows. Keeping them equal (600/600) avoids it, which is the config we run.
- Zoom 11 was too far out to read; **13** shows the river valley and downtown.
Also added `mirror_url` to `server/panel_server.py`: with it set, the Pi stops
rendering and instead fetches that URL on its timer, **keeping the last good
image** if the fetch fails. That is how the desktop-only container feeds the
always-on Pi without the panel breaking when the desktop is off.

## 2026-09-06 — Line-art map drawn from OSM vector data
Ask: make the map look like a printed street-map poster — black streets on
white, solid black river.
Constraint: the two reference pictures supplied were a watermarked Alamy stock
photo and a Redbubble print listing. Both are copyrighted artwork, so neither
could be used. The *style* is reproducible from open data, so that is what we
built.
Did: `server/linemap.py` queries the **Overpass API** for road and water
geometry in a bbox and draws it — roads as black lines weighted by class, water
as solid black — at 2x, downsampled for anti-aliasing (PIL has no anti-aliased
lines). Optional place-name plate, as on the posters.
Why not a tile server: every black-and-white raster basemap that served this
style is gone. Stamen Toner moved to Stadia and needs a key,
`tiles.wmflabs.org/bw-mapnik` no longer resolves, Tracestrack 403s. Esri's
World Light Gray Canvas is keyless and close to the *light* reference, but its
water is light grey where the reference is dark.
Gotcha worth remembering: Overpass returns a water **relation**'s outer
boundary as separate ways in arbitrary order and direction. Filling each one on
its own closes an open line across the whole map — the North Saskatchewan came
out as a black band from corner to corner. `_stitch_rings` chains members
end-to-end and keeps only rings that actually close.
Cost: one query per location, ~34,000 elements and ~13 s for Edmonton at zoom
12, then cached as JSON and as a PNG. Overpass is a shared free service — never
poll it.
This is also the right choice for the panel: 16 grey levels, and upstream
dithers to 4, so pure black on white has nothing to dither. `lineart` is now the
default style.

## 2026-09-06 — Upstream's renderer running natively on the Pi Zero 2 W
Goal: stop depending on the desktop. Run upstream's Chromium-based renderer on
the always-on Pi.
Key finding: **Docker was the blocker, not the hardware.** Raspberry Pi OS ships
`chromium` and `chromium-driver` in apt (152.x), so a venv against those avoids
both the amd64-only image and a container runtime we cannot spare 425 MB for.
`upstream/install-on-pi.sh` does it all; see `upstream/README.md`.
Measured on the Pi:
- Overpass fetch + line-art draw: **77 s**, once, then cached.
- Chromium render: **~35-45 s per page**, stable, **no OOM**.
- All five pages: ~3 min. With the page-filter patch, **one page: ~30 s**.
- Memory at rest with all three services up: 122 MB of 425 used, 57 MB swap.
What it took:
- **Swap 512 MB → 2 GB.** `dphys-swapfile` also caps at `CONF_MAXSWAP`, which
  has to be raised too or `CONF_SWAPSIZE` is silently ignored.
- **Pillow and PyYAML from apt, not pip** — no armv7 wheels, and building them
  here takes about an hour. venv created with `--system-site-packages`.
- Upstream's exact version pins relaxed, for the same reason.
Two bugs worth remembering:
- `server.py` line 30 sets `cwd = os.path.dirname(os.path.realpath(__file__))`,
  and reads `config.yaml` from there. There is no `--config` flag, so systemd's
  `WorkingDirectory` does nothing. The real config lives in `upstream/run/` and
  is symlinked into the submodule.
- `server.py` builds **all five pages unconditionally**, ignoring the schedule's
  pools, so every regeneration launched Chromium five times.
  `upstream/patches/0001-render-only-scheduled-pages.patch` filters them.
  Applied with `git apply`, so it fails loudly if upstream moves the code.
- `git -C <dir> apply <patch>` resolves the patch path **relative to `<dir>`**,
  not the shell's cwd. Pass an absolute path or it silently does nothing.
Wiring: `weather-cal` on :8082 renders; `nookpanel` on :8000 mirrors
`127.0.0.1:8082/hourly.png` and keeps the last good copy; the Nook is unchanged.
The Pi's pre-existing service on :5050 is still untouched.
Regeneration now runs every two hours.

## 2026-09-07 — Page rotation by time of day, with a weather override
Design: the Nook polls our mirror every 5 minutes, but upstream regenerates
hourly. So the *choice* of page belongs in the mirror, not in upstream's
schedule — `server/pagechoice.py`.

Schedule: `06:00` hourly, `09:30` today, `17:00` daily, `21:00` tomorrow.
09:30 rather than 10:00 because by then the hourly page's first columns are
already behind you.

Advisory override — **change of kind, not of degree**. Switches to `hourly` for
precipitation starting (dry now, ≥50% ahead), rain↔snow, thunderstorm, crossing
freezing, an 8°+ swing, or wind past 40 km/h. Deliberately silent on cloud
thickening or a couple of degrees of drift: that is what the day view already
shows. Suppressed 22:00–06:00.
Verified each branch against synthetic hourly data, and the negative cases
("steady overcast", "already raining, steady", "gradual 3° drift") correctly do
not fire. Against Edmonton live it also stayed on `today` — 11-20% drizzle is
exactly the gradual case.

### Incident: blank panel, and a Chromium crash loop
Restarting `weather-cal` twice in quick succession left the first regeneration
still running. Two Chromiums competed and **Selenium's webdriver connection
timed out at 120 s** — a limit `epd_server.render` does not expose. The service
exited 1 and, with `RestartSec=30`, began a crash loop of ~3-minute attempts.
Worse: the mirror had **never** successfully fetched, so it served a zero-byte
PNG. The panel showed nothing.
Fixes:
- `Mirror._degrade()` — keep the last good image, and if there is none, render
  locally with our own Pillow renderer. A cold start against a dead upstream is
  no longer a blank screen.
- Unit: `RestartSec=120`, `TimeoutStopSec=90`, `KillMode=control-group`, so a
  dying run takes its Chromium children with it and does not tight-loop.
- Operationally: never `systemctl restart weather-cal` mid-regeneration. Check
  `journalctl -u weather-cal -n 5` for "Starting http server" first, then
  `stop`, wait, `start`.
Cost of four pages: ~2.5 min of Chromium per regeneration, hourly. Memory held
at ~107 MB of 425 with 47 MB swap.

## 2026-09-07 — "Mirror" was a misleading name
It described a loopback fetch, but it read as "fetches from another machine",
which is the opposite of the deployment. Renamed:
- class `Mirror` → `RenderedPages`
- config `mirror_base` → `renderer_url` (old keys still honoured)
Both services are on the Pi. `renderer_url` is `http://127.0.0.1:8082`.

The split is not a network dependency, it is a division of labour: weather-cal
redraws once an hour (~2.5 min of Chromium for four pages), while the panel
server decides which page to show on every 5-minute refresh.

Verified the Pi is self-contained: the only URL in any config is
`http://127.0.0.1:8082`, and both endpoints answer with the desktop's
development container removed entirely.

Hardened "keep the previous render until a new one succeeds": every fetched page
is now **fully decoded** before being served. The PNG magic bytes alone pass a
file that was interrupted part-way through writing; `Image.open(...).load()` is
the certain check. Tested against a complete PNG, a truncated one, a bare
header, and an HTML error body — only the first is accepted. On any failure the
previous good image keeps being served, and on a cold start with no previous
image the panel server draws the page itself.

## 2026-09-07 — Reboot test, and the cold-start handover
Verified startup by actually rebooting the Pi rather than trusting
`is-enabled`. All three units came back on their own within 30 s.
Added `After=weather-cal.service` to the panel unit — ordering only, not a
`Wants=`, because the panel runs perfectly well alone by drawing its own pages.

The cold start exercised the fallback for real, which is the sequence worth
keeping:

| Time | What happened |
|---|---|
| 10:34:56 | panel starts, renderer not up yet → `Connection refused` |
| 10:34:58 | panel draws the page itself — **valid image 22 s after power-on** |
| 10:38:26 | renderer finishes all four pages (~3.5 min from boot) |
| 10:40:12 | next refresh picks it up: `serving today (50761 bytes)` |

So a power cut costs the panel about 20 seconds of nothing, then a simpler
locally-drawn page for four minutes, then the full one. It never shows a blank
screen and never needs a human.

README rewritten as a setup guide: architecture diagram, Pi setup from a bare
OS, Nook setup from an unrooted device, and a table of what to change to alter
what it shows.

## 2026-09-07 — Precipitation chart on the today page
Ask was "the daily view's bottom half is almost empty". The five-day **daily**
page is actually dense — rows of icon, temperature bar, precipitation, wind, sun
hours, sunrise/sunset and UV. The page with the empty lower half is **today**,
which is also the one on screen 09:30-17:00. Built it there.

`upstream/patches/0002-today-precipitation-chart.patch`:
- adds an `_extra_body(a, **kwargs)` hook to `SimplifiedPage` so `TodayPage` can
  append to the content section without reimplementing the whole template
- adds `hourly_forecasts` to `TodayPage.requires`, which is how the pipeline
  knows to supply it
- draws nine hours of precipitation probability as hatched bars

**Inline SVG, not canvas + rough.js.** The hourly page draws its bars in a
canvas on `window.onload`; that races the screenshot, and a page that renders
half-drawn is worse than one that is plain. SVG needs nothing to run, and the
hatch is a `<pattern>` rather than a library.

Two things that needed a second pass:
- `preserveAspectRatio="none"` stretches the viewBox, which shears text with it.
  `vector-effect: non-scaling-stroke` on the text elements fixes it.
- A fixed 0-100% axis made a 20% day read as a flat line under a lot of empty
  space — the same mistake as the Pillow hourly layout. It now scales to the
  window's peak, rounded up to a tidy step and floored at 40%, **with the top of
  scale printed** so the auto-scaling is visible rather than misleading. Every
  bar keeps its true percentage.

Deployment note: `git apply` a patch that is already applied fails, which is
correct but reads as an error in a loop over all patches. Check the tree for a
marker string rather than trusting the exit code.

## 2026-09-07 — Precipitation chart on tomorrow too; README photographs
`hourly_forecasts` is "the next N hours from now", so on the tomorrow page —
shown 21:00-06:00 — it would have charted the overnight, not tomorrow. Added a
**`tomorrow_hourly`** dataset instead: 06:00-21:00 every two hours. It is
**concrete and returns `[]` on the base `WeatherService`**, overridden for
Open-Meteo, which already fetches a multi-day hourly array. Making it abstract
would have broken every other provider the moment a page listed it in
`requires`; this way they just yield no chart.
The chart itself moved into `SimplifiedPage._precip_chart` so both pages share
one implementation.

README photographs: Wikimedia Commons, licences checked —
[Nook Simple Touch](https://commons.wikimedia.org/wiki/File:Nook_Simple_Touch.jpg)
by Tthaas (CC BY-SA 3.0) and
[Raspberry Pi Zero 2 W](https://commons.wikimedia.org/wiki/File:Raspberry_Pi_Zero_2_W_--_2024_--_0008.jpg)
by Anil Öztas (CC BY 4.0). Vendored with attribution rather than hotlinked;
both licences permit it, and links rot.

### Three mistakes, all mine, all worth remembering
- **The overlay is patches *and* a file copy.** `google/api.py` is installed by
  copying, not patching. Reverting the checkout so patches apply cleanly threw
  it away silently, and the renderer came up running upstream's Google code and
  died on `Invalid API key provided.` Now `upstream/refresh-on-pi.sh` does both
  and greps the result to prove the shim landed.
- **A helper that takes a `title` and then hardcodes the string.** The tomorrow
  page read "Chance of precipitation" instead of naming the day. Extracted code
  needs its parameters actually wired, not just accepted.
- **Fetching the sample images before the HTTP server was up truncated all four
  to zero bytes.** The `until` loop matched a stale log line. Fetch to a temp
  file, decode it, and only then move it into place — the same rule the panel
  server already follows for the pages it serves.

## 2026-09-07 — The renderer was dying at boot on DNS
Report: "I restarted the server, and it did not run again." True, and not a
matter of looking too early.

Boot before the fix:

| Time | |
|---|---|
| 13:21:47 | `weather-cal` started |
| 13:21:49 | `URLError: Temporary failure in name resolution` |
| 13:21:52 | **crashed** — upstream does not catch it, so the process exits |
| 13:25:11 | restarted, after `RestartSec=120` |
| 13:27:39 | serving — **six minutes after boot** |

Both units were correctly `enabled`. The cause was
**`NetworkManager-wait-online` returning in 2.077 s**: it reports the network up
when the Wi-Fi link associates, which is well before DNS resolves. The renderer
geocodes its location at startup, so it died on the first lookup. My
`RestartSec=120` then turned a two-second race into a six-minute outage.

Fix — wait for a name to actually resolve, rather than trusting the target:

```ini
ExecStartPre=/bin/sh -c 'for i in $(seq 1 60); do getent hosts api.open-meteo.com >/dev/null 2>&1 && exit 0; sleep 2; done; exit 0'
```

Bounded at two minutes and exits 0 either way, so a genuinely offline boot still
starts and retries instead of blocking. `RestartSec` 120 → 30. Both units also
order after `time-sync.target`: a Pi has no RTC, the clock jumps when NTP syncs
(`uptime -s` disagreed with the journal by a minute), and page selection is by
time of day.

Verified by rebooting again:

| Time | |
|---|---|
| 15:28:11 | both units started |
| 15:28:18 | panel drawing its own page — 7 s after boot |
| 15:31:31 | renderer finished all four pages |
| — | **0 tracebacks this boot** |

Lesson: `network-online.target` means "a link is up", not "the network works".
Anything that resolves a name at startup needs its own check.

README gains an **Auto-start** section: how to verify, the power-cut timeline,
why Wi-Fi is slower than systemd thinks, and what to run when it does not come
back.

## 2026-09-07 — Installing on a second Pi found two bugs, and adb now survives reboot
`nultra` (192.168.4.43) is the real deployment; `pi2` was a test box and is
being powered down. `nultra` also runs its owner's own services on **5050** —
ours use 8000 and 8082, the renderer has its own venv, and nothing global is
touched. The shared cost is memory, which is why swap goes to 2 GB.

### Why the install would not run
`E: dpkg was interrupted, you must manually run 'sudo dpkg --configure -a'`.
A previous apt run had left packages half-configured, so every `apt-get` failed
and the installer died on its first line — with an error that reads as if the
script produced it. Both installers now run `dpkg --configure -a` in a preflight
step; it is a no-op when nothing is pending, and took several minutes here
(pandas, matplotlib).

### Two bugs only a clean machine shows
- **The unit file was rejected.** `install-on-pi.sh` writes it from an
  **unquoted** heredoc, so the inline `sh -c` DNS wait had its `$(seq 1 60)`
  expanded *at install time*. The generated line read `for i in 1` and systemd
  refused the unit: `Unbalanced quoting`. `pi2` never saw it because its unit
  had been edited in place rather than generated. Now `upstream/wait-for-dns.sh`
  — a script has no quoting hazard and can be tested alone.
- **The generated config named only one page.** Pools listed `hourly`, a
  leftover from before the rotation, so `today`, `daily` and `tomorrow` returned
  **207-byte 404 bodies** and the panel fell back to drawing its own. Again,
  `pi2` worked only because those pools had been expanded by hand. The installer
  now writes all four plus a matching hourly schedule.

Verified end to end on a from-scratch install: all four pages render, and the
panel serves upstream's bytes — `panel b38a3a576882 == today b38a3a576882`.

### adb over Wi-Fi that survives a reboot
`tools/enable-adb-tcp.sh`. `adb tcpip 5555` sets the property on the running
system only; editing `/init.rc` is also useless because `/` is a **read-only
ramdisk** rebuilt from `uRamdisk` at every boot. `/data/local.prop` is read by
init before services start and `/data` persists, so the property sticks. The
rooter had already commented out adbd's `disabled` flag, so adbd always runs —
it only needed the port set.

Proof it is the property and not a leftover session: **58 s uptime, port already
5555**.

**Security:** adb on Android 2.1 predates RSA auth (4.2.2) and adbd runs as
root, so this is an unauthenticated root shell to anyone on the LAN. `--off`
reverses it.

Also worth remembering: **USB Mass Storage mode pauses the app.** The foreground
activity becomes `UMSServerActivity`, the panel stops fetching, and the e-ink
holds its last frame — which looks exactly like a stale or wrong page.

## 2026-09-12 — Keep the previous picture after a failed refresh
Device: BNRV300, FW 1.2.2 (confirmed via adb getprop), previously rooted.
Goal: stop failed image requests from replacing the dashboard with an error URL.
Did: changed PanelActivity to retain the existing bitmap on fetch failure and
continue normal scheduled retries. The error remains for an initial fetch with
no previous image. Updated the app README and layout comment. Built with
`cd app && make debug`; connected with `adb connect 192.168.4.78:5555`, installed
with `adb install -r app/bin/NookPanel-debug.apk`, and launched with
`adb shell am start -n com.hackingnook.panel/.PanelActivity`.
Result: build and in-place installation succeeded; activity confirmed resumed.
Broke / gotchas: adb emitted a temporary-file cleanup warning after reporting
installation Success. The retained image lives only in the current activity,
not across app restarts. A network failure was not deliberately induced on hardware.

## 2026-09-12 — Open the panel menu with a long press
Device: BNRV300, FW 1.2.2 (confirmed again via adb getprop).
Goal: prevent ordinary taps from opening Refresh now / Settings.
Did: replaced both picture and status click listeners with a shared long-click
listener that consumes the gesture. Updated waiting/error hints and app README.
Built with `cd app && make debug`, installed with
`adb install -r app/bin/NookPanel-debug.apk`, and launched with
`adb shell am start -n com.hackingnook.panel/.PanelActivity`.
Result: build and installation succeeded, launch accepted. Physical touch
behavior has not been manually verified.
Broke / gotchas: the same adb temporary-file cleanup warning followed Success.

## 2026-09-12 — Battery overlay on the loaded picture
Device: BNRV300, FW 1.2.2 (adb getprop); battery service reported 99%.
Goal: display the Nook battery level on the downloaded image.
Did: added a monochrome BatteryView in the top-right corner with fill level,
percentage, and a plus sign while charging. Subscribe to ACTION_BATTERY_CHANGED
while resumed and unregister on pause; redraw only when the displayed state
changes. The overlay is visible with a loaded or retained image and supports
the existing long-press menu. Updated the app README.
Validation: `cd app && make debug`, `git diff --check`,
`adb shell dumpsys battery`, `adb install -r app/bin/NookPanel-debug.apk`,
`adb shell am start -n com.hackingnook.panel/.PanelActivity`.
Result: build and in-place installation succeeded; launch accepted. Visual
placement and charging transitions have not been manually verified on the panel.
Broke / gotchas: adb still reports its temporary-file cleanup warning after Success.

## 2026-09-12 — Fix Settings crash after adding the battery resource
Device: BNRV300, FW 1.2.2 (confirmed via adb getprop).
Goal: restore Settings from the long-press menu.
Found: `adb logcat -d -v time AndroidRuntime:E '*:S'` showed repeated
NullPointerException crashes in SettingsActivity.onCreate at line 28. Adding
panel_battery renumbered settings view IDs, but Ant reused SettingsActivity.class
with old inlined IDs. The crash restarted the panel and looked like a refresh.
Did: changed `make debug` to run `ant clean debug` so every class is recompiled
against the generated resource IDs; documented the reason in app/README.md.
Validation: clean build and `adb install -r app/bin/NookPanel-debug.apk` succeeded;
`git diff --check` passed. Reopened PanelActivity with adb.
Limit: direct adb launch of SettingsActivity was denied because it is not exported;
opening it through the physical long-press menu remains to be verified.

## 2026-09-12 — Start the dashboard past the boot slide lock
Device: BNRV300, FW 1.2.2 (confirmed via adb getprop).
Goal: boot directly into NookPanel without pressing a button or unlocking.
Found: BootReceiver already launches the configured panel on BOOT_COMPLETED,
but the panel only requested KEEP_SCREEN_ON. The upstream TRMNL DisplayActivity
setKeepScreenAwake method also uses SHOW_WHEN_LOCKED, DISMISS_KEYGUARD and
TURN_SCREEN_ON. Applied those same API-7-compatible window flags to NookPanel.
Did: updated app README; `cd app && make debug`; installed using
`adb install -r app/bin/NookPanel-debug.apk`; ran `adb reboot` and reconnected
with `adb connect 192.168.4.78:5555`. No manual launch or input injected after boot.
Result: `adb shell dumpsys window` confirmed mSystemBooted=true,
mDisplayEnabled=true, PanelActivity focused, visible and drawn; Keyguard was
GONE (mViewVisibility=0x8) with mPolicyVisibility=false. Automatic boot works
according to the device window state. `git diff --check` passed.
Broke / gotchas: the usual adb temporary APK cleanup warning followed Success.

## 2026-09-12 — Innovetron boot, lock and power-off pictures
Device: BNRV300, FW 1.2.2 (adb getprop).
Goal: replace normal Nook branding with matching Innovetron artwork, including
an explicit Nook is off screen.
Did: inspected https://innovetron.com/ and its orbit/iN logo; created four
matching monochrome circuit illustrations with the built-in imagegen tool.
Saved source outputs, full prompts, converted device images and conversion
script in assets/innovetron/. Backed up the original splash, loading frames,
shutdown pictures, default/selected screensaver, settings DB and framework APK
in backups/branding-2026-09-12/.
Installed: boot partition booting.pgm (P5 800x600 rotated clockwise), loading
render-0.png (512x256 RGBA), cold_boot_screen.png and autoshutdown_screen.png
(600x800 RGB, Nook is off), fallback default.png and the selected JPEG in
/media/screensavers/Extra/ (Resting). Low-battery/recovery/charging artwork and
loading progress frames were preserved. Used staged files, host/device MD5
comparison, temporary sibling files and cmp before rename. Restored /system
read-only and unmounted the boot partition. Exact device script is saved with
backups; implementation notes are in docs/08-custom-screens.md.
Validation: conversion dimension/mode/decode assertions and git diff --check
passed. All six installed file checksums matched the host files. Ran adb reboot,
reconnected, and confirmed mSystemBooted=true, mDisplayEnabled=true, PanelActivity
focused, and Keyguard hidden without sending an unlock or manual launch.
Limit: early transient screens and actual power-off retention were not captured
on the physical display. The device was left running NookPanel.
Broke / gotchas: full-device streaming backup was too slow over Wi-Fi and stopped;
.gz.partial/.bz2.partial are incomplete, not recovery images. Individual artwork
backups completed. No firmware image or bootloader was flashed. ADB exec-out is
unsupported; a tested raw shell with stty raw -echo preserves binary data.

## 2026-09-12 — Battery-saving assessment (read-only device checks)
Device: BNRV300, FW 1.2.2 confirmed via getprop; battery 96%, unplugged.
Goal: assess disabling touch, physical-button controls and maximum battery life.
Did: inspected dumpsys power/battery, /proc/bus/input/devices, keypad keylayouts
and zForce input sysfs. Power service reports an active KEEP_SCREEN_ON_FLAG
screen wake lock and no partial wake locks. This matches PanelActivity's current
always-awake design. The keypad has distinct LEFT/RIGHT_NEXT/PREVPAGE mappings;
Home is handled by gpio-keys with WAKE_DROPPED. Side-button wake from suspend
has not been physically tested. No touch-controller power switch was identified
in the input2 directory; ignoring touches in the app is not hardware power-down.
Recommendation: implement image-as-screensaver plus RTC wake, bounded Wi-Fi
fetches and sleep between updates first; add side-button app controls and test
physical wake, keeping Home/power available for waking and recovery. The dashboard
must remain the sleep image rather than displaying the branded Resting artwork
on every cycle. Upstream TRMNL README reports 30+ days at 30-minute updates;
that is an upstream result, not a measurement or promise for this aged battery.
Result: no app, input, or power settings changed during this assessment.

## 2026-09-12 — Hourly dashboard screensaver and deep sleep
Device: BNRV300, FW 1.2.2; initial battery 96%, unplugged.
Goal: keep the dashboard visible while asleep, refresh hourly, use manual wake
and the existing long-press menu instead of remapping side buttons.
Did: replaced Handler-only periodic refresh with a manifest RefreshReceiver and
RTC_WAKEUP alarm, scheduling a fallback before each attempt. Added a bounded
90-second refresh wake lock, a 25-second Wi-Fi connection wait and a 75-second
attempt watchdog. Wi-Fi is disabled between updates. The current panel including
its battery overlay is atomically written to /media/screensavers/NookPanel/panel.png,
selected as screensaver, and the banner hidden. Previous screensaver settings
are saved in app preferences. Last successful downloads are also saved internally
and loaded on app restart. The old image survives failed fetches. Sleep uses the
one-second system timeout, restored on SCREEN_OFF and recovered on next launch.
Automatic refresh sleeps after five seconds; manual wake gives 60 seconds of
idle time. Long-press menu and Settings remain usable and stay awake while open.
Settings restores Wi-Fi; side-button mappings and touch configuration are unchanged.
Validation:
- Clean API-7-compatible Docker build passed; installed the APK in place.
- Temporarily used a 90-second interval. Logs showed sleep at 13:49:06, screen off
  at 13:49:13, automatic alarm at 13:49:33, successful fetch at 13:49:39 and a
  return to sleep at 13:49:45. Another alarm/fetch followed at 13:51:08/13:51:14.
- dmesg confirmed actual kernel mem suspend and resume, with Wi-Fi driver
  reinitialization afterward. This was not merely an invisible activity.
- Reinstalled to restart the process, then tested http://127.0.0.1:9/unavailable.png.
  Connection refused; the cached image was byte-identical before and after.
  Another alarm retried the failed URL and returned to sleep. Saved screensaver
  was inspected: dashboard with battery icon, no error screen or sleep branding.
- Restored the original URL and set interval_seconds=3600. Final real fetch
  succeeded at 13:55:32; saved next_refresh_at minus last_attempt_at was exactly
  3,600,000 ms, matching dumpsys alarm's RTC_WAKEUP entry.
- git diff --check passed. Logs, original/final preferences and retained
  screensaver are in gitignored backups/sleep-test-2026-09-12/.
Gotchas: the automatic online window is brief, so early ADB reconnect attempts
missed it; later logs confirmed both alarms had fired correctly. Tests used short
intervals; we did not wait a full hour or measure multi-day battery runtime.

## 2026-09-12 — Retry server generation and preserve the real dashboard
Device: existing BNRV300 FW 1.2.2; Nook untouched. Server: nultra (192.168.4.43).
Goal: stop replacing failed upstream renders with the simpler local dashboard.
Did: removed the mirror-mode Pillow fallback, added an atomic disk cache of the
last complete PNG and 30-second fetch retries. A first start without any good
image returns HTTP 503/Retry-After. Added upstream patch 0003 and a DisplayServer
adapter with three generation attempts, waiting 30 then 60 seconds; shutdown
interrupts waits. Install/update scripts and Docker include the adapter.
Validation: six unittest cases cover download failure, corrupt PNG rejection,
persistence across restart, HTTP 503, retry backoff/exhaustion, shutdown, and skipped
pages. Python compilation, shell syntax and patch application checks passed.
Deployment: copied the server and adapter to nultra, backed up replaced files in
/tmp/nook-before-retry, applied only patch 0003 to the deployed upstream checkout,
then restarted nookpanel before weather-cal. Restarted nookpanel again while
weather-cal was generating; curl/cmp confirmed byte-identical previous images
both during renderer downtime and after loading the cache from disk. Logs show
HTTP 200 for the cached image and retrying refused renderer connections.
Result: no substitute image on failure. Hourly Nook wake schedule is unchanged.
Recovery: weather-cal finished all four pages at 15:23:15 (Pi local time), resumed
HTTP on port 8082, and nookpanel automatically fetched today.png at 15:23:45.
Both services were active; no manual refresh was needed.

## 2026-09-12 — Adaptive bottom charts for Today and Tomorrow
Device: existing BNRV300 FW 1.2.2; Nook untouched. Renderer: nultra, 192.168.4.43.
Goal: show useful weather information instead of a dry precipitation chart.
Did: committed/pushed the preceding image-retry work first (20431f4). Added local
smart_chart.py and upstream patch 0004. Today prioritizes precipitation in the next
five hours; Tomorrow evaluates every hour from 06:00 through 21:00 tomorrow.
Otherwise choose strong wind/cloudy wind, UV, lighter wind, then temperature.
Rain retains the hatched probability bars; the heading explains the chosen metric.
Tomorrow shows labelled two-hour peaks, preserving showers between old chart labels.
Added UV, clouds, gusts and precipitation amount to the existing Open-Meteo request.
Old caches without the new fields refresh automatically; tomorrow_hourly is now
invalidated with other forecast data. Hourly/daily layouts and Nook alarms unchanged.
Validation: 19 local unittest cases passed, including rain window boundaries,
cloud/wind/UV priorities, night, mph, missing values, between-label spikes and the
previous image recovery cases. Isolated Pi integration tests passed for request
fields/cache reuse/migration, hourly mapping, tomorrow invalidation and all four
real templates. Chromium previews for UV, precipitation, wind and negative
temperature fit 600x800; visually inspected. Native and Docker-style patch application
checks, Python compilation, shell syntax and git diff whitespace checks passed.
Deployment: backed up touched renderer files to /tmp/nook-before-smart-charts,
applied only patch 0004 and installed the helper on nultra. The panel proxy kept
serving its byte-identical saved image during renderer startup. First live Today
render selected UV (peak 1.9), confirming the new API fields reached the template.
Result: the final helper (including cloudy/windy priority) completed all four
renders at 15:44:25 Pi local time. Today and Tomorrow both selected UV from the
live forecast (peaks 1.9 and 4.8). Inspected both live 600x800 images. HTTP 8082
resumed, and the proxy automatically served the new Today PNG at 15:44:49. Both
services active; the next scheduled generation remains 15:58 for the 16:00 wake.

## 2026-09-12 — Smooth UV and temperature lines
Device: existing BNRV300 FW 1.2.2; Nook untouched. Server: nultra.
Goal: retain precipitation bars and use spline-like curves for UV and temperature.
Did: added shape-preserving cubic SVG paths for UV/temperature, retaining point
markers and labels. Curves break at missing values and do not overshoot adjacent
values. Precipitation (including rain/snow) and wind retain hatched bars.
Validation: all 21 unit tests passed, including gaps and bounded UV and
negative temperature curves. Real template checks confirmed curved paths for UV and
temperature, bars for precipitation/wind. Four Chromium previews fit 600x800.
Deployment/result: backed up the helper to /tmp/nook-before-smooth-chart.py and
installed the verified helper on nultra. Visually inspected the regenerated live
Today UV curve. The full cycle finished at 15:53:37; Tomorrow selected wind from
the updated forecast (gusts 35 km/h), retaining its bars as intended. The renderer
resumed HTTP service and kept the existing 16:00 client-wake schedule.

## 2026-09-13 — Touch-free APK and remote settings dashboard

Device: BNRV300, firmware 1.2.2 (confirmed over ADB). Server: nultra,
192.168.4.43. No flashing or firmware changes.

Built APK 0.2.0 with the pinned Docker/Ant toolchain. Removed the long-press menu
and SettingsActivity; PanelActivity consumes touch without extending awake time.
The image response's X-Nook-Refresh-Seconds header persists the next wake interval,
including on 503; absent/invalid values retain the previous setting.

Added a Nultra-inspired settings dashboard on :8001, with one Weather & forecast
radio card, per-render enable/start times, advisory switch, and displayer refresh.
Validated settings persist atomically and wake page selection; disabled Hourly
cannot reappear via advisories. Existing one-hour device interval and four-page
schedule remain defaults. Current is not offered because this deployment only
generates Hourly, Today, Daily, and Tomorrow. Future program adapter and per-device
profile boundaries are documented in server/README.md.

Deployed only the proxy/control files, preserving Nultra's existing dirty checkout
and weather-cal service. Compared proxy files with the Git baseline first;
backups are /home/afshin/nook-backups/settings-20260913 on Nultra. Restarted only
nookpanel. Live :8001 API and browser load succeeded; :8000/panel.png returned
HTTP 200, 44,463 bytes, with X-Nook-Refresh-Seconds: 3600.

Validation: 25 unit tests pass; clean APK build passes; browser preview saved a
30-minute interval and disabled Hourly, with the expected JSON persisted. These
preview changes did not alter live settings. Asked for the hardware wake button
when the APK was ready; ADB became reachable for installation.

ADB `install -r` returned Success and PanelActivity launched. Triggered a normal
automatic refresh intent for runtime verification. Existing URL/preferences were
preserved; no device touch events or firmware writes were used.
Post-install verification: Nultra logged the Nook (192.168.4.78) fetching
/panel.png with HTTP 200 at 08:41:51. The subsequent ADB read was unavailable
after the sleep window, so persisted device preferences were not read back.

## 2026-09-13 — Install fetch-on-manual-wake update

Device: BNRV300, firmware 1.2.2 (reconfirmed using ADB getprop).
Goal: fetch immediately when waking with the physical n button.
Did: built the updated APK with `cd app && make debug`. After the owner woke
it, connected with `adb connect <nook-ip>:5555`, installed using
`adb -s <nook-ip>:5555 install -r app/bin/NookPanel-debug.apk`, and launched
`adb -s <nook-ip>:5555 shell am start -n com.hackingnook.panel/.PanelActivity`.
Result: install returned Success; app log for new PID 2345 showed a manual
refresh starting at 15:48:07 and succeeding at 15:48:11 (device log time).
Existing app settings preserved by reinstall. No firmware changes.
Broke / gotchas: first Wi-Fi connection reported No route to host; retry connected.
Next: verify a subsequent physical n-button wake fetches before the scheduled
interval; the post-install launch fetch was verified, the next button wake was not.

## 2026-09-13 — Dashboard-controlled server generation interval

Device: Nook untouched. Server: deployment Pi (<server-ip>).
Goal: generate fresh weather images every 30 minutes and expose the interval on :8001.
Did: confirmed the previous upstream scheduler ran hourly with a 120-second lead;
the proxy checks for images every 300 seconds and the device wakes every 3600.
Added server_refresh_seconds (900–86400; default 1800) to the settings API and
Program settings. The retrying adapter polls the API every 15 seconds, retains
the interval on outages, serially regenerates all configured pages, and skips
missed slots. It retains the existing 120-second lead (:28 and :58 for 30 minutes).
Validation: 29 unit tests passed, including interval validation/persistence,
legacy saves, control outages, hot reload, deadline alignment and serial runs.
Python compilation and git diff whitespace checks passed. Visually checked the
live dashboard and saved 30 minutes through its Program settings form.
Deployment: verified deployed files matched Git baseline, backed up settings.py,
dashboard.html, config.json and retrying_server.py under
~/nook-backups/generation-20260913 on the Pi. Copied only updated
control files and the renderer adapter; restarted nookpanel and weather-cal.
Both services reported active. Live settings API returned server_refresh_seconds
1800 and device_refresh_seconds 3600; existing page choices and start times retained.
Post-deploy verification: image endpoint remained HTTP 200 during startup.
All four startup pages finished; at 15:57:49 the live adapter logged
"Server image generation every 1800 seconds; next at Sun Sep 13 15:58:00 2026".
The next slots are :28 and :58. Dashboard form save and visual inspection passed.

## 2026-09-13 — Reset display button (deployment pending)

Device: Nook untouched; no reboot sent. Server: deployment Pi (<server-ip>).
Goal: reboot the Nook from :8001 and show failure when it is not connected.
Did: added Reset display to Your displayer, a same-origin JSON POST endpoint,
and an ADB adapter with explicit configured IPv4:port targeting, connection-state
verification, bounded command timeouts, concurrency guard and 30-second success
cooldown. Added adb to installer dependencies. nook_adb_address is blank in the
example; deployment must set it to the known Nook <nook-ip>:5555.
Validation: all 34 tests passed, including no reboot on offline/failed connection,
timeouts/missing ADB/reboot rejection, duplicates, request validation and origin
protection. Local browser preview verified the red offline failure message using
a simulated unavailable Nook. Python compilation and shell syntax passed.
Deployment blocked: SSH to the Pi returned No route to host on repeated attempts.
Need to deploy server/settings.py, dashboard.html and display_control.py, ensure
adb is installed, configure nook_adb_address preserving all other settings, and
restart only nookpanel once the server is reachable. No live files changed.

## 2026-09-13 — Reset display deployed after server returned

Server: deployment Pi (<server-ip>). Nook unreachable during verification; no reboot sent.
Compared live dashboard/settings against the prepared change: only the expected
reset feature differed. Backed up settings.py, dashboard.html and config.json to
~/nook-backups/reset-20260913 on the Pi. Installed distro adb package,
deployed settings.py, dashboard.html, display_control.py and updated installer.
Set nook_adb_address to <nook-ip>:5555 preserving all other config. Started ADB
as the service user and restarted only nookpanel. Python compilation passed on the Pi.
Live browser button test returned: "Reset failed: Nook is asleep, off, or not
connected. Wake it with the n button and try again." The button re-enabled.
Settings API retained server interval 1800, device interval 3600 and page choices;
image endpoint returned HTTP 200. Connected-device reboot remains unit-tested,
not hardware-confirmed in this deployment session.

## 2026-09-16 — Today current temperature (deployment blocked)

Goal: show the current temperature on Today instead of the daily forecast range.
Added overlay 0005 to request current_conditions and use its temperature,
feels-like, icon and weather text. Daily rain probability and adaptive hourly
chart remain forecasts. Upstream submodule source was not edited.
Validation: all 35 unit tests passed, including applying the complete overlay
series to an isolated checkout and checking positive, zero, negative and
Fahrenheit current temperatures distinct from daily extrema. Updated the optional
renderer integration check; visual rendering was not run in this environment.
Deployment: three SSH attempts to the configured pi2 target returned No route
to host. No live files changed and no service restarted. Once reachable, back up
the live Today template, apply overlay 0005 and restart weather-cal when idle;
verify a fresh Today image before marking deployment complete.

## 2026-09-16 — Today current temperature deployed to nultra

User corrected the deployment target: SSH alias nultra, 192.168.4.43 (hostname
raspberrypi), not pi2. Verified weather-cal was idle and the live Today template
matched the patch baseline. Saved the original under
~/nook-backups/today-current-20260916/today.py, copied overlay 0005 into the
server repo, checked and applied it, compiled the template and restarted weather-cal.
Both weather-cal and nookpanel reported active. Today rendered at 16:21:07 MDT;
retrieved and visually checked its 600x800 PNG: 17°C, feels like 14°, one current
temperature with no daily low/high range, and the forecast chart preserved.
The panel endpoint remained HTTP 200. The Nook itself was not woken or modified;
it receives the new image on a subsequent fetch after the proxy picks it up.
All four startup renders completed at 16:22:50 MDT; the renderer's today.png
endpoint returned HTTP 200 at 16:23:27 and the next generation is scheduled at 16:28.

## 2026-09-16 — ECCC observations for Edmonton current temperature

User selected Environment Canada after comparing The Weather Network with
Open-Meteo. Confirmed Open-Meteo current values are model data. ECCC city code
s0000045 uses Edmonton Blatchford (not Edmonton International Airport): at
22:00 UTC it measured 19.7 C, while the earlier model render showed 17 C.
Added openmeteo_eccc provider and patch 0006, with bounded public XML fetching,
quality/freshness checks, optional observed wind chill/humidex and observation
time attribution. Open-Meteo forecasts, charts, icon and advisories remain.
No model temperature fallback: failures use the existing image retry/recovery.
Updated native/Docker deployment paths and documented the Edmonton-only scope.
Validation: 40 unit tests passed; live provider test on nultra returned 20 C
(rounded from 19.7), no unsupported feels-like, and ECCC/Blatchford/4:00 PM label.
Deployment: backed up server.py and config.yaml under ~/nook-backups/eccc-20260916,
installed adapters and patch 0006, switched weather.service to openmeteo_eccc,
and restarted the idle weather-cal service. Both services reported active.
A transient Open-Meteo DNS failure during startup recovered on the automatic
retry. ECCC logged the 19.7 C observation and Today rendered at 16:33:42 MDT.
Retrieved and visually checked the 600x800 image: 20 C and the complete
ECCC / Blatchford / 4:00 PM attribution fit, with forecast chart preserved.
All four renders completed at 16:35:40 MDT. Both panel.png and the renderer
Today endpoint returned HTTP 200. Nook picks up the image on its next fetch.

## 2026-09-16 — Simple Weather concept B

User selected portrait concept B and requested implementation, deployment and Git push.
Added a second Simple Weather program with radio selection in the control center.
The new upstream page uses inline SVG: month/date/day, large outlined weather icon,
large temperature, and four hourly columns with temperature, rain chance and wind.
It retains ECCC current-temperature attribution and Open-Meteo forecast data.
Switching programs preserves the original weather schedule/advisories; the proxy
uses separate disk caches and retains its previous image until a valid replacement.
Native/Docker deployment scripts install the page and patch 0007 registers it.
Validation: 43 unit tests passed, including overlay application, ECCC validation,
program persistence, advisory bypass, failed switching and separate caches, winter
artwork and missing hourly data. JavaScript and shell syntax checks passed.
Inspected a 600x800 Chrome preview and adjusted date spacing. Confirmed the real
upstream page interface accepts serialized bytes before starting final generation.
Deployment: baseline hashes of the three control files matched local Git before
replacement. Backups are under ~/nook-backups/simple-weather-20260916 on nultra.
Installed the page, patch, control changes and deployment scripts, then restarted
weather-cal and nookpanel. Browser verification exercised radio selection, saving
Simple Weather settings, switching back and retaining the original page times,
and switching to Simple Weather again. Existing device refresh remains 60 minutes
and server generation remains 30 minutes; no APK or device firmware changes.
Final verification: inspected the deployed 600x800 PNG and saved it as
`docs/images/page-simple-weather.png`. At 17:28:11 the proxy served Simple Weather;
SHA-256 of panel.png matched the renderer's simple-weather.png exactly. Both
services were active. The Nook fetched panel.png with HTTP 200 at 17:28:30.
Simple Weather remains selected. Physical screen appearance was not inspected.

## 2026-09-16 — Simple Weather header alignment

Moved the large day number to the left and stacked weekday above month on the
right, as requested. Inspected the 600x800 Chrome preview; Python compilation
and whitespace checks passed. Backed up the prior adapter under
~/nook-backups/simple-header-20260916 on nultra, deployed the update and restarted
the idle renderer. The existing program selection and timing settings are unchanged.
The updated page rendered at 17:37:55 MDT. Visually inspected the deployed PNG;
panel.png and simple-weather.png SHA-256 hashes match. Updated the reference image.

## 2026-09-16 — Inverted date banner

Changed Simple Weather's date header to a full-width black banner with white
text, retaining the large day on the left and stacked weekday/month on the right.
Inspected the 600x800 Chrome preview; compilation and whitespace checks passed.
Backed up the previous layout under ~/nook-backups/inverted-header-20260916 on
nultra, deployed the adapter and restarted the idle renderer.
Regeneration completed at 18:59:25 MDT. Visually verified the deployed black
header and white date text. panel.png matches simple-weather.png byte-for-byte;
updated the checked-in reference image.

## 2026-09-16 — Adaptive Simple Weather refresh

Implemented adaptive wake timing through the existing X-Nook-Refresh-Seconds
header. Displayer settings owns fixed/adaptive mode, minimum/maximum intervals
and quiet hours; Simple Weather owns temperature/precipitation/wind thresholds.
Defaults: 15–120 minutes, 00:00–06:00, 3 C, 50% precipitation and 20 km/h wind delta.
Fixed 60-minute setting and original program schedule remain available.
Metadata with the displayed reading and 24 forecast hours is embedded atomically
in each Simple Weather PNG. The proxy derives the next wake from those exact
bytes, including restored caches. Stale/missing data takes a short retry rather
than a long sleep. Boundaries use local time with epoch interval arithmetic.
Overnight artwork shows four morning hours and NEXT UPDATE; a matching complete
morning plan is required for an overnight sleep. Server generation remains 30 min.
Validation: 57 unit tests passed; real upstream integration check verified morning
content, metadata and six-hour wake interval. Inspected the 600x800 overnight
fixture. JavaScript, shell syntax and Python compilation checks passed.
Deployment baseline hashes matched. Backups under ~/nook-backups/adaptive-20260916
on nultra. Deployed the control files, shared policy, page, extended forecast helper,
patch 0008 and deployment scripts. Restarted nookpanel/weather-cal, both active.
Enabled Adaptive via the dashboard and verified the default limits/quiet hours;
Simple Weather settings displayed and saved all three weather thresholds.
Live verification: all five pages finished at 21:20:54 MDT. The served PNG had
24 forecast hours and the matching displayed temperature. HTTP 200 response at
21:21:24 carried X-Nook-Refresh-Seconds: 1800; the dashboard reported Temperature
change / 30 minutes. The checked-in renderer integration also passed failed-render
retention. Overnight behavior was verified with a controlled midnight fixture,
not a physical overnight battery measurement. No APK update was required.

### 2026-09-16 — Dashboard display fetch history

- Added persistent successful NookPanel delivery tracking, last fetch, expected next
  fetch from the actual response timer, daily counts, and today/yesterday events
  grouped in the configured timezone. Browser previews and failed deliveries do
  not count. Tracking starts with this deployment; old events are not reconstructed.
- Moved Display options into Your display and Reset display into that dialog.
- Deployed server files to nultra (192.168.4.43); backed up originals in
  `/home/afshin/nook-backups/display-activity-20260916`, restarted only nookpanel.
- Validation: 61 unit tests pass; live dashboard and options dialog verified.
  Nook BNRV300 firmware 1.2.2 unchanged; no device reset or APK update performed.

### 2026-09-16 — Complete display improvement suite

- Added the eight-item checklist in display-roadmap.md, battery telemetry and
  learned discharge estimate, overdue/failed fetch reporting, daily hourly-baseline
  comparison, exact cached-image preview, clock/calendar banner, and optional
  daily program switching that bounds the device's next wake.
- Simple Weather now has a 12-hour trend and feels-like/precipitation/wind summary.
  Quiet hours use a distinct morning briefing with forecast temperature, sunrise,
  four morning hours, and wake time. Reviewed day/night/clock 600x800 artwork.
- Confirmed Nook model BNRV300 and firmware 1.2.2 via ADB. Built APK 0.3.0 using
  the pinned ADT container, installed with adb install -r, and launched it. Live
  server received 93% battery, unplugged, zero reported failures. Estimates remain
  unknown until sufficient discharge readings accumulate; no extra wake is added.
- Backed up nultra server/renderer files under
  /home/afshin/nook-backups/display-suite-20260916 and deployed overlays. Existing
  Simple Weather selection and sleep settings retained; schedule is opt-in.
- Validation: 66 tests passed and real weather-cal integration verified atomic
  overnight PNG metadata and six-hour sleep. No firmware flash or device reset.

### 2026-09-16 — Photo frame, countdown, daylight, reminders and exact preview

- Added Photo / Art Frame with normalized uploads and delivery-driven rotation;
  Countdown with icons/photos and configurable appearance; Seasonal Daylight with
  dated Open-Meteo solar data; and one-shot reminder overrides with overlap checks.
- Added actual Clock & Calendar settings and per-program configuration buttons.
  Moved preview/report above Programs. The preview stores the exact delivered PNG,
  independently of newly generated artwork and settings previews.
- Deployed to nultra, with originals backed up in
  /home/afshin/nook-backups/program-library-20260916. No new APK was needed; the
  existing BNRV300 / firmware 1.2.2 refresh-header protocol remains unchanged.
- User woke the Nook; live delivery and preview both had SHA-256
  f46a7f77522a0762c8769cf82e914bc8b16f34e746eb682650f6032456f90172.
- Validation: 76 tests including real local HTTP upload/preview/delete and exact
  bytes, reminder transitions, no slideshow advancement by preview, and restart
  persistence. Inspected all 600x800 program artwork and live dashboard controls.
- Timing limitation is visible in the dashboard: a sleeping Nook must fetch once
  to learn a new reminder; a reminder inserted before its next fetch may be missed.

### 2026-09-16 — Main-page schedule and repeat reminders

- Moved program scheduling from Display options into a main-page card with direct
  row editing and Save schedule. Removed radio selectors and shared Program settings;
  each program retains its own Settings button. Preserved existing program timing.
- Added once/daily/weekdays/weekly reminders, local-time recurrence, next-occurrence
  display, overlap checks and correct occurrence-end wake timers. Missing DST times
  skip; repeated times run once. Reminder series can be edited/deleted normally.
- Deployed to nultra, backing up originals under
  /home/afshin/nook-backups/schedule-repeat-20260916. No Nook APK changes.
- Validation: 81 tests pass, including DST, weekday/weekly recurrence, cross-midnight
  activity, conflicts, and legacy one-shot reminders; dashboard JavaScript checks pass.

### 2026-09-17 — Mobile dashboard, HEIC gallery, popup reminders and retry APK

- Reworked the dashboard for a 375-pixel phone viewport: direct program cards,
  SVG action icons with accessible names, comfortable touch targets, navigation
  shortcuts, and collapsed technical metrics/history. Program previews show
  loading/error states; gallery controls support native HEIC uploads.
- Deployed server/dashboard changes to nultra (192.168.4.43), preserving user
  settings. Backup: `/home/afshin/nook-backups/mobile-dashboard-20260917`.
- Installed distribution `libheif-examples`; isolated synthetic HEIC encode →
  upload → normalized PNG test passed on ARM. Decoder uses bounded subprocesses.
- Reminder popups overlay the scheduled image; successful Nook transfers consume
  that occurrence, so pressing n fetches the clear display. Delivery ledger
  persists through restart; previews do not consume reminders.
- Countdown now has a black counter banner, photo/icon middle and timestamped
  observation temperature footer. Inspected rendered countdown and popup images.
- Validation: 83 server tests passed, Java retry policy test passed, JS syntax
  check passed. APK 0.4.0 builds successfully in the pinned API-7 environment.
  Retries sleep 1m, 1m, 30m, then 1h; success restores normal timing.
- Browser verification at 375 × 812 found no horizontal overflow. All six
  programs returned valid 600 × 800 previews. Nook installation pending wake:
  known address 192.168.4.78:5555 was unreachable during this work.
