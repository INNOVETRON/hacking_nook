# 06 — NookPanel: our own Android 2.1 app

Lives in [`app/`](../app). Status: **installed on BNRV300 firmware 1.2.2, with
hourly screensaver sleep, automatic wake, and an API-7-compatible APK.**

## The build problem, and the solution

Android Studio and the modern Gradle plugin cannot target API 7 — the minimum
they will accept is far above it. The only working route is the **last ADT
bundle Google shipped, `adt-bundle-linux-x86_64-20140702`**, which still
contains the Ant build system plus `aapt` and `dx`. This is exactly the trick
the maintained TRMNL client uses; we independently confirmed it works.

We pin it in a container so nobody has to install a 2014 SDK on their laptop:

```bash
cd app
make image     # build the container (downloads the ~500 MB ADT bundle once)
make debug     # -> bin/NookPanel-debug.apk
make install   # adb install -r, run from the host with the Nook plugged in
```

Notes that cost time to discover:
- The bundle's ADT binaries are 32-bit x86, hence `lib32stdc++6` / `lib32z1`.
  On x86_64 they run natively; on ARM hosts you need QEMU binfmt.
- **JDK 8**, not 11 or 17 — the 2014 Ant scripts do not understand newer JDKs.
- The bundle only ships the **android-20** platform, so `project.properties`
  says `target=android-20`. That is the *compile* target only; the runtime
  target is API 7, set by `uses-sdk` in `AndroidManifest.xml`.
- Files in the bundle unpack root-only; the Dockerfile `chmod -R a+rX`s them so
  the container can run as your UID and not leave root-owned build output.

## App components

| | |
|---|---|
| `PanelActivity` | Fullscreen image with battery overlay; touch input ignored. Fetches, saves the screensaver, then sleeps |
| `ImageFetcher` | Plain HTTP only. Decodes to `RGB_565` with `inPurgeable`, and catches `Throwable` because `OutOfMemoryError` is a genuine expectation at 256 MB |
| `Config` | One place for SharedPreferences keys, with a 10 s floor on the interval |
| `RefreshReceiver` / `PowerCycle` | Persistent RTC wake alarm, bounded wake lock, Wi-Fi control and screen-timeout restoration |
| `FrameStore` | Last-good-image cache and atomic dashboard screensaver writes |

Java 6 language level throughout: no diamond operator, no try-with-resources,
no strings in `switch`.

Remaining omissions: HTTPS and explicit e-ink refresh control.

## Known Android-2.1 landmines (already handled or noted)

- **`HttpURLConnection` keep-alive is broken** on Eclair/Froyo — it hands back
  closed sockets. We set `http.keepAlive=false` and send `Connection: close`.
- **No TLS 1.2, no SNI.** Plain HTTP on the LAN for now. If we ever need HTTPS,
  bundle **SpongyCastle** (the Android repackaging of BouncyCastle) as the TRMNL
  client does — see `external/trmnl-nook-simple-touch/libs/`.
- **Recycle bitmaps by hand.** We free the previous bitmap when swapping in a
  new one.

## Launching it — the stock home hides sideloaded apps

`com.bn.nook.home` has no general app drawer; it lists B&N content only. A
sideloaded APK is installed and runnable but appears **nowhere on screen**. Four
ways to reach NookPanel, best last:

1. **adb** — `adb shell am start -n com.hackingnook.panel/.PanelActivity`
2. **ReLaunch** (installed by NookManager) is a real launcher and lists every
   installed app: `adb shell am start -n com.harasoft.relaunch/.Main`
3. **NTMM** (`org.nookmods.ntmm`, also from NookManager) can remap the physical
   **Home button** — short press → NookPanel, long press → app drawer. This is
   what the TRMNL client's docs recommend, and it is the most useful for a
   device with no keyboard.
4. **Start on boot.** `BootReceiver` listens for `BOOT_COMPLETED` and launches
   the panel, provided a URL is configured. A wall-mounted dashboard should come
   back by itself after a power cut, and this also makes the app reachable
   without any launcher at all.

If you want the Nook to be *nothing but* a dashboard, add
`<category android:name="android.intent.category.HOME" />` to `PanelActivity`'s
intent filter and it becomes the home screen. Recoverable via adb and ReLaunch,
but do it only once deep sleep works — otherwise a crash loop leaves you poking
at it over Wi-Fi.

## v0.2 — deep sleep

Implemented in NookPanel on 2026-09-12, with a **one-hour default refresh**:

- Save the last successful download in app-private storage and reload it after
  process restarts. Failed fetches preserve that image.
- Render the dashboard, including the battery overlay, to
  `/media/screensavers/NookPanel/panel.png`, select it as the system screensaver,
  and hide the screensaver banner. The Innovetron boot and off screens remain.
- Use an explicit manifest `RefreshReceiver` and `AlarmManager.RTC_WAKEUP`, so
  the next cycle survives process eviction. Schedule a fallback before fetching
  and rearm at completion. The server supplies the interval through the image response header.
- Allow 25 seconds for Wi-Fi to associate; a 75-second watchdog bounds the whole
  attempt. A timed-out completion cannot replace the currently displayed image.
- Automatic cycles sleep after five seconds; manual wake enables Wi-Fi and
  leaves 60 seconds for ADB access. Touch input is ignored. No side-button remapping is used.
- Turn Wi-Fi off, release the bounded refresh wake lock, clear the awake window
  flags, and set the system timeout to one second. Restore the original timeout
  on SCREEN_OFF, with a persisted recovery flag for the next app launch.

The battery icon and clock are snapshots between wakes. ADB over Wi-Fi is
unavailable while sleeping. If `/media` is unmounted (USB mass-storage mode), a
screensaver write can fail; the prior screensaver stays intact and the app still
returns to sleep. Original screensaver settings are saved in app preferences.

### Why the natural screen-off path matters

The upstream TRMNL project reports about **60 hours** awake and **30+ days** with
deep sleep at a 30-minute refresh. Those are upstream results, not a measured
runtime for our Nook's aged battery. The mechanism, learned from
`external/trmnl-nook-simple-touch/AGENTS.md`, is worth reading in full because
almost every obvious approach fails:

| Approach | Result |
|---|---|
| `PowerManager.goToSleep()` | `SecurityException` — needs `DEVICE_POWER`, a `signatureOrSystem` permission. Not grantable even with root |
| `input keyevent 26` (KEYCODE_POWER) | No-op; the Nook kernel eats the power key before Android sees it |
| `sendevent` raw `KEY_POWER` | Same |
| `echo mem > /sys/power/state` via `su` | Suspends the kernel but bypasses Android's power manager: no screensaver render, unreliable wake |
| `service call power 2 ...` via `su` | Correct binder call, works from adb — but the Superuser prompt *is itself user activity*, which resets the idle timer and invalidates the timestamp |
| **`Settings.System.SCREEN_OFF_TIMEOUT` = 1000 ms** | ✅ **Works.** `WRITE_SETTINGS` is a normal permission. Android's own `PowerManagerService` then runs the natural screen-off path, which renders the EPD screensaver, calls `set_screen_state 0`, and sets up the keyguard properly |

The manifest now includes `WRITE_SETTINGS`, `WRITE_EXTERNAL_STORAGE`,
`CHANGE_WIFI_STATE`, and `WAKE_LOCK` for this flow.

## Roadmap

- **v0.1** ✅ fetch and display, settings, long-press menu, start on boot
- **v0.2** ✅ deep sleep, hourly wake, last-good-image cache, battery overlay
- **v0.3** battery/RSSI reporting back to the server; explicit e-ink full-refresh
  control (`/sys/class/graphics/fb0/epd_*`, `android.hardware.EpdController`)
- **Remote control**: server dashboard selects programs, render schedules, and device refresh. No touch zones are planned.
