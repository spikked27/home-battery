# Changelog

## 1.4.1

- Keep BMS DC-power readings and retired calculated planning helpers out of the critical-load chooser. Exclude integration-owned and selected BMS-device entities by registry identity so renamed entities remain filtered. Validate the same boundary on save.
- Put the current meter and available sensors first, then sort by friendly name.

## 1.4.0

- Add a searchable W/kW load-sensor chooser and 7/14/30/90-day learning period directly in Backup plan, with a shortcut and readable learning status on Overview. Show the actual usable history, missing coverage, expected daily energy and chronological prediction error.
- Learn local hourly weekday/weekend demand with recency weighting. Read completed hourly Recorder statistics only; never replace missing readings with zero or validate against future training data. Refresh every fifteen minutes and rebuild from the selected sensor after restart.
- Use learned weekday/weekend profiles for savings projections. Peak energy reservation can use learned demand plus observed prediction error only with at least 80% history coverage, 24 held-out checks, a current-day forecast and fresh model; otherwise retain live-load planning.
- Sensor changes clear the old heartbeat, start a separate pattern and pause scheduling for review. History-only changes preserve scheduling. Existing charging limits, reserves, protection checks and branding remain intact.

## 1.3.9

- Inspect history charts by hovering, touching, or using arrow keys. Show recorded values with units, cursor time and sample time; preserve missing-data gaps instead of interpolating values.
- Fix cell-group bars to the configured BMS low/high protection voltages. Read matching limit metadata from the selected cell sensors; never infer chemistry, autoscale around readings or alter equipment settings for display.
- Identify out-of-limit cell readings in red without expanding the axis. Preserve existing branding, scheduling and charging safeguards.

## 1.3.8

- Fix a high-charge alarm deadlock: block charging while allowing BMS-permitted recovery discharge for isolated high-SOC/cell/pack-voltage flags. Require a fresh explicit BMS discharge permission, all expected cells within a conservative recovery window, temperature, and a ready inverter.
- Unknown/mixed faults, missing permission or readings, or unsafe recovery values still block battery use. Use available utility with charging disabled for a protection hold; do not override the BMS or reset alarms.
- Preserve reserve/runtime visibility during protection holds. Keep charge target/cell latches and recharge hysteresis intact, and report recovery separately from ordinary scheduling.

## 1.3.7

- Stop utility charging at the configured SOC target, optional per-cell soft ceiling, or BMS/inverter alarm without changing load source. A hold on manual actions or scheduling does not defeat charge inhibition.
- Persist target/voltage latches across restarts. Require five SOC points / 50 mV of recovery and three minutes of clear readings before permitting recharge; do not replay interrupted source writes.
- Hold on grid without charging when saving energy for peak or when charging is uneconomical. Manual and scheduled charging requests respect the same guard.
- Report precise Daly alarm codes, payload and sample time. Only a fresh SOC-high level-one warning with valid cells below the configured ceiling can permit discharge; all other alarms continue to pause source changes.
- Add a visible charging-safeguard explanation. Do not reset SOC, alter BMS thresholds or force MOSFETs on. Utility-charge supervision requires HA/MQTT and cannot inhibit PV charging.

## 1.3.6

- Show verified inverter energy paths independently of reference-meter commissioning, with separate inverter AC output and planning-meter readings.
- Add explicit colored arrowheads, directional animation and solar input when measured; keep charging direction correct and suppress active paths on stale data.
- Clarify control names, disable unavailable controls, validate number input, and keep weather-tab scheduler/transfer status live without restarting radar.
- Preserve unknown cell difference as unavailable and distinguish local energy integration from BMS counters.

## 1.3.5

- Fix battery temperature unit recognition and Fahrenheit-to-Celsius conversion.
- Preserve valid chart intervals around short telemetry outages instead of blanking their entire average buckets.
- Extend recorded graphs with live samples, refresh history every minute, and show explicit charging/discharging state plus a live endpoint.
- Keep cached history on transient API errors while labeling refresh failures; preserve genuine unknown intervals.

## 1.3.4

- Make normal automatic scheduling independent of meter commissioning, with no separate test mode.
- Keep the selected reference load for reserve and price planning, and retain projected savings until a connected-panel meter is commissioned.
- Preserve verified source transitions, live telemetry, charge ceilings, fault handling and restart recovery.

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
