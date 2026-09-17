import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from display_activity import DisplayActivity
import program_schedule
import display_preview


class Features(unittest.TestCase):
    def test_battery_learning_and_charging_reset(self):
        with tempfile.TemporaryDirectory() as folder:
            activity=DisplayActivity(Path(folder)/'events.json')
            for at,level,charge in [(1000000,90,'0'),(1086400,85,'0')]:
                activity.record(3600,'Fixed',at,{'X-Nook-Battery':str(level),'X-Nook-Charging':charge,'X-Nook-Failures':'2'})
            state=activity.snapshot('UTC',1086400)
            self.assertEqual(state['battery']['days_remaining'],17)
            self.assertEqual(state['device_failures'],2)
            activity.record(3600,'Fixed',1086500,{'X-Nook-Battery':'85','X-Nook-Charging':'1'})
            self.assertIsNone(activity.snapshot('UTC',1086500)['battery']['days_remaining'])
            self.assertTrue(DisplayActivity(activity.path).snapshot('UTC')['battery']['charging'])

    def test_offline_time_does_not_earn_savings(self):
        with tempfile.TemporaryDirectory() as folder:
            activity=DisplayActivity(Path(folder)/'events.json')
            now=datetime(2026,9,16,6,tzinfo=ZoneInfo('UTC')).timestamp()
            activity.record(7200,'Stable',now)
            state=activity.snapshot('UTC',now+10*3600)
            self.assertEqual(state['days'][0]['hourly_baseline'],2)
            self.assertEqual(state['days'][0]['fetches_avoided'],1)
            self.assertEqual(state['reliability'],'Overdue')

    def test_program_boundaries(self):
        config={'timezone':'America/Edmonton','program_schedule_enabled':True,'program_schedule':{'06:00':'simple-weather','10:00':'clock-calendar','22:00':'weather-cal'}}
        program_schedule.validate(config)
        now=datetime(2026,9,16,9,50,tzinfo=ZoneInfo(config['timezone']))
        self.assertEqual(program_schedule.active(config,now),'simple-weather')
        self.assertEqual(program_schedule.next_boundary(config,now)-now.timestamp(),600)
        self.assertEqual(program_schedule.active(config,now.replace(hour=1)),'weather-cal')
        self.assertEqual(program_schedule.active(config,now.replace(hour=10)),'clock-calendar')
        with self.assertRaises(ValueError):
            program_schedule.validate(dict(config,program_schedule={'25:00':'clock-calendar'}))

    def test_clock_has_generation_metadata(self):
        now=datetime(2026,9,16,10,tzinfo=ZoneInfo('UTC'))
        png=display_preview.clock_image(now)
        self.assertEqual(Image.open(io.BytesIO(png)).size,(600,800))
        self.assertEqual(display_preview.metadata(png)['generated_at'],now.timestamp())
