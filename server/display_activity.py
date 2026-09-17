"""Persist successful Nook image deliveries; browser previews are not updates."""
from datetime import datetime, timedelta
import json
import logging
import os
from pathlib import Path
import tempfile
import threading
import time
from zoneinfo import ZoneInfo

LOG = logging.getLogger(__name__)


class DisplayActivity:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.started_at = time.time()
        self.events = []
        try:
            data = json.loads(self.path.read_text())
            self.started_at = float(data['started_at'])
            self.events = data['events']
            for event in self.events:
                float(event['at'])
                int(event['seconds'])
                str(event['reason'])
        except FileNotFoundError:
            self._persist()
        except (OSError, ValueError, KeyError, TypeError):
            LOG.exception('Could not load display fetch history')
            self.started_at = time.time()
            self.events = []

    def _persist(self):
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', dir=self.path.parent, delete=False) as handle:
                temporary = handle.name
                json.dump({'started_at': self.started_at, 'events': self.events}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError:
            LOG.exception('Could not persist display fetch history')
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def record(self, seconds, reason, now=None):
        now = time.time() if now is None else now
        with self.lock:
            self.events.append({'at': now, 'seconds': seconds, 'reason': reason})
            # Three days cover today/yesterday even across DST. Keep the last
            # delivery indefinitely so an offline display still has a last fetch.
            self.events = [e for e in self.events if e['at'] >= now - 3 * 86400][-10000:]
            self._persist()

    def snapshot(self, timezone, now=None):
        now = time.time() if now is None else now
        zone = ZoneInfo(timezone)
        today = datetime.fromtimestamp(now, zone).date()
        with self.lock:
            events = list(self.events)
            started = self.started_at
        days = []
        for day in (today, today - timedelta(days=1)):
            matching = [e for e in reversed(events) if datetime.fromtimestamp(e['at'], zone).date() == day]
            days.append({'date': day.isoformat(), 'count': len(matching), 'events': matching})
        last = events[-1] if events else None
        return {'timezone': timezone, 'started_at': started, 'last_fetch': last,
                'next_fetch': last['at'] + last['seconds'] if last else None,
                'days': days}
