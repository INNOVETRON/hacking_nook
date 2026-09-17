"""Concept B: sharp portrait weather artwork rendered by the existing pipeline."""
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo
import adaptive_refresh
from html import escape
import math


def symbol(icon):
    name = (icon or '').lower()
    night = '/night/' in name
    sun = '<circle cx="50" cy="50" r="21"/>' + ''.join(
        '<path d="M %.2f %.2f L %.2f %.2f"/>' % (
            50+33*math.cos(i*math.pi/4),50+33*math.sin(i*math.pi/4),
            50+44*math.cos(i*math.pi/4),50+44*math.sin(i*math.pi/4)) for i in range(8))
    moon = '<path d="M 65 10 A 40 40 0 1 0 90 70 A 38 38 0 0 1 65 10 Z"/>'
    cloud = '<path d="M 23 70 C 0 70 0 40 23 39 C 24 10 65 9 71 38 C 98 31 107 70 80 70 Z"/>'
    if 'partly' in name:
        art = '<g transform="translate(0,-5) scale(.65)">'+(moon if night else sun)+'</g>'+cloud
        label = 'PARTLY CLOUDY'
    elif 'clear' in name:
        art, label = (moon if night else sun), 'CLEAR'
    elif any(k in name for k in ('cloud', 'rain', 'snow', 'thunder', 'storm', 'fog')):
        art, label = cloud, 'CLOUDY'
    else:
        art, label = '<text x="50" y="70" text-anchor="middle" stroke="none" fill="black" font-size="65">?</text>', 'WEATHER'
    if 'snow' in name:
        art += '<path d="M 25 82 v 14 m -6 -7 h 12 M 52 82 v 14 m -6 -7 h 12 M 79 82 v 14 m -6 -7 h 12"/>'
        label = 'SNOW'
    elif 'thunder' in name or 'storm' in name:
        art += '<path d="M 53 72 l -15 15 h 15 l -10 13"/>'
        label = 'THUNDERSTORM'
    elif 'rain' in name or 'shower' in name:
        art += '<path d="M 28 80 l -5 12 M 53 80 l -5 12 M 78 80 l -5 12"/>'
        label = 'RAIN'
    elif 'fog' in name:
        art += '<path d="M 10 82 h 80 M 20 94 h 60"/>'
        label = 'FOG'
    return '<g fill="white" stroke="black" stroke-width="6" stroke-linecap="round" stroke-linejoin="round">'+art+'</g>', label


def briefing(current,hourly):
    parts=[]
    feels=current.get('temperature',{}).get('feels_like')
    if feels is not None:
        parts.append('Feels '+str(round(feels))+'°')
    wet=next((r for r in hourly[:6] if (r.get('rain_probability') or 0)>=50),None)
    if wet:
        kind='Snow' if 'snow' in (wet.get('icon') or '') else 'Rain'
        parts.append(kind+' '+wet['dt'].strftime('%-I%p').lower())
    else:
        parts.append('Low precip. chance' if hourly and all(r.get('rain_probability') is not None for r in hourly[:6]) else 'Precip. unavailable')
    winds=[(r.get('wind') or {}).get('value') for r in hourly[:6]]
    winds=[w for w in winds if w is not None]
    if winds:
        unit=(hourly[0].get('wind') or {}).get('unit','kmh')
        strong = max(winds) >= (25 if unit=='mph' else 40)
        parts.append(('Strong wind ' if strong else 'Wind ')+str(round(max(winds)))+(' km/h' if unit=='kmh' else ' '+unit))
    return ' · '.join(parts)


def trend(rows):
    valid=[(i,r['temperature'].get('value')) for i,r in enumerate(rows) if r['temperature'].get('value') is not None]
    if len(valid)<2:
        return '<text x="300" y="460" text-anchor="middle" font-size="20">Trend unavailable</text>'
    low,high=min(v for _,v in valid),max(v for _,v in valid)
    span=max(4,high-low)
    points=[(42+i*516/max(1,len(rows)-1),470-(v-low)*65/span) for i,v in valid]
    line=' '.join(f'{x:.1f},{y:.1f}' for x,y in points)
    labels=''.join(f'<text x="{42+i*516/max(1,len(rows)-1):.1f}" y="509" text-anchor="middle" font-size="17">{escape(rows[i]["dt"].strftime("%-I%p"))}</text>' for i in sorted(set([0,len(rows)//2,len(rows)-1])))
    return f'<text x="30" y="391" font-size="16">NEXT {len(rows)} HOURS · {low}° TO {high}°</text><polyline points="{line}" fill="none" stroke="black" stroke-width="4" stroke-linejoin="round"/>'+labels


def artwork(current, hourly, now=None, overnight=None):
    now = now or datetime.now()
    pieces = []
    def text(x,y,value,size,anchor='middle',weight=700):
        pieces.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{escape(str(value))}</text>')
    def icon(x,y,size,path):
        art, label = symbol(path)
        pieces.append(f'<g transform="translate({x},{y}) scale({size/100})">{art}</g>')
        return label
    pieces.append('<rect width="600" height="128" fill="black"/><g fill="white">')
    text(145,112,now.day,112)
    text(394, 60,now.strftime('%A').upper(),30)
    text(394,102,now.strftime('%B').upper(),26)
    pieces.append('</g>')
    if overnight:
        # An unmistakable night card: dark masthead, tomorrow's morning reading,
        # sunrise, and an explicit wake time rather than an old current reading.
        pieces = ['<rect width="600" height="195" fill="black"/><g fill="white">']
        text(300,45,'WHILE YOU SLEEP',24)
        text(300,106,'MORNING BRIEFING',38)
        text(300,151,overnight.strftime('%A · %B %-d').upper(),23)
        pieces.append('</g>')
        first = hourly[0] if hourly else current
        label=icon(50,220,150,first.get('icon'))
        value=first['temperature'].get('value')
        text(395,335,('—' if value is None else str(value)+'°'),110)
        text(395,377,'AT '+overnight.strftime('%-I:%M %p'),22)
        sunrise=first.get('sunrise')
        dawn=datetime.fromisoformat(sunrise).strftime('%-I:%M %p') if sunrise else '—'
        text(300,425,'SUNRISE '+dawn+'  ·  '+label,21)
        summary=briefing(first,hourly)
        text(300,471,summary,min(19,550/max(1,len(summary))/.62))
        pieces.append('<path d="M 24 503 H 576" stroke="black" stroke-width="3"/>')
        text(300,537,'MORNING FORECAST',22)
    else:
        label=icon(42,152,150,current.get('icon'))
        temp=current['temperature']
        value=f"{temp['value']}{temp['unit']}"
        text(387,268,value,min(98,350/max(1,len(value))/.64))
        text(387,313,label,23 if len(label)<14 else 18)
        summary=briefing(current,hourly)
        text(300,354,summary,min(19,550/max(1,len(summary))/.62))
        pieces.append(trend(hourly[:12]))
    rows=list(hourly[:4])
    for i in range(4):
        x=84+i*144
        if i:
            pieces.append(f'<path d="M {x-72} 553 V 752" stroke="black" stroke-width="1.5"/>')
        if i>=len(rows):
            text(x,641,'—',36)
            continue
        row=rows[i]
        text(x,578,row['dt'].strftime('%I %p').lstrip('0'),24)
        icon(x-42,592,84,row.get('icon'))
        text(x,709,('—' if row['temperature'].get('value') is None else str(row['temperature']['value'])+'°'),47)
        pop=row.get('rain_probability')
        text(x,735,'—' if pop is None else f'{round(pop)}% precip.',18)
        wind=row.get('wind') or {}
        bearing=wind.get('direction_degrees')
        direction='' if bearing is None else ['N','NE','E','SE','S','SW','W','NW'][int((bearing+22.5)//45)%8]
        speed=wind.get('value')
        text(x,759,'—' if speed is None else f'{direction} {round(speed)}',18)
    # The current adapter supplies the observation source and local timestamp.
    source=('NEXT UPDATE '+overnight.strftime('%-I:%M %p')) if overnight else (current.get('weather_text') or 'EDMONTON')
    text(18,790,source,12,'start')
    unit=(rows[0].get('wind') or {}).get('unit','kmh') if rows else 'kmh'
    text(582,790,'WIND '+('km/h' if unit=='kmh' else unit),12,'end')
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 800" role="img" aria-label="Simple Weather"><rect width="600" height="800" fill="white"/><g fill="black" font-family="DejaVu Sans, sans-serif">'+''.join(pieces)+'</g></svg>'


# Kept separate from artwork() so fixtures can exercise it without Chromium.
from views.page import Page


class SimpleWeatherPage(Page):
    requires = ('current_conditions','simple_hourly_forecasts')

    def __init__(self,*geometry):
        super().__init__('simple-weather',*geometry)

    def template(self,**kwargs):
        try:
            with urlopen(os.environ.get('NOOK_SETTINGS_URL','http://127.0.0.1:8001/api/settings'),timeout=3) as response:
                settings=json.load(response)
            adaptive_refresh.validate(settings)
            self._settings=settings
        except (OSError, ValueError, TypeError):
            settings=getattr(self,'_settings',{})
        zone=ZoneInfo(settings.get('timezone','America/Edmonton'))
        now=datetime.now(zone)
        current=kwargs['current_conditions']
        hours=kwargs['simple_hourly_forecasts']
        def local(stamp):
            return stamp.replace(tzinfo=zone) if stamp.tzinfo is None else stamp.astimezone(zone)
        def celsius(temp):
            value=temp.get('value')
            return None if value is None else ((value-32)*5/9 if 'F' in temp.get('unit','') else value)
        def wind_kmh(wind):
            value=wind.get('value')
            return None if value is None else (value*1.609344 if wind.get('unit')=='mph' else value)
        overnight=None
        if settings.get('refresh_mode')=='adaptive':
            # Prepare for a boundary just ahead of this scheduled render.
            window,_=adaptive_refresh.quiet_window(now+timedelta(minutes=5),settings)
            overnight=window[1] if window else None
        morning=[r for r in hours if overnight and local(r['dt']) >= overnight][:4]
        if overnight and len(morning)<4:
            overnight=None
        self._metadata=dict(program='simple-weather',generated_at=now.timestamp(),
            temperature_c=celsius(current['temperature']),
            condition=adaptive_refresh.category(current.get('icon')),
            wind_kmh=wind_kmh(current.get('wind') or {}),
            quiet_until=overnight.timestamp() if overnight else None,
            morning_hours=len(morning),hours=[dict(at=local(r['dt']).timestamp(),
                temperature_c=celsius(r['temperature']),condition=adaptive_refresh.category(r.get('icon')),
                wind_kmh=wind_kmh(r.get('wind') or {}),rain=r.get('rain_probability')) for r in hours])
        svg=artwork(current,morning if overnight else hours,now,overnight)
        self.airium=('<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;width:100%;height:100%;background:white;overflow:hidden}svg{display:block;width:100%;height:100%}</style></head><body>'+svg+'</body></html>').encode('utf-8')

    @property
    def png_path(self):
        path=super().png_path
        return path+'.stage' if getattr(self,'_staging',False) else path

    def save(self):
        # Publish pixels and the matching forecast as one atomic PNG. Never pair
        # an old cached image with metadata from a newer generation.
        from PIL import Image, PngImagePlugin
        target=super().png_path
        self._staging=True
        try:
            super().save()
            info=PngImagePlugin.PngInfo()
            info.add_text(adaptive_refresh.PNG_KEY,json.dumps(self._metadata,allow_nan=False))
            with Image.open(target+'.stage') as image:
                image.save(target+'.adaptive.tmp',format='PNG',pnginfo=info,optimize=True)
            os.replace(target+'.adaptive.tmp',target)
        finally:
            self._staging=False
            for suffix in ('.stage','.stage.tmp','.adaptive.tmp'):
                Path(target+suffix).unlink(missing_ok=True)
