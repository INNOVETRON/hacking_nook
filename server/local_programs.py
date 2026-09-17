"""Portrait programs rendered on the server, with delivery-driven photo rotation."""
from datetime import datetime, timedelta
import io
import json
import logging
import math
import os
from pathlib import Path
import threading
from urllib.parse import urlencode
from urllib.request import urlopen
from PIL import Image, ImageDraw, ImageFont, ImageOps, PngImagePlugin
import adaptive_refresh
import display_preview
import program_options

LOCAL = {'clock-calendar','photo-frame','countdown','daylight','reminder'}
LOG = logging.getLogger(__name__)


def font(size, bold=False):
    return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans'+('-Bold' if bold else '')+'.ttf', size)


def label(draw, y, value, size=26, fill=0, width=540, bold=False):
    value=str(value)
    while size > 12 and draw.textlength(value,font=font(size,bold)) > width:
        size-=1
    draw.text((300,y),value,font=font(size,bold),fill=fill,anchor='mt')


def lines(draw,y,value,size=34,fill=0,width=520,max_lines=4):
    words=str(value).split()
    rows=[]
    for word in words:
        if rows and draw.textlength(rows[-1]+' '+word,font=font(size,True)) <= width:
            rows[-1]+=' '+word
        else:
            rows.append(word)
    # Fit long user text by reducing type before falling back to ellipsis.
    if len(rows)>max_lines and size>18:
        return lines(draw,y,value,size-2,fill,width,max_lines)
    for i,row in enumerate(rows[:max_lines]):
        label(draw,y+i*(size+10),row,size,fill,width,True)
    return y+min(len(rows),max_lines)*(size+10)


def emblem(draw,kind,center=(300,220),size=90,fill=0):
    x,y=center;s=size/2
    if kind=='heart':
        draw.ellipse((x-s,y-s,x,y),fill=fill);draw.ellipse((x,y-s,x+s,y),fill=fill)
        draw.polygon([(x-s,y-s/2),(x+s,y-s/2),(x,y+s)],fill=fill)
    elif kind=='plane':
        draw.polygon([(x,y-s),(x+s*.2,y-s*.1),(x+s,y+s*.3),(x+s,y+s*.55),(x+s*.2,y+s*.2),(x+s*.2,y+s*.7),(x+s*.4,y+s),(x-s*.4,y+s),(x-s*.2,y+s*.7),(x-s*.2,y+s*.2),(x-s,y+s*.55),(x-s,y+s*.3),(x-s*.2,y-s*.1)],fill=fill)
    elif kind=='gift':
        draw.rectangle((x-s,y-s*.3,x+s,y+s),outline=fill,width=5)
        draw.line((x,y-s*.3,x,y+s),fill=fill,width=7)
        draw.ellipse((x-s*.65,y-s,x,y-s*.25),outline=fill,width=5)
        draw.ellipse((x,y-s,x+s*.65,y-s*.25),outline=fill,width=5)
    elif kind=='calendar':
        draw.rounded_rectangle((x-s,y-s,x+s,y+s),radius=10,outline=fill,width=5)
        draw.line((x-s,y-s*.35,x+s,y-s*.35),fill=fill,width=5)
        draw.line((x-s*.45,y-s*1.15,x-s*.45,y-s*.7),fill=fill,width=5)
        draw.line((x+s*.45,y-s*1.15,x+s*.45,y-s*.7),fill=fill,width=5)
    else:
        pts=[(x+math.sin(i*math.pi/5)*(s if i%2==0 else s*.42),y-math.cos(i*math.pi/5)*(s if i%2==0 else s*.42)) for i in range(10)]
        draw.polygon(pts,fill=fill)


def png(image, metadata):
    info=PngImagePlugin.PngInfo()
    info.add_text(adaptive_refresh.PNG_KEY,json.dumps(metadata,allow_nan=False))
    stream=io.BytesIO();image.save(stream,format='PNG',pnginfo=info)
    return stream.getvalue()


def frame_image(library, ident, options, caption=''):
    image=Image.new('L',(600,800),255)
    border=options['border'];bottom=48 if options['caption'] else 0
    bounds=(600-2*border,800-2*border-bottom)
    picture=ImageOps.grayscale(library.image(ident))
    picture=ImageOps.autocontrast(picture,cutoff=1)
    picture=ImageOps.fit(picture,bounds,method=Image.Resampling.LANCZOS) if options['fit']=='cover' else ImageOps.contain(picture,bounds,method=Image.Resampling.LANCZOS)
    if options['dither']:
        picture=picture.convert('1').convert('L')
    image.paste(picture,((600-picture.width)//2,border+(bounds[1]-picture.height)//2))
    if options['caption']:
        label(ImageDraw.Draw(image),754,caption,18)
    return image


class ProgramRenderer:
    def __init__(self, library, cache):
        self.library=library
        self.cache=Path(cache)
        self.lock=threading.RLock()
        self.rotation=self._read('rotation.json',{})
        self.sun=self._read('daylight.json',{})
        self.sun_attempt=0
        self.reminders=self._read('reminder-deliveries.json',{})
        self.temperature=self._read('temperature.json',{})
        self.temperature_attempt=0

    def _read(self,name,default):
        try:return json.loads((self.cache/name).read_text())
        except (OSError,ValueError):return default

    def _write(self,name,data):
        self.cache.mkdir(parents=True,exist_ok=True)
        path=self.cache/name;temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data));os.replace(temporary,path)

    def delivered(self,body,now):
        meta=display_preview.metadata(body)
        with self.lock:
            if meta.get('reminder_id') and meta.get('reminder_at') is not None:
                self.reminders[meta['reminder_id']]=meta['reminder_at']
                try:self._write('reminder-deliveries.json',self.reminders)
                except OSError:LOG.exception('Could not persist reminder delivery')
            previous=self.rotation
            program=meta.get('program','weather-cal')
            state={'program':program,'id':previous.get('id'),'at':previous.get('at',now)}
            if program=='photo-frame':
                ident=meta.get('image_id')
                state['id']=ident
                if previous.get('program')!=program or previous.get('id')!=ident:
                    state['at']=now
            self.rotation=state
            try:self._write('rotation.json',state)
            except OSError:LOG.exception('Could not save photo rotation')

    def pending_reminder(self,config,now):
        reminder=program_options.active_reminder(config,now)
        with self.lock:
            return reminder if reminder and self.reminders.get(reminder['id'])!=reminder['at'] else None

    def overlay_reminder(self,body,reminder):
        image=Image.open(io.BytesIO(body)).convert('L')
        # Keep the current program recognizable behind a crisp paper popup.
        image=Image.blend(image,Image.new('L',image.size,255),.55)
        draw=ImageDraw.Draw(image)
        draw.rounded_rectangle((26,174,582,666),radius=18,fill=80)
        draw.rounded_rectangle((18,164,574,654),radius=18,fill=255,outline=0,width=4)
        draw.rounded_rectangle((20,166,572,244),radius=16,fill=0)
        draw.rectangle((20,205,572,244),fill=0)
        label(draw,188,'REMINDER',27,255,bold=True)
        emblem(draw,reminder['icon'],(300,296),54)
        bottom=lines(draw,343,reminder['title'],32,max_lines=2)
        lines(draw,bottom+12,reminder['message'],23,max_lines=4)
        label(draw,615,'PRESS n TO DISMISS',17,bold=True)
        meta=display_preview.metadata(body)
        meta.update(program='reminder',reminder_id=reminder['id'],reminder_at=reminder['at'],next_update=reminder['at']+reminder['minutes']*60)
        return png(image,meta)

    def refresh_temperature(self,config):
        import time
        if time.time()-self.temperature_attempt<300:return
        self.temperature_attempt=time.time()
        base=(config.get('renderer_url') or config.get('mirror_base') or '').rstrip('/')
        if not base:return
        try:
            with urlopen(base+'/simple-weather.png',timeout=10) as response:
                data=display_preview.metadata(response.read())
            if data.get('temperature_c') is not None:
                with self.lock:
                    self.temperature={'value':data['temperature_c'],'at':data['generated_at']}
                    self._write('temperature.json',self.temperature)
        except (OSError,ValueError,KeyError):LOG.warning('Temperature unavailable; retaining last observation')

    def refresh_daylight(self,config,now):
        if now.timestamp()-self.sun_attempt < 300:return
        location=[config.get('latitude'),config.get('longitude'),config.get('timezone')]
        if self.sun.get('location')==location and now.timestamp()-self.sun.get('fetched_at',0)<14400:return
        self.sun_attempt=now.timestamp()
        params=dict(latitude=location[0],longitude=location[1],timezone=location[2],
                    daily='sunrise,sunset,daylight_duration',past_days=1,forecast_days=2)
        try:
            with urlopen('https://api.open-meteo.com/v1/forecast?'+urlencode(params),timeout=12) as response:
                daily=json.load(response)['daily']
            if now.date().isoformat() not in daily['time']:raise ValueError('No daylight for today')
            with self.lock:
                self.sun={'location':location,'fetched_at':now.timestamp(),'daily':daily}
                self._write('daylight.json',self.sun)
        except (OSError,ValueError,KeyError):LOG.exception('Daylight update failed; retaining dated data')

    def render(self,program,config,now,preview_image=None):
        opts=program_options.options(config)
        stamp=now.timestamp()
        meta={'program':program,'generated_at':stamp}
        image=Image.new('L',(600,800),255);draw=ImageDraw.Draw(image)
        if program=='clock-calendar':
            return display_preview.clock_image(now,opts[program])
        if program=='photo-frame':
            items=self.library.list();o=opts[program]
            with self.lock:state=dict(self.rotation)
            ids=[item['id'] for item in items]
            ident=preview_image or state.get('id')
            if ident not in ids:ident=ids[0] if ids else None
            same=state.get('program')==program and ident==state.get('id')
            if ids and not preview_image and same and stamp-state.get('at',stamp)>=o['minutes']*60:
                ident=ids[(ids.index(ident)+1)%len(ids)];same=False
            if ident:
                item=next(item for item in items if item['id']==ident)
                image=frame_image(self.library,ident,o,item['name'])
            else:
                emblem(draw,'heart',size=120)
                label(draw,370,'YOUR LITTLE GALLERY',30,bold=True)
                label(draw,440,'Add pictures in your gallery',22)
            deadline=state.get('at',stamp)+o['minutes']*60 if same else stamp+o['minutes']*60
            # One-photo galleries still use a future deadline after each interval.
            if deadline<=stamp:deadline=stamp+o['minutes']*60
            meta.update(image_id=ident,next_update=deadline)
        elif program=='countdown':
            o=opts[program]
            draw.rectangle((0,0,600,270),fill=0)
            label(draw,22,o['title'],29,255,bold=True)
            if o['date']:
                target=datetime.strptime(o['date'],'%Y-%m-%d').date();days=(target-now.date()).days
                label(draw,67,abs(days),118,255,bold=True)
                label(draw,198,'DAYS TO GO' if days>0 else 'DAYS SINCE' if days<0 else o['complete'],25,255,bold=True)
                label(draw,239,target.strftime('%B %-d, %Y'),18,255)
            else:label(draw,113,'Choose your date',38,255)
            if o['image']:
                try:
                    picture=ImageOps.fit(ImageOps.grayscale(self.library.image(o['image'])),(600,370),method=Image.Resampling.LANCZOS)
                    image.paste(picture,(0,270))
                except OSError:emblem(draw,o['icon'],(300,450),140)
            else:emblem(draw,o['icon'],(300,450),140)
            label(draw,654,o['subtitle'],22)
            draw.line((30,694,570,694),fill=0,width=2)
            with self.lock:temperature=dict(self.temperature)
            value=temperature.get('value');at=temperature.get('at',0)
            if value is not None and 0<=stamp-at<10800:
                imperial=config.get('units')=='imperial'
                label(draw,711,str(round(value*9/5+32 if imperial else value))+'°'+('F' if imperial else 'C'),43,bold=True)
                label(draw,769,'WEATHER · UPDATED '+datetime.fromtimestamp(at,now.tzinfo).strftime('%-I:%M %p'),13)
            else:label(draw,733,'Weather unavailable',23)
            midnight=(now+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
            meta['next_update']=min(stamp+o['refresh_minutes']*60,midnight)
        elif program=='reminder':
            reminder=program_options.active_reminder(config,now)
            if not reminder:raise ValueError('Reminder is no longer active')
            draw.rectangle((0,0,600,136),fill=0)
            label(draw,36,'A LITTLE REMINDER',29,255,bold=True)
            label(draw,87,now.strftime('%A · %B %-d'),21,255)
            emblem(draw,reminder['icon'],(300,230),108)
            bottom=lines(draw,330,reminder['title'],45,max_lines=3)
            lines(draw,bottom+30,reminder['message'],25,max_lines=5)
            end=datetime.fromtimestamp(reminder['at']+reminder['minutes']*60,now.tzinfo)
            draw.line((35,735,565,735),fill=0,width=3)
            label(draw,759,'BACK TO YOUR DISPLAY AT '+end.strftime('%-I:%M %p'),18)
            meta.update(reminder_id=reminder['id'],next_update=end.timestamp())
        elif program=='daylight':
            o=opts[program]
            draw.rectangle((0,0,600,145),fill=0)
            label(draw,35,o['title'],32,255,bold=True)
            label(draw,95,config.get('location_name','')+' · '+now.strftime('%B %-d'),22,255)
            with self.lock:sun=dict(self.sun)
            daily=sun.get('daily',{});dates=daily.get('time',[])
            if now.date().isoformat() not in dates or sun.get('location') != [config.get('latitude'),config.get('longitude'),config.get('timezone')]:
                label(draw,340,'Waiting for daylight data',29)
                label(draw,400,'Your server will try again shortly',21)
                meta['next_update']=stamp+900
            else:
                i=dates.index(now.date().isoformat());duration=daily['daylight_duration'][i]
                rise=daily['sunrise'][i];setting=daily['sunset'][i]
                rise=datetime.fromisoformat(rise).replace(tzinfo=now.tzinfo) if rise else None
                setting=datetime.fromisoformat(setting).replace(tzinfo=now.tzinfo) if setting else None
                draw.arc((65,190,535,660),180,360,fill=0,width=5)
                draw.line((50,425,550,425),fill=0,width=3)
                if rise and setting and setting>rise:
                    progress=max(0,min(1,(stamp-rise.timestamp())/(setting.timestamp()-rise.timestamp())))
                    angle=math.pi*(1-progress);x=300+235*math.cos(angle);y=425-235*math.sin(angle)
                    draw.ellipse((x-18,y-18,x+18,y+18),fill=0)
                label(draw,285,f'{int(duration)//3600}h {int(duration)%3600//60:02d}m',54,bold=True)
                label(draw,355,'OF DAYLIGHT',21)
                fmt='%H:%M' if o['format']=='24' else '%-I:%M %p'
                label(draw,469,'SUNRISE  '+(rise.strftime(fmt) if rise else '—'),29,bold=True)
                label(draw,523,'SUNSET   '+(setting.strftime(fmt) if setting else '—'),29,bold=True)
                previous=daily['daylight_duration'][i-1] if i else None
                if previous is not None:
                    delta=round(duration-previous);label(draw,602,f'{abs(delta)//60}m {abs(delta)%60:02d}s '+('more' if delta>=0 else 'less')+' than yesterday',22)
                remaining=max(0,min(duration,setting.timestamp()-stamp)) if setting else 0
                label(draw,665,(f'{int(remaining)//3600}h {int(remaining)%3600//60}m of daylight left' if remaining else 'The day is resting'),24)
                label(draw,764,'OPEN-METEO · '+datetime.fromtimestamp(sun['fetched_at'],now.tzinfo).strftime('%b %-d %-I:%M %p'),13)
                meta['next_update']=min([stamp+o['refresh_minutes']*60]+[t.timestamp() for t in (rise,setting) if t and t.timestamp()>stamp])
        return png(image,meta)
