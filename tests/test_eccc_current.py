from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'upstream'))
from eccc_current import parse_observation, fetch_observation

NOW = datetime(2026, 9, 16, 22, 30, tzinfo=timezone.utc)
XML = '''<siteData><currentConditions>
<station>Edmonton Blatchford</station>
<dateTime zone="UTC"><timeStamp>20260916220000</timeStamp></dateTime>
<temperature units="C" qaValue="100">19.7</temperature>
</currentConditions></siteData>'''


class Observations(unittest.TestCase):
    def test_measured_temperature_without_invented_feels_like(self):
        obs = parse_observation(XML, NOW)
        self.assertEqual(obs['value'], 19.7)
        self.assertIsNone(obs['feels_like'])
        self.assertEqual(obs['station'], 'Edmonton Blatchford')

    def test_zero_negative_and_wind_chill(self):
        for value in ('0', '-25.4'):
            xml = XML.replace('19.7', value).replace('</currentConditions>',
                '<windChill>-32</windChill></currentConditions>')
            obs = parse_observation(xml, NOW)
            self.assertEqual(obs['value'], float(value))
            self.assertEqual(obs['feels_like'], -32)

    def test_reject_invalid_observations(self):
        for xml in (XML.replace('19.7', 'NaN'), XML.replace('19.7', ''),
                    XML.replace('100', '10'), XML.replace('units="C"', 'units="F"'),
                    XML.replace('20260916220000', '20260916180000'),
                    XML.replace('20260916220000', '20260916230000')):
            with self.subTest(xml=xml), self.assertRaises(ValueError):
                parse_observation(xml, NOW)

    def test_missing_current_hour_uses_previous_hour(self):
        calls = []
        name = '20260916T210053.355Z_MSC_CitypageWeather_s0000045_en.xml'
        def reader(url):
            calls.append(url)
            if url.endswith('/22/'):
                return '<html>No file yet</html>'
            if url.endswith('/21/'):
                return '<a href="' + name + '">file</a>'
            return XML.replace('20260916220000', '20260916210000')
        self.assertEqual(fetch_observation(NOW, reader)['value'], 19.7)
        self.assertEqual(len(calls), 3)

    def test_network_failure_never_returns_model_value(self):
        def offline(url):
            raise OSError('offline')
        with self.assertRaises(ValueError):
            fetch_observation(NOW, offline)
