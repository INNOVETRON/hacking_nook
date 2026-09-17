"""Integration check: run with the weather-cal venv and --server PATH."""
import io,json,tempfile
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
from PIL import Image
import argparse, sys
parser=argparse.ArgumentParser()
parser.add_argument("--server",required=True)
args=parser.parse_args()
sys.path.insert(0,args.server)
import simple_weather
import adaptive_refresh

settings=dict(refresh_mode='adaptive',active_program='simple-weather',timezone='America/Edmonton')
now=datetime(2026,9,16,0,0,tzinfo=ZoneInfo(settings['timezone']))
class Clock(datetime):
    @classmethod
    def now(cls,tz=None):return now
rows=[dict(dt=now+timedelta(hours=i),icon='icon/day/clear.png',temperature=dict(unit='°C',value=20),rain_probability=0,wind=dict(unit='kmh',value=10,direction_degrees=180)) for i in range(24)]
current=dict(icon='icon/night/clear.png',temperature=dict(unit='°C',value=20),wind=dict(unit='kmh',value=10),weather_text='ECCC · 12:00 AM')
class Renderer:
    def render(self,*args):return Image.new('L',(600,800),255)
with tempfile.TemporaryDirectory() as directory:
    page=simple_weather.SimpleWeatherPage(600,800)
    page.png_dir=page.html_dir=directory
    page.renderer=Renderer()
    with patch.object(simple_weather,'datetime',Clock),patch.object(simple_weather,'urlopen',return_value=io.BytesIO(json.dumps(settings).encode())):
        page.template(current_conditions=current,simple_hourly_forecasts=rows)
    assert b'MORNING FORECAST' in page.airium and b'NEXT UPDATE 6:00 AM' in page.airium
    assert all(label in page.airium for label in [b'6 AM',b'7 AM',b'8 AM',b'9 AM'])
    page.save()
    output=Path(page.png_path).read_bytes()
    assert adaptive_refresh.from_png(output,settings,now)[0]==21600
    assert not list(Path(directory).glob('*.stage*'))
    page.renderer.render=lambda *args: (_ for _ in ()).throw(RuntimeError('render failed'))
    try:
        page.save()
        raise AssertionError('expected render failure')
    except RuntimeError:
        pass
    assert Path(page.png_path).read_bytes()==output
    print('PASS: morning artwork, atomic PNG metadata, six-hour wake header')

