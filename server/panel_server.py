#!/usr/bin/env python3
"""
NookPanel server — renders an e-ink dashboard as a PNG and serves it over HTTP.

Designed to run on a Raspberry Pi Zero 2 W (or anything else on the LAN). All
the work happens here so the Nook only has to fetch and display an image:
Android 2.1 cannot do TLS 1.2, has 256 MB of RAM, and should be asleep most of
the time.

    python3 panel_server.py --config config.json

Set `renderer_url` and it stops drawing pages itself and serves the ones the
weather-cal renderer produces — **on this same machine**, at
`http://127.0.0.1:8082` by default. Nothing off-box is involved. It also chooses
*which* page to serve on each refresh; see `pagechoice.py`.

A page that fails to arrive, or arrives damaged, never reaches the panel: the
previous good image keeps being served until a new one validates.

Endpoints:
    GET /panel.png   the rendered dashboard
    GET /            an HTML page that reloads the image (handy for previewing)
    GET /healthz     "ok"
"""

import argparse
import io
import hashlib
from pathlib import Path
import tempfile
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

from PIL import Image

import fonts
import layouts
import pagechoice
import settings
from weather import Weather
import adaptive_refresh
from display_activity import DisplayActivity

LOG = logging.getLogger("nookpanel")

DEFAULT_CONFIG = {
    "latitude": 52.52,
    "longitude": 13.41,
    "location_name": "Berlin",
    "timezone": "Europe/Berlin",
    "units": "metric",          # "metric" or "imperial"
    "layout": "today",          # "today", "hourly" or "simple"
    # The weather-cal renderer on this same Pi. Set it and we serve its pages
    # instead of drawing our own.
    "renderer_url": None,       # e.g. "http://127.0.0.1:8082"
    "advisories": True,         # let incoming weather override the schedule
    "map_zoom": 11,             # 10 = region, 12 = city centre
    "landscape": False,
    "refresh_seconds": 300,
    "retry_seconds": 30,        # retry unavailable/damaged renderer pages sooner
    "port": 8000,
    "settings_port": 8001,
    "device_refresh_seconds": 3600,
}


class RenderedPages:
    """Serves the pages the local weather-cal renderer produces.

    It runs on this same Pi, so this is a loopback fetch, not a network
    dependency. The indirection buys two things: this process picks which page
    to show on every refresh while the renderer only redraws hourly, and a
    render that fails or produces a damaged file never reaches the panel — the
    previous good image keeps being served until a new one validates.
    """

    def __init__(self, config, cache_dir):
        self.settings_changed = threading.Event()
        self.config = config
        self.base = (config.get("renderer_url")
                     or config.get("mirror_base")   # old name, still honoured
                     or "").rstrip("/")
        source = self.base or config.get("mirror_url", "")
        if config.get("active_program") == "simple-weather":
            source += "|simple-weather"
        key = hashlib.sha256(source.encode()).hexdigest()[:16]
        self.cache_path = Path(cache_dir) / ("last-rendered-" + key + ".png")
        self.retrying = False
        self.png = b""
        self.fetched_at = None
        self.page = None
        self.lock = threading.Lock()

        # Only needed to decide *which* page to show; the image itself is
        # upstream's. A failed weather fetch just means we follow the clock.
        self.weather = Weather(config) if self.base else None
        try:
            body = self.cache_path.read_bytes()
            if _is_complete_png(body):
                self.png = body
                self.fetched_at = self.cache_path.stat().st_mtime
                LOG.info("loaded last good renderer image from disk")
        except FileNotFoundError:
            pass
        except OSError:
            LOG.exception("could not read cached renderer image")
        self.refresh()

    def _target(self):
        """(url, page, reason) for this refresh."""
        if not self.base:
            return self.config["mirror_url"], None, None    # old fixed-URL form

        if self.config.get("active_program") == "simple-weather":
            return f"{self.base}/simple-weather.png", "simple-weather", "selected program"

        now = datetime.now(ZoneInfo(self.config["timezone"]))
        try:
            self.weather.fetch()
        except Exception as exc:
            LOG.warning("weather fetch failed; choosing by the clock alone: %s", exc)

        page, reason = pagechoice.choose(self.config, self.weather, now)
        return f"{self.base}/{page}.png", page, reason

    def refresh(self):
        url, page, reason = self._target()
        if page and page != self.page:
            LOG.info("showing %s%s", page, f" - {reason}" if reason else "")
        elif reason and page == self.page:
            LOG.info("still on %s - %s", page, reason)

        request = urllib.request.Request(
            url, headers={"User-Agent": "NookPanel-mirror/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
        except Exception as exc:
            LOG.warning("fetch of %s failed: %s", url, exc)
            self._degrade()
            return

        if not _is_complete_png(body):
            LOG.warning("renderer returned %d bytes that are not a complete PNG",
                        len(body))
            self._degrade()
            return

        source = self.base or self.config.get("mirror_url", "")
        if page == "simple-weather":
            source += "|simple-weather"
        key = hashlib.sha256(source.encode()).hexdigest()[:16]
        self.cache_path = self.cache_path.with_name("last-rendered-" + key + ".png")
        self._save(body)
        self.retrying = False
        with self.lock:
            self.png = body
            self.fetched_at = time.time()
            self.page = page
        LOG.info("serving %s (%d bytes)", page or url, len(body))

    def _save(self, body):
        temporary = None
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.cache_path.parent, delete=False) as handle:
                temporary = handle.name
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.cache_path)
        except OSError:
            LOG.exception("could not persist renderer image; keeping it in memory")
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
                except OSError:
                    LOG.warning("could not remove temporary renderer cache %s", temporary)

    def _degrade(self):
        """Never draw a replacement dashboard; retry while retaining the last good one."""
        self.retrying = True
        if self.png:
            LOG.warning("renderer unavailable; keeping previous image (%s old); retrying", self._age())
        else:
            LOG.warning("renderer unavailable; no cached image yet; returning 503 and retrying")

    def _age(self):
        if not self.fetched_at:
            return "unknown age"
        seconds = int(time.time() - self.fetched_at)
        return f"{seconds // 60}m{seconds % 60:02d}s"

    def current(self):
        with self.lock:
            return self.png

    def run_forever(self):
        interval = self.config.get("refresh_seconds", 300)
        while True:
            delay = max(1, self.config.get("retry_seconds", 30)) if self.retrying else self.config.get("refresh_seconds", 300)
            self.settings_changed.wait(delay)
            self.settings_changed.clear()
            try:
                self.refresh()
            except Exception:
                self.retrying = True
                LOG.exception("mirror refresh failed; retrying")


class Renderer:
    """Owns the current PNG and refreshes it on a timer in the background."""

    def __init__(self, config, cache_dir):
        self.settings_changed = threading.Event()
        self.config = config
        self.cache_dir = cache_dir
        self.weather = Weather(config)
        self.png = b""
        self.lock = threading.Lock()
        self.refresh()

    def refresh(self):
        try:
            self.weather.fetch()
        except Exception as exc:                       # network flakiness is normal
            LOG.warning("weather fetch failed, keeping previous data: %s", exc)

        now = datetime.now(ZoneInfo(self.config["timezone"]))
        image = layouts.render(self.config, self.weather, now, self.cache_dir)

        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        with self.lock:
            self.png = buffer.getvalue()
        LOG.info("rendered %s layout, %d bytes",
                 self.config.get("layout", "today"), len(self.png))

    def current(self):
        with self.lock:
            return self.png

    def run_forever(self):
        interval = self.config.get("refresh_seconds", 300)
        while True:
            self.settings_changed.wait(self.config.get("refresh_seconds", 300))
            self.settings_changed.clear()
            try:
                self.refresh()
            except Exception:
                LOG.exception("render failed")


def _is_complete_png(body):
    """Reject truncated or corrupt renders before they reach the panel.

    The magic bytes alone are not enough: a render interrupted part-way through
    writing still starts with them. Decoding the whole image is the cheap,
    certain check.
    """
    if not body.startswith(b"\x89PNG"):
        return False
    try:
        Image.open(io.BytesIO(body)).load()
        return True
    except Exception:
        return False


def make_handler(renderer):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"     # Android 2.1's HTTP stack is happier

        def do_GET(self):
            path = urllib.parse.urlparse(self.path).path
            if path in ("/panel.png", "/panel"):
                body = renderer.current()
                if not body:
                    self.send_response(503)
                    self.send_header("X-Nook-Refresh-Seconds", str(adaptive_refresh.from_png(body, renderer.config)[0]))
                    self.send_header("Retry-After", str(max(1, renderer.config.get("retry_seconds", 30))))
                    self.send_header("Content-Length", "0")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    return
                seconds, reason = adaptive_refresh.from_png(body, renderer.config)
                self.send_response(200)
                self.send_header("X-Nook-Refresh-Seconds", str(seconds))
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                self.wfile.flush()
                if self.headers.get("User-Agent", "").startswith("NookPanel/"):
                    renderer.activity.record(seconds, reason)
            elif path == "/healthz":
                self._text("ok")
            elif path == "/":
                interval = renderer.config.get("refresh_seconds", 300)
                self._text(
                    "<html><head><meta http-equiv=refresh content=%d>"
                    "<title>NookPanel preview</title></head>"
                    "<body style='margin:0;background:#888;text-align:center'>"
                    "<img src='/panel.png?%d' style='border:1px solid #000'>"
                    "</body></html>" % (interval, int(time.time())),
                    content_type="text/html")
            else:
                self.send_error(404)

        def _text(self, body, content_type="text/plain"):
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt, *args):
            LOG.info("%s %s", self.address_string(), fmt % args)

    return Handler


def load_config(path):
    config = dict(DEFAULT_CONFIG)
    if path and os.path.exists(path):
        with open(path) as handle:
            config.update(json.load(handle))
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--port", type=int)
    parser.add_argument("--layout", choices=sorted(layouts.LAYOUTS))
    parser.add_argument("--once", metavar="OUT.PNG",
                        help="render a single PNG to a file and exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    config = load_config(args.config)
    if args.port:
        config["port"] = args.port
    if args.layout:
        config["layout"] = args.layout

    pages_from = (config.get("renderer_url") or config.get("mirror_base")
                  or config.get("mirror_url"))

    if not pages_from and not fonts.have_comic_neue():
        LOG.warning("Comic Neue not installed (apt install fonts-comic-neue) — "
                    "the layout is tuned for it and will look off without it")

    cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")

    if pages_from:
        LOG.info("serving pages from %s", pages_from)
        renderer = RenderedPages(config, cache_dir)
    else:
        renderer = Renderer(config, cache_dir)

    if args.once:
        if not renderer.current():
            raise SystemExit("No good image available yet; retry when the renderer is ready")
        with open(args.once, "wb") as handle:
            handle.write(renderer.current())
        print("wrote", args.once)
        return

    renderer.activity = DisplayActivity(Path(cache_dir) / "display-fetches.json")
    threading.Thread(target=renderer.run_forever, daemon=True).start()

    control = ThreadingHTTPServer(("0.0.0.0", config["settings_port"]),
                                  settings.make_handler(settings.Settings(renderer, args.config)))
    threading.Thread(target=control.serve_forever, daemon=True).start()
    LOG.info("settings dashboard on port %d", config["settings_port"])

    server = ThreadingHTTPServer(("0.0.0.0", config["port"]), make_handler(renderer))
    LOG.info("serving http://0.0.0.0:%d/panel.png", config["port"])
    server.serve_forever()


if __name__ == "__main__":
    main()
