"""Optional daily program switching; every sleep stops at the next boundary."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re

PROGRAMS = {'simple-weather', 'weather-cal', 'clock-calendar'}


def validate(config):
    if type(config.get('program_schedule_enabled', False)) is not bool:
        raise ValueError('Program schedule enabled must be true or false.')
    schedule = config.get('program_schedule', {})
    if not isinstance(schedule, dict) or len(schedule) > 12 or any(
        not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', key) or value not in PROGRAMS
        for key, value in schedule.items()
    ):
        raise ValueError('Use up to 12 unique times and valid programs.')
    if config.get('program_schedule_enabled') and not schedule:
        raise ValueError('Add at least one scheduled program.')


def active(config, now=None):
    now = now or datetime.now(ZoneInfo(config.get('timezone', 'America/Edmonton')))
    schedule = config.get('program_schedule', {}) if config.get('program_schedule_enabled') else {}
    if not schedule:
        return config.get('active_program', 'weather-cal')
    keys = sorted(schedule)
    eligible = [key for key in keys if key <= now.strftime('%H:%M')]
    return schedule[eligible[-1] if eligible else keys[-1]]


def next_boundary(config, now=None):
    now = now or datetime.now(ZoneInfo(config.get('timezone', 'America/Edmonton')))
    if not config.get('program_schedule_enabled'):
        return None
    candidates = []
    for offset in (0, 1):
        for value in config.get('program_schedule', {}):
            hour, minute = map(int, value.split(':'))
            stamp = (now + timedelta(days=offset)).replace(hour=hour, minute=minute, second=0, microsecond=0)
            # Try both folds on a repeated clock hour; skip imaginary times.
            for fold in (0, 1):
                stamp = stamp.replace(fold=fold)
                roundtrip = datetime.fromtimestamp(stamp.timestamp(), now.tzinfo)
                if roundtrip.hour == hour and roundtrip.minute == minute and stamp.timestamp() > now.timestamp():
                    candidates.append(stamp.timestamp())
    return min(candidates) if candidates else None
