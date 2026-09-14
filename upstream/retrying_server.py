"""Local epd-server adapter: retry transient generation failures without new artwork."""
import logging
import json
import os
import time
from urllib.request import urlopen
from epd_server import DisplayServer as BaseDisplayServer

LOG = logging.getLogger("nookpanel.generation")


class DisplayServer(BaseDisplayServer):
    def _generation_interval(self, previous):
        url = os.environ.get("NOOK_SETTINGS_URL", "http://127.0.0.1:8001/api/settings")
        try:
            with urlopen(url, timeout=3) as response:
                interval = json.load(response)["server_refresh_seconds"]
            if type(interval) is not int or not 900 <= interval <= 86400:
                raise ValueError("invalid server generation interval")
            return interval
        except (OSError, ValueError, KeyError, TypeError):
            return previous  # Control service outages must not stop generation.

    def _loop(self):
        # Poll the control plane so saving a setting does not restart Chromium.
        # Epoch arithmetic avoids DST ambiguity. Keep the existing lead time.
        interval = self._generation_interval(1800)
        deadline = self._next_generation(time.time(), interval)
        LOG.info("Server image generation every %d seconds; next at %s", interval, time.ctime(deadline))
        while not self.shutdown_event.is_set():
            current = self._generation_interval(interval)
            if current != interval:
                interval = current
                deadline = self._next_generation(time.time(), interval)
                LOG.info("Server image generation updated to %d seconds; next at %s", interval, time.ctime(deadline))
            if self.shutdown_event.wait(min(15, max(0, deadline - time.time()))):
                break
            if time.time() < deadline:
                continue
            try:
                self.regenerate(force_refresh=True)
            except Exception:
                LOG.exception("Scheduled generation failed; retaining previous images")
            # Skip missed slots after slow renders; never queue overlapping runs.
            deadline = self._next_generation(time.time(), interval)

    def _next_generation(self, now, interval):
        lead = min(self.regen_lead_seconds, interval - 1)
        return ((now + lead) // interval + 1) * interval - lead

    def regenerate(self, only=None, force_refresh=False):
        # Serial upstream calls preserve its rendering lock and atomic PNG writes.
        # Three attempts per scheduled run; no concurrent Chromium retries.
        for attempt in range(3):
            try:
                return super().regenerate(only=only, force_refresh=force_refresh or attempt > 0)
            except Exception:
                if attempt == 2:
                    LOG.exception("Generation failed after 3 attempts; keeping existing images")
                    raise
                delay = 30 * (attempt + 1)
                LOG.exception("Generation failed; retrying in %d seconds (attempt %d/3)", delay, attempt + 2)
                if self.shutdown_event.wait(delay):
                    raise
