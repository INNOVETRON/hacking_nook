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
        self.batteries = []
        self.failures = []
        try:
            data = json.loads(self.path.read_text())
            self.started_at = float(data['started_at'])
            self.events = data['events']
            self.batteries = data.get('batteries', [])
            self.failures = data.get('failures', [])
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
                json.dump({'started_at': self.started_at, 'events': self.events, 'batteries': self.batteries, 'failures': self.failures}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError:
            LOG.exception('Could not persist display fetch history')
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def failed(self, reason):
        with self.lock:
            now = time.time()
            self.failures = [e for e in self.failures if e['at'] > now - 3*86400]
            self.failures.append({'at': now, 'reason': reason})
            self.failures = self.failures[-10000:]
            self._persist()

    def record(self, seconds, reason, now=None, headers=None):
        now = time.time() if now is None else now
        with self.lock:
            event = {'at': now, 'seconds': seconds, 'reason': reason}
            headers = headers or {}
            try:
                event['device_failures'] = max(0, min(2147483647, int(headers.get('X-Nook-Failures'))))
            except (TypeError, ValueError):
                pass
            try:
                level = int(headers.get('X-Nook-Battery'))
                charging = headers.get('X-Nook-Charging')
                if 0 <= level <= 100 and charging in ('0', '1'):
                    self.batteries.append({'at': now, 'percent': level, 'charging': charging == '1'})
                    self.batteries = [b for b in self.batteries if b['at'] >= now - 30*86400][-50000:]
            except (TypeError, ValueError):
                pass
            self.events.append(event)
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
            batteries = list(self.batteries)
            failures = list(self.failures)
        days = []
        for day in (today, today - timedelta(days=1)):
            matching = [e for e in reversed(events) if datetime.fromtimestamp(e['at'], zone).date() == day]
            days.append({'date': day.isoformat(), 'count': len(matching), 'events': matching})
        last = events[-1] if events else None
        battery = dict(batteries[-1]) if batteries else None
        if battery:
            battery['days_remaining'] = None
            # Only a continuous unplugged discharge segment, at least a day and
            # a 3-point drop. A charge or upward jump starts a new segment.
            segment = [battery]
            for previous in reversed(batteries[:-1]):
                if previous['charging'] or segment[-1]['charging'] or previous['percent'] < segment[-1]['percent']:
                    break
                segment.append(previous)
            first = segment[-1]
            elapsed, drop = battery['at'] - first['at'], first['percent'] - battery['percent']
            if elapsed >= 86400 and drop >= 3 and not battery['charging']:
                battery['days_remaining'] = round(battery['percent'] / drop * elapsed / 86400, 1)
        for day in days:
            begin = datetime.fromisoformat(day['date']).replace(tzinfo=zone).timestamp()
            end = (datetime.fromisoformat(day['date']) + timedelta(days=1)).replace(tzinfo=zone).timestamp()
            covered = 0
            for index, event in enumerate(events):
                until = min(event['at'] + event['seconds'], events[index+1]['at'] if index+1 < len(events) else now, now, end)
                covered += max(0, until-max(begin,event['at']))
            # No savings credit for unexplained offline hours beyond a sent timer.
            day['hourly_baseline'] = round(covered/3600, 1)
            day['fetches_avoided'] = round(covered/3600-day['count'], 1)
            day['failures'] = [f for f in reversed(failures) if begin <= f['at'] < end]
        return {'battery': battery,
                'reliability': 'Waiting for first fetch' if not last else ('Overdue' if now > last['at']+last['seconds']+300 else 'On schedule'),
                'device_failures': next((e['device_failures'] for e in reversed(events) if 'device_failures' in e), None),
                'timezone': timezone, 'started_at': started, 'last_fetch': last,
                'next_fetch': last['at'] + last['seconds'] if last else None,
                'days': days}
