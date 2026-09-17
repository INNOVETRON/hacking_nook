# Upstream's server, with Google Static Maps swapped for keyless OSM tiles.
#
# Everything else — the HTML/CSS page layouts, Chart.js, rough.js, Selenium and
# the headless Chromium that screenshots them — remains upstream's.
# The Google adapter removes the billing dependency; the retry adapter handles
# transient generation failures.
FROM ghcr.io/chrisjtwomey/inkplate10-weather-cal-server:latest

USER root

# Our map code, shared with the Pillow renderer in ../server.
COPY server/mapview.py /app/nook_mapview.py
COPY server/linemap.py /app/linemap.py
COPY server/fonts.py /app/fonts.py
COPY upstream/google_api_shim.py /app/google/api.py

RUN chown -R app:app /app/google /app/nook_mapview.py /app/linemap.py /app/fonts.py

COPY upstream/retrying_server.py /app/retrying_server.py
COPY upstream/smart_chart.py /app/smart_chart.py
COPY upstream/eccc_current.py /app/eccc_current.py
COPY upstream/eccc_weather.py /app/eccc_weather.py
COPY upstream/simple_weather.py /app/simple_weather.py
COPY upstream/simple_weather_data.py /app/simple_weather_data.py
COPY server/adaptive_refresh.py /app/adaptive_refresh.py
COPY upstream/patches/ /tmp/nook-patches/
# Apply the same overlays as the native Pi install (strip the server/ prefix).
RUN for patch in /tmp/nook-patches/*.patch; do git apply -p2 "$patch" || exit 1; done \
    && chown -R app:app /app/views /app/server.py /app/weather \
    && rm -rf /tmp/nook-patches

USER app
