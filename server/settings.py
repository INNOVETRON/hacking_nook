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

PROGRAMS = [{"id": "weather-cal", "name": "Weather & forecast", "description": "Your day, at a glance", "pages": ["hourly", "today", "daily", "tomorrow"]}]


class Settings:
    def __init__(self, renderer, path):
        self.renderer = renderer
        self.path = Path(path)
        self.lock = threading.Lock()

    def snapshot(self):
        c = self.renderer.config
        return {"version": 1, "programs": PROGRAMS, "active_program": c.get("active_program", "weather-cal"),
                "device_refresh_seconds": c.get("device_refresh_seconds", 3600),
                "enabled_pages": c.get("enabled_pages", list(dict.fromkeys((c.get("page_schedule") or pagechoice.DEFAULT_SCHEDULE).values()))),
                "page_schedule": c.get("page_schedule", pagechoice.DEFAULT_SCHEDULE),
                "advisories": c.get("advisories", True), "timezone": c["timezone"],
                "renderer_available": bool(c.get("renderer_url") or c.get("mirror_base"))}

    def save(self, data):
        keys = {"active_program", "device_refresh_seconds", "enabled_pages", "page_schedule", "advisories"}
        if not isinstance(data, dict) or set(data) != keys:
            raise ValueError("Send all settings fields, without unknown fields.")
        if data["active_program"] != "weather-cal":
            raise ValueError("Unknown program.")
        interval = data["device_refresh_seconds"]
        if type(interval) is not int or not 60 <= interval <= 86400:
            raise ValueError("Refresh must be between 60 and 86400 seconds.")
        enabled = data["enabled_pages"]
        if not isinstance(enabled, list) or not enabled or any(p not in PROGRAMS[0]["pages"] for p in enabled) or len(set(enabled)) != len(enabled):
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
            elif path == "/":
                self.reply(200, Path(__file__).with_name("dashboard.html").read_bytes(), "text/html; charset=utf-8")
            else:
                self.reply(404, {"error": "Not found"})

        def do_POST(self):
            if self.path != "/api/settings":
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
                result = settings.save(json.loads(self.rfile.read(length)))
                self.reply(200, result)
            except (ValueError, TypeError) as exc:
                self.reply(400, {"error": str(exc)})
            except OSError:
                self.reply(500, {"error": "Could not save settings; previous settings retained."})
    return Handler
