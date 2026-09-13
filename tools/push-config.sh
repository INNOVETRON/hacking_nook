#!/usr/bin/env bash
# Configure NookPanel over adb instead of typing on the infrared touchscreen.
#
#   ./tools/push-config.sh http://192.168.4.42:8000/panel.png [interval_seconds]
#
# Writes the app's SharedPreferences XML directly. The app must not be running
# (it rewrites the file on save), so this stops it first.
set -euo pipefail

PKG=com.hackingnook.panel
URL="${1:?usage: $0 <image-url> [interval-seconds]}"
INTERVAL="${2:-3600}"
PREFS_DIR="/data/data/$PKG/shared_prefs"

# Android 2.1's toolbox is threadbare: no `ls -ld`, no `mkdir -p`, and `chown`
# wants user.group rather than user:group. Busybox (installed by NookManager)
# has all of them, so use it for everything that touches the filesystem.
BB=/system/xbin/busybox

# `am force-stop` does not exist on Android 2.1 — kill the process directly.
adb shell "$BB pkill -f $PKG" >/dev/null 2>&1 || true

# Whatever uid the installer gave the app — prefs must stay owned by it.
OWNER=$(adb shell "$BB ls -ldn /data/data/$PKG" | tr -d '\r' | awk '{print $3"."$4}')
case "$OWNER" in
    [0-9]*.[0-9]*) ;;
    *) echo "ERROR: could not read the uid of $PKG — is it installed?" >&2; exit 1 ;;
esac

# Write locally and push. Piping into `adb shell "cat > file"` hangs forever:
# adb never forwards EOF, so cat sits waiting for input that cannot arrive.
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
cat > "$TMP" <<XML
<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
<string name="url">$URL</string>
<int name="interval_seconds" value="$INTERVAL" />
</map>
XML

adb shell "$BB mkdir -p $PREFS_DIR"
adb push "$TMP" "$PREFS_DIR/nookpanel.xml" >/dev/null
adb shell "$BB chown $OWNER $PREFS_DIR $PREFS_DIR/nookpanel.xml; $BB chmod 771 $PREFS_DIR; $BB chmod 660 $PREFS_DIR/nookpanel.xml"

echo "configured:"
adb shell "cat $PREFS_DIR/nookpanel.xml" | tr -d '\r'
echo "launching..."
adb shell "am start -n $PKG/.PanelActivity" | tr -d '\r'
