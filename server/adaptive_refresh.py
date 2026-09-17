"""Pure adaptive wake policy shared by the image renderer and image server."""
from datetime import datetime, timedelta
import io
import json
import math
import re
from zoneinfo import ZoneInfo

DEFAULTS = dict(min_seconds=900, max_seconds=7200, quiet_enabled=True,
                quiet_start='00:00', quiet_end='06:00', temperature_delta_c=3,
                precipitation_percent=50, wind_delta_kmh=20)
PNG_KEY = 'nook_weather_v1'


def options(config):
    return {**DEFAULTS, **config.get('adaptive_refresh', {})}


def validate(config):
    if config.get('refresh_mode', 'fixed') not in ('fixed', 'adaptive'):
        raise ValueError('Refresh mode must be fixed or adaptive.')
    values = config.get('adaptive_refresh', {})
    if not isinstance(values, dict) or set(values) - set(DEFAULTS):
        raise ValueError('Unknown adaptive refresh setting.')
    opt = options(config)
    for key, lo, hi in [('min_seconds',900,3600), ('max_seconds',900,14400),
                         ('temperature_delta_c',2,10), ('precipitation_percent',10,100),
                         ('wind_delta_kmh',10,60)]:
        if type(opt[key]) is not int or not lo <= opt[key] <= hi:
            raise ValueError('Invalid adaptive setting: ' + key)
    if opt['max_seconds'] < opt['min_seconds']:
        raise ValueError('Maximum refresh must be at least the minimum.')
    if type(opt['quiet_enabled']) is not bool:
        raise ValueError('Quiet hours must be true or false.')
    for key in ('quiet_start','quiet_end'):
        if not isinstance(opt[key], str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', opt[key]):
            raise ValueError('Quiet hours must use HH:MM.')
    if opt['quiet_start'] == opt['quiet_end']:
        raise ValueError('Quiet hours need different start and end times.')
    return opt


def quiet_window(now, config):
    """Return active quiet interval and next start, using local wall-clock times.

    UTC timestamps are used for elapsed time, including across DST changes.
    """
    opt = options(config)
    if not opt['quiet_enabled']:
        return None, None
    start_h, start_m = map(int, opt['quiet_start'].split(':'))
    end_h, end_m = map(int, opt['quiet_end'].split(':'))
    windows = []
    for delta in (-1,0,1,2):
        day = now.date() + timedelta(days=delta)
        start = datetime(day.year,day.month,day.day,start_h,start_m,tzinfo=now.tzinfo)
        end = datetime(day.year,day.month,day.day,end_h,end_m,tzinfo=now.tzinfo)
        if end <= start:
            end += timedelta(days=1)
        windows.append((start,end))
    active = next(((a,b) for a,b in windows if a.timestamp() <= now.timestamp() < b.timestamp()), None)
    future = min(a for a,b in windows if a.timestamp() > now.timestamp())
    return active, future


def category(icon):
    icon = (icon or '').lower().replace('/day/','/').replace('/night/','/')
    if 'thunder' in icon or 'storm' in icon: return 'storm'
    if 'snow' in icon: return 'snow'
    if 'rain' in icon or 'shower' in icon: return 'rain'
    if 'fog' in icon: return 'fog'
    if 'partly' in icon: return 'partly cloudy'
    if 'cloud' in icon: return 'cloudy'
    if 'clear' in icon: return 'clear'
    return None


def _number(value):
    return type(value) in (float,int) and math.isfinite(value)


def decide(metadata, config, now=None):
    """Return (seconds, human-readable reason). Never fetch data here."""
    fixed = config.get('device_refresh_seconds',3600)
    if config.get('refresh_mode','fixed') != 'adaptive' or config.get('active_program') != 'simple-weather':
        return fixed, 'Fixed interval'
    now = now or datetime.now(ZoneInfo(config['timezone']))
    opt = options(config)
    retry = opt['min_seconds']
    active, next_start = quiet_window(now,config)
    boundary = active[1] if active else next_start
    fallback_seconds = min(retry,max(60,math.ceil(boundary.timestamp()-now.timestamp()))) if boundary else retry
    fallback = (fallback_seconds, 'Waiting for fresh forecast image')
    if not isinstance(metadata, dict) or metadata.get('program') != 'simple-weather':
        return fallback
    generated = metadata.get('generated_at')
    if not _number(generated) or not -60 <= now.timestamp()-generated <= min(5400, config.get('server_refresh_seconds',1800)+900):
        return fallback
    rows = metadata.get('hours')
    if not isinstance(rows,list) or not rows or not _number(metadata.get('temperature_c')):
        return fallback
    if any(not isinstance(r,dict) or not all(_number(r.get(k)) for k in ('at','temperature_c','wind_kmh','rain')) or not r.get('condition') for r in rows):
        return fallback
    if not metadata.get('condition') or not _number(metadata.get('wind_kmh')):
        return fallback
    if active:
        end = active[1].timestamp()
        # Sleep overnight only with an image specifically prepared for this morning.
        if metadata.get('quiet_until') == end and metadata.get('morning_hours',0) >= 4:
            return min(86400,max(60,math.ceil(end-now.timestamp()))), 'Quiet hours; wake at ' + active[1].strftime('%H:%M')
        return fallback
    if metadata.get('quiet_until'):
        return fallback  # A retained overnight image must not get a daytime long sleep.
    future = sorted((r for r in rows if r['at'] >= generated),key=lambda r:r['at'])
    if not future:
        return fallback
    deadline = min(now.timestamp()+opt['max_seconds'], generated+opt['max_seconds'], future[-1]['at'])
    reason = 'Stable weather'
    if next_start and next_start.timestamp() < deadline:
        deadline, reason = next_start.timestamp(), 'Quiet hours begin'
    wet = metadata['condition'] in ('rain','snow','storm')
    for row in future:
        change = None
        if abs(row['temperature_c']-metadata['temperature_c']) >= opt['temperature_delta_c']:
            change = 'Temperature change'
        rain = row['condition'] in ('rain','snow','storm') or row['rain'] >= opt['precipitation_percent']
        if rain != wet:
            change = 'Precipitation change'
        if row['condition'] != metadata['condition']:
            change = 'Conditions change'
        if abs(row['wind_kmh']-metadata['wind_kmh']) >= opt['wind_delta_kmh']:
            change = 'Wind change'
        if change:
            # Quarter-hour lead for conditions/rain; half-hour cap for imminent changes.
            event = row['at'] - (900 if change != 'Temperature change' else 0)
            if row['at'] <= now.timestamp()+3600:
                event = min(event,now.timestamp()+1800)
            if event < deadline:
                deadline, reason = event, change
    seconds = max(retry, math.floor(deadline-now.timestamp()))
    # Clock boundaries may be closer than the minimum interval.
    if next_start:
        seconds = min(seconds,max(60,math.ceil(next_start.timestamp()-now.timestamp())))
    return min(opt['max_seconds'],seconds), reason


def from_png(body, config, now=None):
    if config.get('refresh_mode','fixed') != 'adaptive' or config.get('active_program') != 'simple-weather':
        return decide(None,config,now)
    from PIL import Image
    try:
        with Image.open(io.BytesIO(body)) as image:
            raw = image.info.get(PNG_KEY,'')
        metadata = json.loads(raw) if raw else None
        return decide(metadata,config,now)
    except (ValueError,TypeError,KeyError,OSError,OverflowError):
        return decide(None,config,now)
