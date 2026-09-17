#!/usr/bin/env bash
# Install upstream's weather-cal server natively on a Raspberry Pi.
#
# Run it ON the Pi, from a clone of this repo:
#   ~/hacking_nook/upstream/install-on-pi.sh
#
# Not Docker: upstream's published image is linux/amd64, and on a Zero 2 W with
# 425 MB of RAM a container runtime is overhead we cannot spare. Raspberry Pi OS
# ships chromium and chromium-driver in apt, so a venv against those is both
# lighter and simpler.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$REPO/external/inkplate10-weather-cal/server"
VENV="$REPO/upstream/.venv"
RUNDIR="$REPO/upstream/run"
PORT="${PORT:-8082}"
SWAP_MB="${SWAP_MB:-2048}"

echo "==> preflight"
# A previously interrupted apt run leaves dpkg half-configured, and every
# apt-get after it fails with "dpkg was interrupted, you must manually run
# 'sudo dpkg --configure -a'" - an error that reads as if this script produced
# it. This is a no-op when nothing is pending, and can take a few minutes when
# something is.
sudo dpkg --configure -a

echo "==> system packages"
sudo apt-get update -qq
# Pillow and PyYAML come from apt: neither publishes armv7 wheels, and building
# them from source on a Zero 2 W takes the better part of an hour.
sudo apt-get install -y -qq \
    chromium chromium-driver \
    python3-venv python3-pil python3-yaml \
    fonts-dejavu-core git

echo "==> swap (Chromium needs more headroom than 425 MB of RAM)"
if [ "$(free -m | awk '/^Swap:/{print $2}')" -lt "$SWAP_MB" ]; then
    sudo dphys-swapfile swapoff
    sudo sed -i "s/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=$SWAP_MB/" /etc/dphys-swapfile
    # The default cap is 2048; raise it so CONF_SWAPSIZE is honoured.
    sudo sed -i "s/^#\?CONF_MAXSWAP=.*/CONF_MAXSWAP=$SWAP_MB/" /etc/dphys-swapfile
    sudo dphys-swapfile setup
    sudo dphys-swapfile swapon
fi
free -m | awk '/^Swap:/{print "    swap now " $2 " MB"}'

echo "==> submodule"
git -C "$REPO" submodule update --init --depth 1 external/inkplate10-weather-cal

echo "==> python environment"
# --system-site-packages so the apt Pillow and PyYAML are visible.
[ -d "$VENV" ] || python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip wheel

# Upstream's requirements minus Pillow and PyYAML (from apt above), and with
# the pins relaxed: the exact versions upstream pins have no armv7 wheels.
"$VENV/bin/pip" install --quiet \
    selenium airium packaging googlemaps Flask requests Werkzeug \
    paho-mqtt astral \
    "epd-server @ git+https://github.com/chrisjtwomey/epd.git@v0.3.1#subdirectory=server"

echo "==> patches"
# Idempotent: --check first so a re-run does not fail on an already-patched tree.
for patch in "$REPO"/upstream/patches/*.patch; do
    if git -C "$REPO/external/inkplate10-weather-cal" apply --check "$patch" 2>/dev/null; then
        git -C "$REPO/external/inkplate10-weather-cal" apply "$patch"
        echo "    applied $(basename "$patch")"
    else
        echo "    skipped $(basename "$patch") (already applied, or upstream moved)"
    fi
done

echo "==> our map shim"
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

# server.py hardcodes config.yaml beside itself (`cwd` on line 30 is
# os.path.dirname(os.path.realpath(__file__)), not the process working
# directory) and has no --config flag. Keep the real file outside the submodule
# and symlink it into place.
mkdir -p "$RUNDIR"
if [ ! -f "$RUNDIR/config.yaml" ]; then
    sed -e 's/^  port: .*/  port: '"$PORT"'/' \
        "$REPO/upstream/config.example.yaml" > "$RUNDIR/config.yaml"
    # All four pages the rotation uses, regenerated hourly. `current` is the one
    # page nothing shows, and patch 0001 renders only what the pools name, so
    # leaving it out saves a Chromium run per cycle.
    python3 - "$RUNDIR/config.yaml" <<'CFG'
import re, sys
path = sys.argv[1]
text = open(path).read()
pools = ("  pools:\n    hourly: [hourly.png]\n    today: [today.png]\n"
         "    daily: [daily.png]\n    tomorrow: [tomorrow.png]\n")
text = re.sub(r"  pools:\n(?:    .*\n)+", pools, text)

# Mirrors the panel server's page_schedule so the client protocol agrees with
# what we actually show. Regeneration runs at each of these times.
rotation = {0: "tomorrow", 6: "hourly", 10: "today", 17: "daily", 21: "tomorrow"}
page, out = "tomorrow", []
for hour in range(24):
    page = rotation.get(hour, page)
    out.append('    "%02d:00:00": %s' % (hour, page))
text = re.sub(r"  schedule:\n(?:    .*\n)+",
              "  schedule:\n    type: times\n" + "\n".join(out) + "\n", text)
open(path, "w").write(text)
CFG
    echo "    wrote upstream/run/config.yaml - edit location and timezone"
fi
ln -sfn "$RUNDIR/config.yaml" "$APP/config.yaml"

echo "==> systemd unit"
sudo tee /etc/systemd/system/weather-cal.service >/dev/null <<UNIT
[Unit]
Description=inkplate10-weather-cal server (upstream, with OSM map shim)
After=network-online.target NetworkManager-wait-online.service time-sync.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$RUNDIR
# Wait for DNS, not just for a link. See upstream/wait-for-dns.sh.
# A script rather than an inline sh -c: this heredoc is unquoted, so anything
# with a $ in it would be expanded here at install time rather than at boot.
ExecStartPre=$REPO/upstream/wait-for-dns.sh
Environment=CHROME_BIN=/usr/bin/chromium
Environment=SERVER_PORT=$PORT
Environment=OSM_MAP_ZOOM=${OSM_MAP_ZOOM:-12}
Environment=OSM_MAP_STYLE=${OSM_MAP_STYLE:-lineart}
Environment=OSM_MAP_LABEL=${OSM_MAP_LABEL:-}
ExecStart=$VENV/bin/python $APP/server.py
Restart=always
# A regeneration is several minutes of Chromium. Restarting on top of one leaves
# two browsers competing and the webdriver connection times out at 120s - which
# Selenium does not expose - so give a dying run time to take its children with
# it, and leave a long gap before retrying.
# Long enough that a crash cannot spin, short enough that a boot-time failure
# is not a five-minute outage.
RestartSec=30
TimeoutStopSec=90
KillMode=control-group
# Chromium is the memory hog; let it swap rather than be killed.
MemoryMax=infinity

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now weather-cal
echo "==> started. Watch it with:  journalctl -u weather-cal -f"
echo "    then point the Pi's panel server at http://127.0.0.1:$PORT/hourly.png"
