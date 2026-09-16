"""Check the patched Today data contract without requiring Chromium."""
import pathlib
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch


class TodayCurrentTests(unittest.TestCase):
    def test_today_uses_current_not_daily_temperature(self):
        repo = pathlib.Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            archive = subprocess.check_output([
                'git', '-C', str(repo / 'external/inkplate10-weather-cal'),
                'archive', 'HEAD'])
            subprocess.run(['tar', 'xf', '-', '-C', directory], input=archive, check=True)
            for overlay in sorted((repo / 'upstream/patches').glob('*.patch')):
                subprocess.run(['git', 'apply', str(overlay)], cwd=directory,
                               check=True, capture_output=True)
            source = pathlib.Path(directory, 'server/views/today.py').read_text()

        class SimplifiedPage:
            def __init__(self, *args):
                pass

            def template(self, **kwargs):
                self.received = kwargs

        simplified = types.ModuleType('views.simplified')
        simplified.SimplifiedPage = SimplifiedPage
        chart = types.ModuleType('smart_chart')
        chart.choose_chart = chart.draw_chart = lambda *args, **kwargs: None
        namespace = {'__package__': 'views'}
        with patch.dict('sys.modules', {'views.simplified': simplified, 'smart_chart': chart}):
            exec(compile(source, 'today.py', 'exec'), namespace)
        page = namespace['TodayPage'](600, 800)
        self.assertIn('current_conditions', page.requires)
        for value, unit in [(13, '°C'), (0, '°C'), (-7, '°C'), (55, '°F')]:
            with self.subTest(value=value, unit=unit):
                rows = [{'forecast': 'preserved'}]
                page.template(map_url='map.png', hourly_forecasts=rows,
                              daily_summary={'temperature': {'min': 9, 'max': 21},
                                             'rain_probability': 40},
                              current_conditions={'temperature': {'value': value,
                                  'unit': unit, 'feels_like': value - 2},
                                  'icon': 'current.png', 'weather_text': 'Clear now'})
                forecast = page.received['forecast']
                self.assertEqual(forecast['temperature'], dict(
                    min=None, max=value, unit=unit, feels_like=value - 2))
                self.assertEqual(forecast['icon'], 'current.png')
                self.assertEqual(forecast['day_phrase'], 'Clear now')
                self.assertEqual(forecast['rain_probability'], 40)
                self.assertIs(page.received['hourly_forecasts'], rows)
