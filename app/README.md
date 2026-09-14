# app — NookPanel, our Android 2.1 client

A fullscreen image panel for the Nook Simple Touch: fetch a PNG from a server on
the LAN, save the dashboard as the screensaver, and sleep until the next update.
The default refresh interval is **3600 seconds (one hour)**.

The APK ignores all touchscreen input. There is no on-device settings activity
or long-press menu. Set the initial image URL using `tools/push-config.sh` over
ADB; existing installations keep their URL when upgraded.

Use `http://<server>:8001/` for displayer refresh and weather page settings.
The server returns `X-Nook-Refresh-Seconds` with every image response (including
503). The app persists valid values from 60 to 86400 seconds and uses the new
interval for the next alarm. Missing or invalid headers retain the previous
interval; the default is one hour. Already-sleeping devices receive changes on
their next fetch, not immediately.

A small battery icon and percentage overlay the top-right corner. A plus sign
indicates charging. It remains visible over retained images and screensavers.
Automatic cycles sleep after five seconds. Waking with the physical “n” button
fetches immediately, even before the next scheduled refresh, and leaves Wi-Fi
available for 60 seconds after the fetch finishes. Opening the app also fetches
immediately. Touching the display does not extend that time.
The app starts automatically after boot when an image URL is configured.

If a refresh fails, the last successfully displayed image stays visible while
the app retries at the configured interval. An error is shown only if no image
has loaded yet. The last good image is saved in app-private storage so it also
survives app restarts and temporary network outages.

While asleep, the dashboard and battery snapshot remain visible. Wi-Fi is off;
an Android RTC wake alarm starts the next refresh even if the app process was
killed. Wi-Fi gets up to 25 seconds to reconnect and the whole fetch attempt has
a 75-second watchdog, after which the app retains the old image and sleeps.
Remote ADB over Wi-Fi is therefore available only while the device is awake.

The app selects `/media/screensavers/NookPanel/panel.png` and hides the Nook's
screensaver banner. This replaces the Innovetron “Resting” picture during normal
dashboard sleep; custom boot and power-off pictures still apply. The previous
screensaver selection is saved in app preferences. A failed screensaver write
retains the previous file. The temporary one-second screen timeout is restored
as soon as the screen turns off and recovered on the next launch after a crash.

```bash
make image     # one-time: build the pinned 2014 ADT container
make debug     # -> bin/NookPanel-debug.apk
make install   # adb install -r  (run on the host, Nook plugged in)
```

`make debug` always performs a clean build: the legacy Ant incremental compiler
can retain obsolete resource IDs after layout changes and crash Settings.

Full background, build-chain gotchas, and the roadmap:
[../docs/06-our-own-app.md](../docs/06-our-own-app.md).
The server that produces the image: [../server](../server).
