"""Versioned LAN control plane. Program adapters remain server-side."""
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit
import pagechoice
import adaptive_refresh
from display_control import DisplayControl, ResetError

PROGRAMS = [
    {"id": "weather-cal", "name": "Weather & forecast", "description": "Your day, at a glance",
     "pages": ["hourly", "today", "daily", "tomorrow"]},
    {"id": "simple-weather", "name": "Simple Weather", "description": "Big, clear weather and the next four hours",
     "pages": []},
]


class Settings:
    def __init__(self, renderer, path):
        self.renderer = renderer
        self.path = Path(path)
        self.lock = threading.Lock()
        self.display = DisplayControl()

    def snapshot(self):
        c = self.renderer.config
        seconds, reason = adaptive_refresh.from_png(getattr(self.renderer, "current", lambda: b"")(), c)
        return {"refresh_preview": {"seconds": seconds, "reason": reason}, "version": 1, "programs": PROGRAMS, "active_program": c.get("active_program", "weather-cal"),
                "server_refresh_seconds": c.get("server_refresh_seconds", 1800),
                "device_refresh_seconds": c.get("device_refresh_seconds", 3600),
                "refresh_mode": c.get("refresh_mode", "fixed"),
                "adaptive_refresh": adaptive_refresh.options(c),
                "enabled_pages": c.get("enabled_pages", list(dict.fromkeys((c.get("page_schedule") or pagechoice.DEFAULT_SCHEDULE).values()))),
                "page_schedule": c.get("page_schedule", pagechoice.DEFAULT_SCHEDULE),
                "advisories": c.get("advisories", True), "timezone": c["timezone"],
                "renderer_available": bool(c.get("renderer_url") or c.get("mirror_base"))}

    def save(self, data):
        keys = {"active_program", "device_refresh_seconds", "enabled_pages", "page_schedule", "advisories"}
        if not isinstance(data, dict) or not keys <= set(data) or set(data) - keys - {"server_refresh_seconds", "refresh_mode", "adaptive_refresh"}:
            raise ValueError("Send all settings fields, without unknown fields.")
        if data["active_program"] not in {p["id"] for p in PROGRAMS}:
            raise ValueError("Unknown program.")
        interval = data["device_refresh_seconds"]
        if type(interval) is not int or not 60 <= interval <= 86400:
            raise ValueError("Refresh must be between 60 and 86400 seconds.")
        server_interval = data.get("server_refresh_seconds", self.renderer.config.get("server_refresh_seconds", 1800))
        if type(server_interval) is not int or not 900 <= server_interval <= 86400:
            raise ValueError("Server generation must be between 15 minutes and 24 hours.")
        adaptive_refresh.validate({**self.renderer.config, **data})
        enabled = data["enabled_pages"]
        if not isinstance(enabled, list) or not enabled or any(p not in next(p["pages"] for p in PROGRAMS if p["id"] == "weather-cal") for p in enabled) or len(set(enabled)) != len(enabled):
            raise ValueError("Enable at least one valid render, without duplicates.")
        schedule = data["page_schedule"]
        if not isinstance(schedule, dict) or not schedule or any(not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", t) or p not in enabled for t, p in schedule.items()):
            raise ValueError("Schedule must contain valid times and enabled renders only.")
        if set(schedule.values()) != set(enabled):
            raise ValueError("Give every enabled render a start time.")
        if type(data["advisories"]) is not bool:
            raise ValueError("Advisories must be true or false.")
        with self.lock:
            # Preserve unrelated renderer/location settings; persist before publishing.
            config = dict(self.renderer.config)
            config.update(data)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            name = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent, delete=False) as f:
                    name = f.name
                    json.dump(config, f, indent=2)
                    f.write("\n")
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(name, self.path)
            finally:
                if name and os.path.exists(name):
                    os.unlink(name)
            self.renderer.config = config
            self.renderer.settings_changed.set()
        return self.snapshot()


def make_handler(settings):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body, kind="application/json"):
            if not isinstance(body, bytes):
                body = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/api/settings":
                self.reply(200, settings.snapshot())
            elif path == "/api/display/status":
                self.reply(200, settings.renderer.activity.snapshot(settings.renderer.config["timezone"]))
            elif path == "/":
                self.reply(200, Path(__file__).with_name("dashboard.html").read_bytes(), "text/html; charset=utf-8")
            else:
                self.reply(404, {"error": "Not found"})

        def do_POST(self):
            if self.path not in ("/api/settings", "/api/display/reset"):
                return self.reply(404, {"error": "Not found"})
            # JSON plus same-origin checking prevents cross-site form writes.
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + self.headers.get("Host", ""):
                return self.reply(403, {"error": "Cross-origin write rejected"})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.reply(415, {"error": "JSON required"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384:
                    raise ValueError("Invalid request size")
                data = json.loads(self.rfile.read(length))
                if self.path == "/api/display/reset":
                    if data != {}:
                        raise ValueError("Reset takes an empty JSON object.")
                    result = settings.display.reset(settings.renderer.config.get("nook_adb_address", ""))
                else:
                    result = settings.save(data)
                self.reply(200, result)
            except ResetError as exc:
                self.reply(exc.status, {"error": str(exc)})
            except (ValueError, TypeError) as exc:
                self.reply(400, {"error": str(exc)})
            except OSError:
                self.reply(500, {"error": "Could not save settings; previous settings retained."})
    return Handler
