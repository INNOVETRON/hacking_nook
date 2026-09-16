"""ECCC observed current temperature, Open-Meteo forecast datasets."""
from datetime import timezone
from zoneinfo import ZoneInfo
import logging

from weather.openmeteo.openmeteo import OpenMeteoService
from weather.registry import register
from eccc_current import fetch_observation

LOG = logging.getLogger('nookpanel.eccc')


@register('openmeteo_eccc')
class EdmontonWeather(OpenMeteoService):
    def __init__(self, *, apikey=None, location=None, num_hours=6, metric=True):
        if (location or '').strip().lower() != 'edmonton':
            raise ValueError('openmeteo_eccc currently supports Edmonton only')
        super().__init__(apikey=apikey, location=location, num_hours=num_hours, metric=metric)
        self._observation = None

    def invalidate_forecast_cache(self):
        super().invalidate_forecast_cache()
        self._observation = None

    def get_current_conditions(self):
        # Keep model icon/context but never substitute model temperature for a
        # missing observation. Existing image recovery retains the last good PNG.
        if self._observation is None:
            self._observation = fetch_observation()
        observation = self._observation
        current = dict(super().get_current_conditions())
        def convert(value):
            if value is None:
                return None
            return round(value if self.units == 'metric' else value * 9 / 5 + 32)
        current['temperature'] = dict(unit=self._temp_unit,
            value=convert(observation['value']), feels_like=convert(observation['feels_like']))
        local = observation['observed'].astimezone(ZoneInfo('America/Edmonton'))
        current['weather_text'] = 'ECCC · Blatchford · ' + local.strftime('%-I:%M %p')
        LOG.info('ECCC %s: %.1f C observed %s', observation['station'],
                 observation['value'], observation['observed'].astimezone(timezone.utc).isoformat())
        return current
