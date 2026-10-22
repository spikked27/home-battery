# Changelog

## 1.3.3

- Add explicit automatic scheduling with a test load, independently of meter commissioning. Reference-load savings stay projected.
- Keep verified source transitions, live telemetry, reserve logic, charging caps and fault handling mandatory in test-load mode.
- Label test automation and disable scheduling if its authorization is removed or the selected meter changes.

## 1.3.2

- Repeated taps on a pending source request preserve its deadline without repeating writes.
- After restarting beyond a pending deadline, allow up to 90 seconds for live telemetry to confirm whether transfer already completed before reporting failure.

## 1.3.1

- Observe source transfers for up to 12 minutes without blocking Home Assistant, reflecting two approximately ten-minute handovers in captured telemetry.
- Show a compact waiting status while keeping actual source and battery reserve visible. A stored preference still does not count as actual power transfer.
- Persist transfer deadlines, manual holds and switch timing; resume observation after restart without replaying writes. Interrupted settings transactions require review.
- Keep automatic writes inhibited during a pending transfer. Genuine write failures and expired transfer observations remain actionable in Advanced.

## 1.3.0

- Coordinate source preference with charging permission: battery use disables utility charging; grid charging restores SNU, within the existing DC current cap.

- Verify fresh actual inverter operating mode after SUB/SBU commands, including an unchanged preference. A stored setting alone no longer counts as a transfer.
- Show transfer progress and latch an actionable fault if the requested mode does not occur, with no automatic command retries.
- Document commissioning of the hardware return-to-battery SOC threshold before enabling source scheduling.

## 1.2.0

- Keep current battery percentage, outage reserve and runtime together on Overview and Backup.
- Add reference-load daily/monthly/yearly savings projections from recorded hourly usage, current charging limits and reserve assumptions; switch the main display to a separate recorded-operation ledger after panel commissioning.
- Restore an animated regional RainViewer radar with local Leaflet assets, visible attribution and data freshness.
- Restore vertical cell bars on a common scale, selectable group values and an optional full-scale view.
- Use thin time-weighted history lines, faint min/max ranges and a signed battery-current zero line. Compact navigation and weather summaries across screen sizes.
- Changing the selected load meter clears commissioning and disables scheduling until the new source is confirmed.

## 1.1.2

- Pause new financial accounting until the critical-load meter is commissioned. Planning and measured energy history remain available; existing historical estimates are retained.

## 1.1.1

- Label uncommissioned load meters as reference loads and suppress unconfirmed load-supply arrows. Preserve the user's selected meter while distinguishing planning measurements from inverter output.
- Run retained bridge discovery callbacks on the Home Assistant event loop.

## 1.1.0

- Restore critical-load usage and cell-difference trends, with 24-hour, 7-day and 30-day history windows and existing bridge history.
- Make backup hours the primary reserve preference; explain the larger-of-hours-or-percent rule and move the percentage floor to Advanced.
- Expand weather into current conditions, humidity, wind/gusts, rain probability, high/low forecast, pressure, official alert details and radar access.
- Suggest known Daly and inverter bridge sources from stable entity identities, preserving renamed entities and physical cell ordering; prefill the MQTT root from its retained discovery record when available.
- Ship local brand icons/logos for Home Assistant and HACS, plus a dashboard logo.
- Fix text encoding and round tiny savings values to zero rather than negative zero.

## 1.0.0

Initial complete integration: local MQTT adapter, guided setup, 25 bridge controls, built-in panel, reserve-first SUB/SBU scheduling, weather recommendations, public PSEG pricing, persistent cash-flow accounting, energy/cell diagnostics and commissioning controls.
