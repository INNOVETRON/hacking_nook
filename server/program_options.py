"""Validated program options and one-shot reminders."""
from datetime import datetime
import math
from zoneinfo import ZoneInfo

DEFAULTS = {
    'clock-calendar': {'title':'AT A GLANCE','format':'12','week_start':'monday','refresh_minutes':30},
    'photo-frame': {'minutes':60,'fit':'contain','border':24,'caption':False,'dither':False},
    'countdown': {'title':'Something to look forward to','date':'','icon':'star','image':'','subtitle':'','complete':'Today is the day!','theme':'light','refresh_minutes':60},
    'daylight': {'title':'FOLLOW THE LIGHT','format':'12','refresh_minutes':60},
}
ICONS = {'star','heart','plane','gift','calendar'}


def options(config):
    supplied = config.get('app_settings', {})
    return {key: dict(value, **supplied.get(key, {})) for key,value in DEFAULTS.items()}


def validate(config, library=None):
    supplied = config.get('app_settings', {})
    if not isinstance(supplied, dict) or set(supplied)-set(DEFAULTS):
        raise ValueError('Unknown program settings.')
    for key, fields in supplied.items():
        if not isinstance(fields,dict) or set(fields)-set(DEFAULTS[key]):
            raise ValueError('Unknown settings for '+key)
    values = options(config)
    for key, fields in values.items():
        for field in ('title','subtitle','complete'):
            if field in fields and (not isinstance(fields[field],str) or len(fields[field]) > (100 if field=='subtitle' else 60)):
                raise ValueError('Keep titles/messages under 60 characters and subtitles under 100.')
        for field in ('minutes','refresh_minutes'):
            if field in fields and (type(fields[field]) is not int or not 1 <= fields[field] <= 1440):
                raise ValueError('Program intervals must be 1–1440 whole minutes.')
    for key in ('clock-calendar','daylight'):
        if values[key]['format'] not in ('12','24'):
            raise ValueError('Choose 12 or 24 hour time.')
    if values['clock-calendar']['week_start'] not in ('monday','sunday'):
        raise ValueError('Choose Monday or Sunday for the calendar.')
    frame=values['photo-frame']
    if frame['fit'] not in ('contain','cover') or type(frame['border']) is not int or not 0 <= frame['border'] <= 60 or any(type(frame[k]) is not bool for k in ('caption','dither')):
        raise ValueError('Invalid picture frame options.')
    countdown=values['countdown']
    if countdown['date']:
        try:
            datetime.strptime(countdown['date'],'%Y-%m-%d')
        except (ValueError,TypeError):
            raise ValueError('Choose a valid countdown date.')
    if countdown['icon'] not in ICONS or countdown['theme'] not in ('light','dark'):
        raise ValueError('Choose a countdown icon and theme.')
    if countdown['image']:
        if library is None or not library.path(countdown['image']).exists():
            raise ValueError('Choose a picture in your library.')


def reminder_at(value, timezone):
    try:
        parsed=datetime.strptime(value,'%Y-%m-%dT%H:%M')
        aware=parsed.replace(tzinfo=ZoneInfo(timezone))
        if datetime.fromtimestamp(aware.timestamp(),aware.tzinfo).replace(tzinfo=None) != parsed:
            raise ValueError()
        return aware.timestamp()
    except (TypeError,ValueError):
        raise ValueError('Choose a valid local date/time (not a skipped daylight-saving hour).')


def active_reminder(config, now):
    stamp=now.timestamp()
    return next((r for r in config.get('reminders',[]) if r['at'] <= stamp < r['at']+r['minutes']*60), None)


def reminder_boundaries(config, now):
    stamp=now.timestamp()
    return [t for r in config.get('reminders',[]) for t in (r['at'],r['at']+r['minutes']*60) if t > stamp]
