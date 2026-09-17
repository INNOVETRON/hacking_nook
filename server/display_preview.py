"""Image metadata and an intentionally static clock/calendar banner."""
import calendar
from datetime import datetime
import io
import json
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin
import adaptive_refresh


def metadata(body):
    try:
        with Image.open(io.BytesIO(body)) as image:
            return json.loads(image.info.get(adaptive_refresh.PNG_KEY, '{}'))
    except (OSError, ValueError, TypeError):
        return {}


def clock_image(now, options=None):
    options = options or {"title":"AT A GLANCE","format":"12","week_start":"monday","refresh_minutes":30}
    image = Image.new('L', (600, 800), 255)
    draw = ImageDraw.Draw(image)
    def text(y, value, size, white=False):
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', size)
        draw.text((300, y), value, font=font, anchor='mt', fill=255 if white else 0)
    draw.rectangle((0, 0, 600, 240), fill=0)
    text(28, options['title'], min(24, max(12, 510//max(1,len(options['title'])))), True)
    text(80, now.strftime('%H:%M' if options['format']=='24' else '%-I:%M'), 112, True)
    text(204, 'UPDATED '+now.strftime('%H:%M' if options['format']=='24' else '%-I:%M %p'), 16, True)
    text(278, now.strftime('%A').upper(), 36)
    text(332, now.strftime('%B %Y'), 26)
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 24)
    days=['MO','TU','WE','TH','FR','SA','SU']
    sunday=options['week_start']=='sunday'
    if sunday: days=days[-1:]+days[:-1]
    for col, name in enumerate(days):
        draw.text((60+80*col, 400), name, font=font, anchor='mm', fill=0)
    for row, week in enumerate(calendar.Calendar(6 if sunday else 0).monthdayscalendar(now.year, now.month)):
        for col, day in enumerate(week):
            if not day:
                continue
            x,y=60+80*col,455+48*row
            if day == now.day:
                draw.ellipse((x-22,y-22,x+22,y+22),fill=0)
            draw.text((x,y),str(day),font=font,anchor='mm',fill=255 if day==now.day else 0)
    text(765, 'TIME SHOWN IS THE LAST SERVER UPDATE', 15)
    info = PngImagePlugin.PngInfo()
    info.add_text(adaptive_refresh.PNG_KEY, json.dumps({'program':'clock-calendar','generated_at':now.timestamp(),'next_update':now.timestamp()+options['refresh_minutes']*60}))
    output=io.BytesIO()
    image.save(output,format='PNG',pnginfo=info)
    return output.getvalue()
