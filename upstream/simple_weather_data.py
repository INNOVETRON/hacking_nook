"""Extended hourly dataset used only by Simple Weather's wake planner."""
from datetime import datetime


def forecasts(service):
    data = service._fetch_forecast()
    hourly = data['hourly']
    now = datetime.fromisoformat(data['current']['time'])
    result = []
    def value(key, index):
        values = hourly.get(key, [])
        return values[index] if index < len(values) else None
    for i, stamp in enumerate(hourly['time']):
        stamp = datetime.fromisoformat(stamp)
        if stamp < now:
            continue
        if len(result) == 24:
            break
        temperature = value('temperature_2m', i)
        code = value('weather_code', i)
        result.append(dict(dt=stamp,
            icon=service.get_icon(service._icon_key(code, value('is_day',i))) if code is not None else '',
            temperature=dict(unit=service._temp_unit, value=round(temperature) if temperature is not None else None),
            rain_probability=value('precipitation_probability',i),
            wind=dict(unit=service._speed_unit, value=value('wind_speed_10m',i),
                      direction_degrees=value('wind_direction_10m',i))))
    return result
