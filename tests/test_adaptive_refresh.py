import copy
from datetime import datetime, timedelta
import io
import json
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo
from PIL import Image, PngImagePlugin

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import adaptive_refresh as adaptive

ZONE=ZoneInfo('America/Edmonton')


class AdaptiveRefresh(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,9,16,10,0,tzinfo=ZONE)
        self.config=dict(active_program='simple-weather',refresh_mode='adaptive',
                         timezone='America/Edmonton',device_refresh_seconds=3600,
                         server_refresh_seconds=1800)
        self.data=self.forecast(self.now)

    def forecast(self, now):
        return dict(program='simple-weather',generated_at=now.timestamp(),temperature_c=20,
                    condition='clear',wind_kmh=10,quiet_until=None,
                    hours=[dict(at=(now+timedelta(hours=i)).timestamp(),temperature_c=20,
                                condition='clear',rain=0,wind_kmh=10) for i in range(1,25)])

    def decide(self,data=None,now=None):
        return adaptive.decide(self.data if data is None else data,self.config,now or self.now)

    def test_stable_two_hours_and_small_changes(self):
        self.data['hours'][0]['temperature_c']=22
        self.assertEqual(self.decide()[0],7200)

    def test_accumulated_three_degree_change_from_displayed_reading(self):
        self.data['hours'][0]['temperature_c']=23
        self.assertEqual(self.decide(),(1800,'Temperature change'))

    def test_rain_lead_and_imminent_short_refresh(self):
        self.data['hours'][0]['rain']=70
        self.assertEqual(self.decide()[0],1800)
        self.data['hours'][0]['at']=(self.now+timedelta(minutes=20)).timestamp()
        self.assertEqual(self.decide()[0],900)

    def test_rain_stopping_snow_and_wind(self):
        self.data['condition']='rain'
        self.assertEqual(self.decide()[1],'Conditions change')
        self.data=self.forecast(self.now)
        self.data['hours'][0]['condition']='snow'
        self.assertLess(self.decide()[0],3600)
        self.data=self.forecast(self.now)
        self.data['hours'][0]['wind_kmh']=35
        self.assertEqual(self.decide()[1],'Wind change')

    def test_fixed_and_other_programs(self):
        for change in [dict(refresh_mode='fixed'),dict(active_program='weather-cal')]:
            self.assertEqual(adaptive.decide(None,{**self.config,**change},self.now),(3600,'Fixed interval'))

    def test_corrupt_missing_stale_and_future_data_retry(self):
        for change in [dict(generated_at=self.now.timestamp()-4000),dict(generated_at=self.now.timestamp()+200),
                       dict(hours=[]),dict(temperature_c=float('nan')),dict(condition=None)]:
            with self.subTest(change=change):
                self.assertEqual(self.decide({**self.data,**change})[0],900)
        self.assertEqual(adaptive.from_png(b'not png',self.config,self.now)[0],900)
        self.data['hours'][0]['rain']=None
        self.assertEqual(self.decide()[0],900)

    def test_delayed_fetch_does_not_extend_old_image_two_hours(self):
        self.assertEqual(self.decide(now=self.now+timedelta(minutes=30))[0],5400)

    def test_quiet_boundary_under_minimum(self):
        now=self.now.replace(hour=23,minute=55)
        self.assertEqual(self.decide(self.forecast(now),now)[0],300)

    def test_quiet_requires_matching_morning_image(self):
        now=self.now.replace(hour=0)
        data=self.forecast(now)
        self.assertEqual(self.decide(data,now)[0],900)
        data.update(quiet_until=now.replace(hour=6).timestamp(),morning_hours=4)
        self.assertEqual(self.decide(data,now)[0],21600)
        data['morning_hours']=3
        self.assertEqual(self.decide(data,now)[0],900)

    def test_morning_wake_and_wrong_quiet_end(self):
        now=self.now.replace(hour=5,minute=55)
        data=self.forecast(now)
        data.update(quiet_until=now.replace(hour=6,minute=0).timestamp(),morning_hours=4)
        self.assertEqual(self.decide(data,now)[0],300)
        self.assertEqual(adaptive.decide(None,self.config,now)[0],300)
        self.assertEqual(self.decide(data,now.replace(hour=6,minute=0))[0],900)
        self.config['adaptive_refresh']={'quiet_end':'07:00'}
        self.assertEqual(self.decide(data,now)[0],900)

    def test_cross_midnight_and_dst(self):
        self.config['adaptive_refresh']={'quiet_start':'23:00','quiet_end':'06:00'}
        now=self.now.replace(hour=23,minute=30)
        window,_=adaptive.quiet_window(now,self.config)
        self.assertEqual((window[1].day,window[1].hour),(17,6))
        self.config['adaptive_refresh']={}
        for day,hours in [(datetime(2026,3,8,tzinfo=ZONE),5),(datetime(2026,11,1,tzinfo=ZoneInfo('America/New_York')),7)]:
            data=self.forecast(day)
            data.update(quiet_until=day.replace(hour=6).timestamp(),morning_hours=4)
            self.assertEqual(self.decide(data,day)[0],hours*3600)

    def test_exact_png_metadata_survives_caching(self):
        image=Image.new('L',(600,800),255)
        info=PngImagePlugin.PngInfo();info.add_text(adaptive.PNG_KEY,json.dumps(self.data))
        out=io.BytesIO();image.save(out,format='PNG',pnginfo=info)
        self.assertEqual(adaptive.from_png(out.getvalue(),self.config,self.now)[0],7200)
        other=io.BytesIO();image.save(other,format='PNG')
        self.assertEqual(adaptive.from_png(other.getvalue(),self.config,self.now)[0],900)

    def test_settings_bounds(self):
        for values in [{'min_seconds':0},{'max_seconds':900,'min_seconds':1800},
                       {'quiet_start':'24:00'},{'quiet_start':'06:00'},
                       {'temperature_delta_c':True},{'wind_delta_kmh':0},{'unknown':1}]:
            with self.subTest(values=values),self.assertRaises(ValueError):
                adaptive.validate({'adaptive_refresh':values})
        self.assertEqual(adaptive.validate({})['max_seconds'],7200)
