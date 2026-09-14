"""Exercise scheduling without starting Chromium or requiring epd-server locally."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('generation_adapter', Path(__file__).resolve().parents[1] / 'upstream/retrying_server.py')
adapter = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'epd_server': types.SimpleNamespace(DisplayServer=object)}):
    spec.loader.exec_module(adapter)


class GenerationSchedule(unittest.TestCase):
    def setUp(self):
        self.server = adapter.DisplayServer()
        self.server.regen_lead_seconds = 120

    def test_half_hour_slots_and_missed_slots(self):
        self.assertEqual(self.server._next_generation(0, 1800), 1680)
        self.assertEqual(self.server._next_generation(1680, 1800), 3480)
        self.assertEqual(self.server._next_generation(4000, 1800), 5280)
        self.assertEqual(self.server._next_generation(4000, 3600), 7080)

    def test_control_outage_and_invalid_values_keep_previous(self):
        with patch.object(adapter, 'urlopen', side_effect=OSError):
            self.assertEqual(self.server._generation_interval(3600), 3600)
        for value in (True, 0, 899, 86401, '1800', None):
            with self.subTest(value=value), patch.object(adapter, 'urlopen', return_value=io.BytesIO(json.dumps({'server_refresh_seconds': value}).encode())):
                self.assertEqual(self.server._generation_interval(3600), 3600)
        with patch.object(adapter, 'urlopen', return_value=io.BytesIO(b'{"server_refresh_seconds":1800}')):
            self.assertEqual(self.server._generation_interval(3600), 1800)

    def test_hot_reload_and_serial_render(self):
        # At 00:16 an hourly schedule changes to half-hourly. Only the new
        # 00:28 deadline should render, and shutdown must stop the loop.
        clock = [960]
        rendered = []
        class Stop:
            done = False
            def is_set(self): return self.done
            def wait(self, delay):
                clock[0] += delay
                return self.done
        stop = Stop()
        self.server.shutdown_event = stop
        def render(**kwargs):
            rendered.append((clock[0], kwargs))
            clock[0] += 200
            stop.done = True
        self.server.regenerate = render
        with patch.object(self.server, '_generation_interval', side_effect=lambda old: 3600 if clock[0] == 960 and old == 1800 else 1800), patch.object(adapter.time, 'time', side_effect=lambda: clock[0]):
            self.server._loop()
        self.assertEqual(rendered, [(1680, {'force_refresh': True})])
