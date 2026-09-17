# Display improvements

Implementation checklist (2026-09-16):

- [x] Battery percentage, charging state, and discharge-based remaining-days estimate.
- [x] Fetch reliability: overdue state, failed transfers, and device-reported failures.
- [x] Distinct overnight morning briefing with morning weather and next wake time.
- [x] Leaving-home summary: feels-like, precipitation timing, and wind.
- [x] Twelve-hour temperature trend.
- [x] Dashboard preview of the actual served image and generation timestamp.
- [x] Optional time-of-day program schedule, including a clock/calendar banner.
- [x] Adaptive fetch savings compared with an hourly baseline.
- [x] Final deployment verification and Git push.
- [x] 66 tests, artwork review, server deployment, and APK update (live battery report: 93%, unplugged).

Battery estimates require enough real, unplugged readings. A missed fetch cannot
prove a Wi-Fi failure; failures that prevent contact are reported on reconnection.
The clock/calendar banner is a snapshot with its update time, not a live clock.
