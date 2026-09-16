"""Concept B: sharp portrait weather artwork rendered by the existing pipeline."""
from datetime import datetime
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


def artwork(current, hourly, now=None):
    now = now or datetime.now()
    pieces = []
    def text(x,y,value,size,anchor='middle',weight=700):
        pieces.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{escape(str(value))}</text>')
    def icon(x,y,size,path):
        art, label = symbol(path)
        pieces.append(f'<g transform="translate({x},{y}) scale({size/100})">{art}</g>')
        return label
    text(145,112,now.day,112)
    text(394, 60,now.strftime('%A').upper(),30)
    text(394,102,now.strftime('%B').upper(),26)
    label=icon(188,136,224,current.get('icon'))
    temp=current['temperature']
    value=f"{temp['value']}{temp['unit']}"
    text(300,477,value, min(132, 520/max(1,len(value))/.64))
    text(300,521,label,30 if len(label)<14 else 25)
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
        text(x,709,str(row['temperature']['value'])+'°',47)
        pop=row.get('rain_probability')
        text(x,735,'—' if pop is None else f'{round(pop)}% rain',18)
        wind=row.get('wind') or {}
        bearing=wind.get('direction_degrees')
        direction='' if bearing is None else ['N','NE','E','SE','S','SW','W','NW'][int((bearing+22.5)//45)%8]
        speed=wind.get('value')
        text(x,759,'—' if speed is None else f'{direction} {round(speed)}',18)
    # The current adapter supplies the observation source and local timestamp.
    source=current.get('weather_text') or 'EDMONTON'
    text(18,790,source,12,'start')
    unit=(rows[0].get('wind') or {}).get('unit','kmh') if rows else 'kmh'
    text(582,790,'WIND '+('km/h' if unit=='kmh' else unit),12,'end')
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 800" role="img" aria-label="Simple Weather"><rect width="600" height="800" fill="white"/><g fill="black" font-family="DejaVu Sans, sans-serif">'+''.join(pieces)+'</g></svg>'


# Kept separate from artwork() so fixtures can exercise it without Chromium.
from views.page import Page


class SimpleWeatherPage(Page):
    requires = ('current_conditions','hourly_forecasts')

    def __init__(self,*geometry):
        super().__init__('simple-weather',*geometry)

    def template(self,**kwargs):
        svg=artwork(kwargs['current_conditions'],kwargs['hourly_forecasts'])
        self.airium=('<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;width:100%;height:100%;background:white;overflow:hidden}svg{display:block;width:100%;height:100%}</style></head><body>'+svg+'</body></html>').encode('utf-8')
