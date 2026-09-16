"""Integration/visual check against an isolated checkout with all patches applied.

Run with the weather-cal venv: python check_smart_renderer.py --server PATH
Add --previews DIR to render Today/Tomorrow examples using headless Chromium.
"""
import argparse
import copy
from datetime import datetime, timedelta
from pathlib import Path
import sys
from unittest.mock import Mock, patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--server', required=True)
    parser.add_argument('--previews')
    args = parser.parse_args()
    sys.path.insert(0, str(Path(args.server).resolve()))
    from views.today import TodayPage
    from views.tomorrow import TomorrowPage
    from weather.openmeteo.openmeteo import OpenMeteoService

    class Cache:
        def __init__(self): self.values = {}
        def get(self, key, **kw): return self.values.get(key)
        def set(self, key, value): self.values[key] = value
        def delete(self, *keys):
            for key in keys: self.values.pop(key, None)

    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    times = [now.replace(hour=0) + timedelta(hours=i) for i in range(72)]
    hourly = {key: [value] * 72 for key, value in {
        'temperature_2m': 18, 'wind_speed_10m': 8, 'wind_direction_10m': 180,
        'wind_gusts_10m': 15, 'relative_humidity_2m': 50, 'precipitation_probability': 0,
        'precipitation': 0, 'uv_index': 4, 'cloud_cover': 10, 'is_day': 1, 'weather_code': 0,
    }.items()}
    hourly['time'] = [t.isoformat() for t in times]
    service = object.__new__(OpenMeteoService)
    service.cache, service.units, service.num_hours = Cache(), 'metric', 9
    service.service_name = 'openmeteo'
    service.baseurl, service.lat, service.lon = 'https://api.open-meteo.com/v1/forecast', 53.55, -113.47
    response = Mock()
    response.json.return_value = {'hourly': hourly, 'current': {'time': now.isoformat()}}
    service.cache.set('forecast', {'hourly': {'time': hourly['time']}})  # old schema
    with patch('weather.openmeteo.openmeteo.requests.get', return_value=response) as get:
        service._fetch_forecast()
        assert 'uv_index' in get.call_args.kwargs['params']['hourly']
        assert 'wind_gusts_10m' in get.call_args.kwargs['params']['hourly']
        service._fetch_forecast()
        assert get.call_count == 1  # one combined request; new-schema cache is reused
    service._fetch_forecast = lambda: {'hourly': hourly, 'current': {'time': now.isoformat()}}
    service.cache.set('hourly_forecast', [{'dt': now}])
    service.cache.set('tomorrow_hourly', [{'dt': now}])
    today = service.get_hourly_forecast()
    tomorrow = service.get_tomorrow_hourly()
    assert len(tomorrow) == 16 and tomorrow[9]['dt'].hour == 15
    assert today[0]['uv_index'] == 4 and tomorrow[0]['wind']['gust'] == 15
    assert tomorrow[0]['cloud_cover'] == 10 and tomorrow[0]['precipitation_mm'] == 0
    service.invalidate_forecast_cache()
    assert service.cache.get('tomorrow_hourly') is None
    assert service._chart_fields({}, 0)['uv_index'] is None
    print('PASS: hourly fields, every tomorrow hour, missing values, cache invalidation')

    daily = dict(dt=now + timedelta(days=1), icon='icon/day/clear.png',
                 temperature={'unit': '°C', 'min': 9, 'max': 21, 'feels_like': 20},
                 wind={'unit': 'kmh', 'value': 8}, rain_probability=0)
    # Use an existing local map when available; no map fetch is needed to test charts.
    maps = list(Path('/home/afshin/hacking_nook/external/inkplate10-weather-cal/server/views/html').glob('osmmap*.png'))
    map_url = maps[0].as_uri() if maps else ''
    generated = []
    for name, kind, cls in [('today-uv', 'uv', TodayPage), ('tomorrow-rain', 'precipitation', TomorrowPage),
                            ('today-wind', 'wind', TodayPage), ('tomorrow-temperature', 'temperature', TomorrowPage)]:
        rows = copy.deepcopy(today if cls is TodayPage else tomorrow)
        for i, row in enumerate(rows):
            row.update(uv_index=max(0, 5 - abs(4-i)) if kind == 'uv' else 0,
                       cloud_cover=10 if kind == 'uv' else 90,
                       rain_probability=85 if kind == 'precipitation' and i == 9 else 0,
                       weather_code=3)
            row['wind'].update(value=20 + i if kind == 'wind' else 8,
                               gust=45 if kind == 'wind' else 15)
            row['temperature']['value'] = -12 + i // 2 if kind == 'temperature' else 18
        page = cls(600, 800)
        if cls is TodayPage:
            page.template(map_url=map_url, daily_summary=daily, hourly_forecasts=rows,
                          current_conditions=dict(icon=daily["icon"],
                              temperature={"unit": "°C", "value": 13, "feels_like": 12},
                              weather_text="Currently clear"))
        else:
            page.template(map_url=map_url, tomorrow_forecast=daily, tomorrow_hourly=rows)
        html = str(page.airium)
        if cls is TodayPage:
            assert 'id="day-temp-lo"' not in html
            assert '13°C' in html and 'Feels like 12' in html
            assert 'Currently clear' in html
        assert f'data-metric="{kind}"' in html, name
        assert '<svg' in html and 'nan' not in html and 'None' not in html
        if kind in ('uv', 'temperature'):
            assert 'day-chart-curve' in html and ' C ' in html and '<rect' not in html
        else:
            assert '<rect' in html and 'day-chart-curve' not in html
        path = Path(args.server) / 'views/html' / (name + '.html')
        path.write_text(html)
        generated.append((name, path))
    print('PASS: real Today/Tomorrow templates for precipitation, UV, wind and negative temperature')

    if args.previews:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.support.ui import WebDriverWait
        out = Path(args.previews)
        out.mkdir(parents=True, exist_ok=True)
        options = Options()
        for flag in ['--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu', '--allow-file-access-from-files']:
            options.add_argument(flag)
        with webdriver.Chrome(options=options) as driver:
            driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride', {'width': 600, 'height': 800, 'deviceScaleFactor': 1, 'mobile': False})
            for name, path in generated:
                driver.get(path.as_uri())
                driver.execute_async_script('document.fonts.ready.then(() => arguments[0]());')
                WebDriverWait(driver, 20).until(lambda d: d.execute_script('return Array.from(document.images).every(i => i.complete)'))
                bounds = driver.execute_script('const r=document.querySelector("#day-precip").getBoundingClientRect(); return {left:r.left,right:r.right,bottom:r.bottom};')
                assert bounds['left'] >= 0 and bounds['right'] <= 601 and bounds['bottom'] <= 800, bounds
                driver.save_screenshot(str(out / (name + '.png')))
                print('Rendered', name, bounds)


if __name__ == '__main__':
    main()
