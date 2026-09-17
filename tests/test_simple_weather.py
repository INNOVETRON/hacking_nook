import io
import runpy
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
import panel_server
from test_image_recovery import png
import settings
import threading
from types import SimpleNamespace


class SimpleWeather(unittest.TestCase):
    def test_artwork_handles_winter_missing_hours_and_special_text(self):
        module = types.ModuleType('views.page')
        module.Page = object
        with patch.dict(sys.modules, {'views.page': module}):
            artwork = runpy.run_path(str(ROOT / 'upstream/simple_weather.py'))['artwork']
        current = dict(icon='icon/cloudy-snowy.png', temperature=dict(value=-25, unit='°C'),
                       weather_text='ECCC & Blatchford <observed>')
        row = dict(dt=datetime(2026,12,31,23), icon='icon/night/clear.png',
                   temperature=dict(value=-27), wind={}, rain_probability=None)
        svg = artwork(current, [row], datetime(2026,12,31))
        root = ET.fromstring(svg)
        text = ''.join(root.itertext())
        self.assertIn('-25°C', text)
        self.assertIn('SNOW', text)
        self.assertIn('11 PM', text)
        self.assertIn('ECCC & Blatchford <observed>', text)
        self.assertNotIn('None', text)
        self.assertEqual(root.attrib['viewBox'], '0 0 600 800')

    def test_overnight_shows_morning_temperature_and_sunrise(self):
        module = types.ModuleType('views.page')
        module.Page = object
        with patch.dict(sys.modules, {'views.page': module}):
            artwork = runpy.run_path(str(ROOT / 'upstream/simple_weather.py'))['artwork']
        now=datetime(2026,9,17)
        current={'icon':'clear','temperature':{'value':20,'unit':'°C'}}
        row={'dt':now.replace(hour=6),'icon':'clear','temperature':{'value':8},'sunrise':'2026-09-17T07:10','rain_probability':0}
        text=''.join(ET.fromstring(artwork(current,[row],now,now.replace(hour=6))).itertext())
        self.assertIn('MORNING BRIEFING',text)
        self.assertIn('SUNRISE 7:10 AM',text)
        self.assertIn('8°',text)
        self.assertNotIn('20°C',text)
        self.assertIn('NEXT UPDATE 6:00 AM',text)

    def test_selection_bypasses_advisories_and_retains_image_on_failure(self):
        body = png()
        config = {'renderer_url':'http://renderer','active_program':'simple-weather',
                  'timezone':'America/Edmonton'}
        with tempfile.TemporaryDirectory() as cache:
            with patch.object(panel_server.urllib.request,'urlopen',return_value=io.BytesIO(body)):
                renderer=panel_server.RenderedPages(config, cache)
            simple_cache=renderer.cache_path
            self.assertEqual(renderer.page,'simple-weather')
            with patch.object(renderer.weather,'fetch',side_effect=AssertionError('must not fetch advisories')):
                self.assertEqual(renderer._target()[0],'http://renderer/simple-weather.png')
            renderer.config=dict(config,active_program='weather-cal')
            with patch.object(renderer,'_target',return_value=('http://renderer/today.png','today',None)), patch.object(panel_server.urllib.request,'urlopen',side_effect=OSError('offline')):
                renderer.refresh()
            self.assertEqual(renderer.current(),body)
            self.assertEqual(renderer.page,'simple-weather')
            with patch.object(renderer,'_target',return_value=('http://renderer/today.png','today',None)), patch.object(panel_server.urllib.request,'urlopen',return_value=io.BytesIO(body)):
                renderer.refresh()
            self.assertNotEqual(renderer.cache_path,simple_cache)
            self.assertTrue(simple_cache.exists())


class ProgramSelection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        renderer = SimpleNamespace(config={'timezone':'America/Edmonton'}, settings_changed=threading.Event())
        self.store = settings.Settings(renderer, Path(self.tmp.name) / 'config.json')
        self.data = dict(active_program='weather-cal', device_refresh_seconds=3600,
                         enabled_pages=['today','tomorrow'],
                         page_schedule={'09:30':'today','21:00':'tomorrow'}, advisories=True)

    def test_switch_preserves_existing_schedule(self):
        original=self.store.save(self.data)
        self.store.save(dict(self.data,active_program='simple-weather'))
        self.assertEqual(self.store.snapshot()['active_program'],'simple-weather')
        self.assertEqual(self.store.snapshot()['page_schedule'],original['page_schedule'])
        self.store.save(self.data)
        self.assertEqual(self.store.snapshot()['active_program'],'weather-cal')
