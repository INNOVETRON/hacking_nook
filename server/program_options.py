"""Validated program options and one-shot reminders."""
from datetime import datetime, timedelta
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


REPEATS = {'none', 'daily', 'weekdays', 'weekly'}


def occurrences(reminder, timezone, start, end):
    """Occurrences in an epoch window, repeated at the original local wall time."""
    if reminder.get('repeat','none') == 'none':
        return [reminder] if start <= reminder['at'] < end else []
    zone=ZoneInfo(timezone)
    first=datetime.fromtimestamp(reminder['at'],zone)
    day=max(first.date(),datetime.fromtimestamp(start,zone).date())
    last=datetime.fromtimestamp(end,zone).date()
    result=[]
    while day <= last:
        repeat=reminder['repeat']
        if repeat=='daily' or repeat=='weekdays' and day.weekday()<5 or repeat=='weekly' and day.weekday()==first.weekday():
            local=datetime.combine(day,first.time().replace(tzinfo=None)).replace(tzinfo=zone,fold=0)
            stamp=local.timestamp()
            # Spring's missing clock time is skipped; autumn's repeated time runs once.
            if datetime.fromtimestamp(stamp,zone).replace(tzinfo=None)==local.replace(tzinfo=None) and max(start,reminder['at']) <= stamp < end:
                result.append(dict(reminder,at=stamp))
        day+=timedelta(days=1)
    return result


def active_reminder(config, now):
    stamp=now.timestamp();zone=config.get('timezone','America/Edmonton')
    for reminder in config.get('reminders',[]):
        for occurrence in occurrences(reminder,zone,stamp-86400,stamp+1):
            if occurrence['at'] <= stamp < occurrence['at']+occurrence['minutes']*60:
                return occurrence
    return None


def reminder_boundaries(config, now):
    stamp=now.timestamp();zone=config.get('timezone','America/Edmonton')
    # Eight days finds the next weekly occurrence, including across DST.
    return [t for r in config.get('reminders',[]) for occurrence in occurrences(r,zone,stamp-86400,stamp+9*86400)
            for t in (occurrence['at'],occurrence['at']+occurrence['minutes']*60) if t > stamp]


def reminder_view(reminder, timezone, now):
    future=occurrences(reminder,timezone,now-86400,now+9*86400)
    current=next((r for r in future if r['at'] <= now < r['at']+r['minutes']*60),None)
    upcoming=next((r for r in future if r['at']>now),None)
    if reminder.get('repeat','none')=='none' and reminder['at']>now:
        upcoming=reminder
    # A recurring series can start more than nine days from now.
    if upcoming is None and reminder['at']>now:
        upcoming=next(iter(occurrences(reminder,timezone,reminder['at'],reminder['at']+9*86400)),None)
    return dict(reminder,repeat=reminder.get('repeat','none'),occurrence_at=(current or upcoming or {}).get('at'),showing=bool(current))


def reminders_overlap(left,right,timezone):
    # Daily/weekly patterns repeat each week; a full year also covers DST changes.
    start=max(left['at'],right['at'])-86400
    end=start+370*86400
    a=occurrences(left,timezone,start,end);b=occurrences(right,timezone,start,end)
    i=j=0
    while i<len(a) and j<len(b):
        if a[i]['at'] < b[j]['at']+b[j]['minutes']*60 and b[j]['at'] < a[i]['at']+a[i]['minutes']*60:
            return True
        if a[i]['at']+a[i]['minutes']*60 <= b[j]['at']:i+=1
        else:j+=1
    return False
