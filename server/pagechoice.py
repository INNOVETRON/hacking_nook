"""Which of upstream's pages to show right now.

Two rules, in order:

1. **Advisory override.** If something is about to change that you would want to
   know before going out — precipitation starting, rain turning to snow, a
   thunderstorm, a crossing of freezing, a big temperature swing, a wind
   pick-up — show the **hourly** page, because that is the one that says *when*.
2. **Time of day.** Otherwise follow the schedule: hourly in the morning,
   today through the day, daily in the evening, tomorrow overnight.

A gradual drift in the current conditions is deliberately not an advisory.
Cloud thickening, or the temperature sliding two degrees over six hours, is what
the day view already shows; interrupting it adds noise, not information.
"""

import logging
from datetime import datetime

LOG = logging.getLogger("nookpanel.pagechoice")

# "HH:MM" -> page shown from that time until the next entry.
DEFAULT_SCHEDULE = {
    "06:00": "hourly",    # before you leave: what the next nine hours do
    "09:30": "today",     # the ambient default, and the longest stretch
    "17:00": "daily",     # end of the day: the week ahead
    "21:00": "tomorrow",  # before bed: what you are waking up to
}

DEFAULTS = {
    "advisory_hours": 6,          # how far ahead to look
    "advisory_from": "06:00",     # only interrupt during waking hours
    "advisory_to": "22:00",
    "precip_probability": 50,     # % that counts as "it is going to"
    "precip_dry_probability": 25, # below this now counts as "currently dry"
    "temp_swing": 8.0,            # degrees over the window
    "wind_speed": 40.0,           # km/h (or mph if units are imperial)
}

SNOW_CODES = {71, 73, 75, 77, 85, 86}
RAIN_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82}
STORM_CODES = {95, 96, 99}


def _minutes(text):
    hour, _, minute = text.partition(":")
    return int(hour) * 60 + int(minute)


def scheduled_page(config, now):
    schedule = config.get("page_schedule") or DEFAULT_SCHEDULE
    enabled = config.get("enabled_pages")
    if enabled is not None:
        schedule = {k: v for k, v in schedule.items() if v in enabled}
    if not schedule:
        return enabled[0] if enabled else "today"
    current = now.hour * 60 + now.minute
    entries = sorted((_minutes(k), v) for k, v in schedule.items())

    chosen = entries[-1][1]          # before the first entry, the overnight one
    for start, page in entries:
        if current >= start:
            chosen = page
    return chosen


def _setting(config, key):
    return config.get(key, DEFAULTS[key])


def advisory(config, weather, now):
    """Return a short reason to force the hourly page, or None.

    Compares the current hour against the next `advisory_hours` and reports the
    first thing that is a genuine change of kind, not of degree.
    """
    forecasts = weather.hourly_from_now(now, count=_setting(config, "advisory_hours") + 1)
    if len(forecasts) < 2:
        return None

    current, upcoming = forecasts[0], forecasts[1:]

    dry_now = (current["precipitation_probability"] or 0) < _setting(
        config, "precip_dry_probability")
    now_snow = current["code"] in SNOW_CODES
    now_rain = current["code"] in RAIN_CODES
    threshold = _setting(config, "precip_probability")

    for forecast in upcoming:
        when = forecast["time"].strftime("%-I%p").lower()
        probability = forecast["precipitation_probability"] or 0

        if forecast["code"] in STORM_CODES:
            return f"thunderstorm by {when}"

        if dry_now and probability >= threshold:
            kind = "snow" if forecast["code"] in SNOW_CODES else "rain"
            return f"{kind} likely by {when} ({probability}%)"

        # A change of kind matters even when it is already wet: rain turning to
        # snow changes what you put on your feet.
        if now_rain and forecast["code"] in SNOW_CODES:
            return f"turning to snow by {when}"
        if now_snow and forecast["code"] in RAIN_CODES:
            return f"turning to rain by {when}"

    temperatures = [f["temperature"] for f in forecasts if f["temperature"] is not None]
    if temperatures:
        swing = max(temperatures) - min(temperatures)
        if swing >= _setting(config, "temp_swing"):
            return f"{round(swing)}° swing in the next {len(forecasts) - 1}h"

        # Ice is worth flagging at a much smaller swing than that.
        if min(temperatures) <= 0 < max(temperatures):
            return "crossing freezing"

    winds = [f["wind_speed"] for f in forecasts if f["wind_speed"] is not None]
    if winds and winds[0] < _setting(config, "wind_speed") <= max(winds):
        return f"wind rising to {round(max(winds))}"

    return None


def _within_waking_hours(config, now):
    current = now.hour * 60 + now.minute
    start = _minutes(_setting(config, "advisory_from"))
    end = _minutes(_setting(config, "advisory_to"))
    return start <= current < end if start <= end else (current >= start or current < end)


def choose(config, weather, now):
    """Return (page_name, reason). `reason` is None when nothing overrode."""
    page = scheduled_page(config, now)

    if "hourly" not in config.get("enabled_pages", ["hourly"]):
        return page, None
    if not config.get("advisories", True) or weather is None or not weather.data:
        return page, None
    if not _within_waking_hours(config, now):
        return page, None

    try:
        reason = advisory(config, weather, now)
    except Exception:
        LOG.exception("advisory check failed; falling back to the schedule")
        return page, None

    if reason and page != "hourly":
        return "hourly", reason
    return page, reason if reason else None
