#!/usr/bin/env bash
# Re-apply everything this repo overlays onto the weather-cal checkout, then
# restart it. Run after a `git pull` that changes a patch or the map shim.
#
#   ~/hacking_nook/upstream/refresh-on-pi.sh
#
# The overlay is two different kinds of thing, and both have to be redone
# together — reverting the submodule to apply patches cleanly also throws away
# the shim, which is a plain file copy, not a patch. That failure is silent
# until the renderer starts and dies on "Invalid API key provided."
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$REPO/external/inkplate10-weather-cal/server"

echo "==> stopping the renderer"
sudo systemctl stop weather-cal || true
sleep 5

echo "==> resetting the checkout"
git -C "$REPO/external/inkplate10-weather-cal" checkout -q -- server/
git -C "$REPO/external/inkplate10-weather-cal" reset -q
rm -f "$APP/views/html/today-precip.css"

echo "==> patches"
for patch in "$REPO"/upstream/patches/*.patch; do
    git -C "$REPO/external/inkplate10-weather-cal" apply "$patch"
    echo "    $(basename "$patch")"
done

echo "==> map shim"
install -m 644 "$REPO/server/mapview.py" "$APP/nook_mapview.py"
install -m 644 "$REPO/server/linemap.py" "$APP/linemap.py"
install -m 644 "$REPO/server/fonts.py"   "$APP/fonts.py"
install -m 644 "$REPO/upstream/google_api_shim.py" "$APP/google/api.py"
install -m 644 "$REPO/upstream/retrying_server.py" "$APP/retrying_server.py"
install -m 644 "$REPO/upstream/smart_chart.py" "$APP/smart_chart.py"
install -m 644 "$REPO/upstream/eccc_current.py" "$APP/eccc_current.py"
install -m 644 "$REPO/upstream/eccc_weather.py" "$APP/eccc_weather.py"
install -m 644 "$REPO/upstream/simple_weather.py" "$APP/simple_weather.py"
install -m 644 "$REPO/upstream/simple_weather_data.py" "$APP/simple_weather_data.py"
install -m 644 "$REPO/server/adaptive_refresh.py" "$APP/adaptive_refresh.py"
grep -q "OpenStreetMap" "$APP/google/api.py" \
    || { echo "ERROR: the shim did not land; upstream's Google version is still in place" >&2; exit 1; }
echo "    google/api.py is ours"

echo "==> starting"
sudo systemctl start weather-cal
echo "    journalctl -u weather-cal -f"
