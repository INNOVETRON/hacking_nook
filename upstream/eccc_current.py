"""Measured Edmonton temperature from ECCC's public Citypage XML feed."""
from datetime import datetime, timedelta, timezone
import math
import re
import urllib.request
import xml.etree.ElementTree as ET

BASE = 'https://dd.weather.gc.ca/today/citypage_weather/AB/'
SITE = 's0000045'  # Edmonton city; station Edmonton Blatchford, not the airport.


def read_url(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.read(2_000_000).decode('utf-8')


def parse_observation(xml, now):
    root = ET.fromstring(xml)
    current = root.find('currentConditions')
    if current is None:
        raise ValueError('ECCC current conditions missing')
    stamp = current.findtext("dateTime[@zone='UTC']/timeStamp")
    observed = datetime.strptime(stamp or '', '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
    age = (now - observed).total_seconds()
    if not -300 <= age <= 3 * 3600:
        raise ValueError('ECCC observation is stale or in the future')

    def number(tag, required=False):
        node = current.find(tag)
        if node is None or not node.text:
            if required:
                raise ValueError('ECCC temperature missing')
            return None
        if node.get('qaValue') and float(node.get('qaValue')) < 100:
            if required:
                raise ValueError('ECCC temperature failed quality control')
            return None
        value = float(node.text)
        if not math.isfinite(value):
            raise ValueError('ECCC non-finite measurement')
        return value

    temperature = number('temperature', required=True)
    if current.find('temperature').get('units') != 'C' or not -90 <= temperature <= 60:
        raise ValueError('Invalid ECCC temperature or units')
    feels = number('windChill')
    if feels is None:
        feels = number('humidex')
    return dict(value=temperature, feels_like=feels,
                station=current.findtext('station') or 'Edmonton',
                observed=observed)


def fetch_observation(now=None, reader=read_url):
    now = now or datetime.now(timezone.utc)
    error = None
    for offset in range(4):
        hour = now - timedelta(hours=offset)
        directory = BASE + hour.strftime('%H/')
        try:
            listing = reader(directory)
            names = sorted(set(re.findall(
                r'\d{8}T\d{6}\.\d+Z_MSC_CitypageWeather_' + SITE + r'_en\.xml', listing)), reverse=True)
            for name in names[:2]:
                try:
                    return parse_observation(reader(directory + name), now)
                except (OSError, ValueError, ET.ParseError) as exc:
                    error = exc
        except (OSError, ValueError) as exc:
            error = exc
    raise ValueError('No fresh ECCC Edmonton observation available') from error
