import sys
from pathlib import Path
import tempfile
import threading
import unittest
from datetime import datetime
from types import SimpleNamespace
import json
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
import settings
import pagechoice

class ControlPlane(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'config.json'
        self.renderer = SimpleNamespace(config={'timezone':'America/Edmonton','renderer_url':'http://localhost:8082'}, settings_changed=threading.Event())
        self.store = settings.Settings(self.renderer, self.path)
        self.data = dict(active_program='weather-cal', device_refresh_seconds=900, enabled_pages=['today','tomorrow'],page_schedule={'08:00':'today','21:00':'tomorrow'},advisories=True)

    def test_persist_and_publish(self):
        self.store.save(self.data)
        self.assertEqual(json.loads(self.path.read_text())['device_refresh_seconds'],900)
        self.assertEqual(self.renderer.config['renderer_url'],'http://localhost:8082')
        self.assertTrue(self.renderer.settings_changed.is_set())

    def test_invalid_never_published(self):
        for change in ({'device_refresh_seconds':True},{'device_refresh_seconds':0},{'enabled_pages':[]},{'page_schedule':{'25:00':'today'}},{'active_program':'clock'},{'page_schedule':{'08:00':'hourly'}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.store.save(dict(self.data,**change))
        self.assertFalse(self.path.exists())
        self.assertNotIn('device_refresh_seconds',self.renderer.config)

    def test_overnight_and_disabled_advisory(self):
        self.assertEqual(pagechoice.scheduled_page(self.data,datetime(2026,9,13,2)), 'tomorrow')
        weather=SimpleNamespace(data=True)
        self.assertEqual(pagechoice.choose(self.data,weather,datetime(2026,9,13,10)), ('today',None))

    def test_default_schedule_enabled_pages_match(self):
        s=self.store.snapshot()
        self.assertEqual(set(s['enabled_pages']),set(s['page_schedule'].values()))
