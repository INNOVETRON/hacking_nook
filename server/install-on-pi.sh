#!/usr/bin/env bash
# Install NookPanel's server as a systemd service on a Raspberry Pi.
#
# Run it ON the Pi, from a clone of this repo:
#   git clone https://github.com/AfshinKI/hacking_nook.git ~/hacking_nook
#   ~/hacking_nook/server/install-on-pi.sh
#
# Idempotent: safe to re-run after a `git pull` to pick up code changes.
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_USER="${SUDO_USER:-$USER}"
UNIT=/etc/systemd/system/nookpanel.service

echo "==> preflight"
# A previously interrupted apt run leaves dpkg half-configured, and every
# apt-get after it fails with "dpkg was interrupted, you must manually run
# 'sudo dpkg --configure -a'" - an error that reads as if this script produced
# it. This is a no-op when nothing is pending, and can take a few minutes when
# something is.
sudo dpkg --configure -a

echo "==> installing dependencies"
# Pillow from apt, not pip: bookworm is PEP 668 externally-managed, and building
# Pillow from source on a Pi Zero 2 W takes the better part of an hour.
# fonts-comic-neue is the rounded hand-lettered face the 'today' layout is
# drawn around; without it the text falls back to DejaVu and looks wrong.
sudo apt-get update -qq
sudo apt-get install -y -qq python3-pil fonts-dejavu-core fonts-comic-neue adb

if [ ! -f "$SERVER_DIR/config.json" ]; then
    echo "==> creating config.json from the example — edit it and re-run"
    cp "$SERVER_DIR/config.example.json" "$SERVER_DIR/config.json"
fi

echo "==> writing $UNIT"
sudo tee "$UNIT" >/dev/null <<UNITEOF
[Unit]
Description=NookPanel e-ink dashboard server
After=network-online.target NetworkManager-wait-online.service time-sync.target
Wants=network-online.target
# Start after the renderer when it is installed. Not a Wants= — this server
# runs perfectly well on its own, drawing pages itself.
After=weather-cal.service

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${SERVER_DIR}
ExecStart=/usr/bin/python3 ${SERVER_DIR}/panel_server.py --config ${SERVER_DIR}/config.json
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNITEOF

echo "==> starting service"
sudo systemctl daemon-reload
sudo systemctl enable --now nookpanel
sleep 3
sudo systemctl --no-pager --lines=5 status nookpanel || true

PORT=$(python3 -c "import json;print(json.load(open('$SERVER_DIR/config.json')).get('port',8000))")
echo
echo "==> done. The Nook should fetch:"
for ip in $(hostname -I); do
    case "$ip" in *:*) continue ;; esac
    echo "      http://${ip}:${PORT}/panel.png"
done
echo "    Preview in a browser: http://$(hostname -I | awk '{print $1}'):${PORT}/"
