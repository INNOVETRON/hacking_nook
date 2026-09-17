"""Versioned LAN control plane. Program adapters remain server-side."""
import json
import io
from PIL import Image
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import uuid
from urllib.request import urlopen
from datetime import datetime
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit, parse_qs, unquote
import pagechoice
import adaptive_refresh
import program_schedule
import display_preview
import program_options
import local_programs
from media_library import MediaLibrary, MAX_UPLOAD
from display_control import DisplayControl, ResetError

PROGRAMS = [
    {"id":"photo-frame","name":"Photo / Art Frame","description":"Your own rotating e-ink gallery","pages":[]},
    {"id":"countdown","name":"Countdown","description":"Make the next big date worth looking forward to","pages":[]},
    {"id":"daylight","name":"Seasonal Daylight","description":"Sunrise, sunset and the changing length of the day","pages":[]},
    {"id": "clock-calendar", "name": "Clock & calendar", "description": "A quiet clock snapshot and monthly calendar", "pages": []},
    {"id": "weather-cal", "name": "Weather & forecast", "description": "Your day, at a glance",
     "pages": ["hourly", "today", "daily", "tomorrow"]},
    {"id": "simple-weather", "name": "Simple Weather", "description": "Big, clear weather and the next four hours",
     "pages": []},
]


class Settings:
    def __init__(self, renderer, path):
        self.renderer = renderer
        self.path = Path(path)
        self.lock = threading.RLock()
        self.library = getattr(renderer,'library',None) or MediaLibrary(self.path.parent/'media')
        self.program_renderer = getattr(renderer,'programs',None) or local_programs.ProgramRenderer(self.library,self.path.parent/'.cache')
        self.display = DisplayControl()

    def snapshot(self):
        c = self.renderer.config
        seconds, reason = adaptive_refresh.from_png(getattr(self.renderer, "current", lambda: b"")(), dict(c, active_program=program_schedule.active(c)))
        return {"app_settings": program_options.options(c), "reminders":[program_options.reminder_view(r,c["timezone"],time.time()) for r in c.get("reminders",[])], "program_schedule_enabled": c.get('program_schedule_enabled', False),
                "program_schedule": c.get('program_schedule', {'06:00':'simple-weather','10:00':'clock-calendar','18:00':'weather-cal','22:00':'simple-weather'}),
                "current_program": program_schedule.selected(c), "refresh_preview": {"seconds": seconds, "reason": reason}, "version": 1, "programs": PROGRAMS, "active_program": c.get("active_program", "weather-cal"),
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
        if not isinstance(data, dict) or not keys <= set(data) or set(data) - keys - {"server_refresh_seconds", "refresh_mode", "adaptive_refresh", "program_schedule_enabled", "program_schedule", "app_settings"}:
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
        program_schedule.validate({**self.renderer.config, **data})
        program_options.validate({**self.renderer.config, **data},self.library)
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
        return self._commit(data)

    def _commit(self, data):
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

    def reminder(self, data):
        if not isinstance(data,dict):raise ValueError('Send a reminder object.')
        with self.lock:
            records=list(self.renderer.config.get('reminders',[]))
            ident=data.get('id') or uuid.uuid4().hex
            if data.get('action')=='delete':
                return self._commit({'reminders':[r for r in records if r['id']!=ident]})
            if set(data)-{'action','id','title','message','when','minutes','icon','repeat'}:
                raise ValueError('Unknown reminder field.')
            title=data.get('title','');message=data.get('message','');minutes=data.get('minutes',15);icon=data.get('icon','calendar')
            if not isinstance(title,str) or not title.strip() or len(title)>60 or not isinstance(message,str) or len(message)>180:
                raise ValueError('Add a title (up to 60 characters) and message (up to 180).')
            if type(minutes) is not int or not 1<=minutes<=1440 or icon not in program_options.ICONS:
                raise ValueError('Choose a duration of 1–1440 minutes and a valid icon.')
            repeat=data.get('repeat','none')
            if repeat not in program_options.REPEATS:
                raise ValueError('Choose once, daily, weekdays or weekly.')
            at=program_options.reminder_at(data.get('when'),self.renderer.config['timezone'])
            if at < time.time()-60 and repeat=='none':
                raise ValueError('Choose a reminder time in the future.')
            if len(records)>=100 and not any(r['id']==ident for r in records):
                raise ValueError('Delete an old reminder before adding another (100 maximum).')
            record=dict(id=ident,title=title.strip(),message=message,minutes=minutes,icon=icon,at=at,when=data['when'],repeat=repeat)
            if any(r['id']!=ident and program_options.reminders_overlap(record,r,self.renderer.config['timezone']) for r in records):
                raise ValueError('This reminder overlaps another one. Choose a different time or duration.')
            return self._commit({'reminders':[r for r in records if r['id']!=ident]+[record]})

    def delete_picture(self, ident):
        with self.lock:
            self.library.delete(ident)
            apps=program_options.options(self.renderer.config)
            if apps['countdown']['image']==ident:
                apps['countdown']['image']=''
                self._commit({'app_settings':apps})
            self.renderer.settings_changed.set()
            return {'pictures':self.library.list(),'settings':self.snapshot()}


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
            query = parse_qs(urlsplit(self.path).query)
            if path == '/api/media':
                return self.reply(200, {'pictures':settings.library.list()})
            if path.startswith('/api/media/'):
                try:
                    return self.reply(200,settings.library.path(path.rsplit('/',1)[-1]).read_bytes(),'image/png')
                except (ValueError,OSError):
                    return self.reply(404,{'error':'Picture not found'})
            if path == '/api/program/preview.png':
                program=query.get('program',[''])[0]
                if program not in program_schedule.PROGRAMS:
                    return self.reply(400,{'error':'Choose a program'})
                try:
                    now=datetime.now(ZoneInfo(settings.renderer.config['timezone']))
                    if program=='daylight':
                        settings.program_renderer.refresh_daylight(settings.renderer.config,now)
                    if program in local_programs.LOCAL:
                        if program=='countdown':
                            settings.program_renderer.refresh_temperature(settings.renderer.config)
                        body=settings.program_renderer.render(program,settings.renderer.config,now,query.get('image',[None])[0])
                    else:
                        base=(settings.renderer.config.get('renderer_url') or settings.renderer.config.get('mirror_base') or '').rstrip('/')
                        page='simple-weather' if program=='simple-weather' else pagechoice.choose(settings.renderer.config,settings.renderer.weather,now)[0]
                        if not base:raise ValueError('Renderer unavailable')
                        with urlopen(base+'/'+page+'.png',timeout=15) as response:body=response.read()
                        with Image.open(io.BytesIO(body)) as image:image.load()
                    return self.reply(200,body,'image/png')
                except (OSError,ValueError):
                    return self.reply(400,{'error':'Could not preview this program'})
            if path == "/api/settings":
                self.reply(200, settings.snapshot())
            elif path == "/api/display/preview.png":
                body = settings.renderer.activity.preview()
                self.reply(200 if body else 404, body or b'', 'image/png')
            elif path == "/api/display/status":
                result = settings.renderer.activity.snapshot(settings.renderer.config["timezone"])
                delivered = settings.renderer.activity.preview()
                result['image'] = display_preview.metadata(delivered)
                result['has_preview'] = bool(delivered)
                result['renderer_retrying'] = bool(getattr(settings.renderer, 'retrying', False))
                result['current_program'] = program_schedule.selected(settings.renderer.config)
                self.reply(200, result)
            elif path == "/dashboard.js":
                self.reply(200, Path(__file__).with_name("dashboard.js").read_bytes(), "text/javascript; charset=utf-8")
            elif path == "/":
                self.reply(200, Path(__file__).with_name("dashboard.html").read_bytes(), "text/html; charset=utf-8")
            else:
                self.reply(404, {"error": "Not found"})

        def do_POST(self):
            if self.path not in ("/api/settings", "/api/display/reset", "/api/media", "/api/media/delete", "/api/reminders"):
                return self.reply(404, {"error": "Not found"})
            # JSON plus same-origin checking prevents cross-site form writes.
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + self.headers.get("Host", ""):
                return self.reply(403, {"error": "Cross-origin write rejected"})
            if self.path == '/api/media':
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=MAX_UPLOAD:
                        raise ValueError('Choose an image smaller than 12 MB.')
                    item=settings.library.add(self.rfile.read(length),unquote(self.headers.get('X-File-Name','Picture')))
                    settings.renderer.settings_changed.set()
                    return self.reply(200,{'picture':item,'pictures':settings.library.list()})
                except (ValueError,TypeError) as exc:
                    return self.reply(400,{'error':str(exc)})
                except OSError:
                    return self.reply(500,{'error':'Could not store the picture.'})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.reply(415, {"error": "JSON required"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    raise ValueError("Invalid request size")
                data = json.loads(self.rfile.read(length))
                if self.path == "/api/display/reset":
                    if data != {}:
                        raise ValueError("Reset takes an empty JSON object.")
                    result = settings.display.reset(settings.renderer.config.get("nook_adb_address", ""))
                elif self.path == '/api/reminders':
                    result = settings.reminder(data)
                elif self.path == '/api/media/delete':
                    result = settings.delete_picture(data.get('id'))
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
