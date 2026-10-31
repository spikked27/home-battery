# Unreleased — optional Pi bridge

- Add verified stored values for 5% inverter SOC shutdown, 10% utility transfer and 44 V transfer voltage; retain a bounded command whitelist and independent protection requirements. This does not change any user's inverter settings automatically.
- Avoid redundant FTDI modem-status requests during serial transmit drain; retain complete-write checks, response deadlines and no automatic retry of uncertain writes.

# 1.9.4

- Honor the HPVINV09's fresh, read-back grid-transfer SOC floor in live scheduling, the 24-hour plan, and projected savings. Keep the user's single hours-based outage target; never lower inverter/BMS protection settings automatically.
- Calculate backup energy above the configured inverter shutdown SOC. Explain the effective grid floor and excluded shutdown energy beside the reserve display.
- Recalculate savings when inverter boundaries change. Pause planning for this known inverter when its SOC-limit readback is missing, malformed, or stale. Threshold precedence and voltage/cell-based cutoff behavior remain uncommissioned.
- Add policy, forecast, financial-model, HA-backed readback, and dashboard rendering regressions.

# 1.9.3

- Keep a started paid cold-weather charge stable above target-minus-five until the normal target, temperature/other protection, or cost budget stops it.
- Persist one advance-attempt marker per upcoming overnight window so falling SOC cannot repeatedly re-arm paid charging. The preview uses the same marker and continuous-charge semantics.
- Includes v1.9.2's missing overnight-block fix and separation of live schedule stops from battery protection. Regression coverage includes a cold morning with no repeated paid-charge pulses.

# 1.9.2

- Fix missing overnight charge blocks after adding cold-weather scheduling. A live daytime charge-stop flag must not become a battery protection reason copied through every future forecast interval.
- Keep schedule stop enforcement independent of source-switch cooldown in the live controller. Ordinary scheduling no longer displays a misleading battery charging-paused warning; temperature, cell, SOC, alarm and recovery guards are unchanged.
- Add regressions that reproduce the missing charge block and distinguish schedule permission from battery protection. Existing HA-backed enforcement coverage remains in place.

# 1.9.1

- Validate held-out passive temperature intervals against an hourly cooling profile fitted only to earlier observations, then fit the operational profile to all history.
- Explain when the chosen charging time is earlier than the coldest candidate because the predicted temperature and uncertainty approach the charging floor.

# 1.9.0

- Add optional temperature-aware timing of needed overnight charging. Learn passive cooling from up to seven days of Celsius-normalized recorder statistics and live samples, with held-out rate checks. Normal charging continues while learning.
- Prefer colder useful hours, retaining completion margin; start before predicted cold-limit crossings. Once overnight charging starts, keep it stable. Reserve, storm readiness, charge targets, cell limits and BMS protection remain authoritative.
- Optional cold-weather availability advances needed charging outside cheap hours under a persistent daily cost cap. Stop permission bypasses source-switch cooldown; uncertain interrupted accounting suspends further paid advances for the day.
- Auto-detect the coldest probe on the selected known Daly device; expose a configurable cold-temperature source, charging floor, controls and diagnostic entities. Add clear status on Overview, Backup plan and Weather while preserving radar and branding.
- No deliberate thermal cycling, forced discharge, increased charging current, heater control or BMS writes. Charging-temperature associations are measured but no heating benefit is credited to forecasts. Long-run savings projections exclude weather-dependent advances; actual charging remains in recorded costs.

# 1.8.6

- Simplify the 24-hour timeline to one block per continuous action. Adjacent utility, battery or charging periods no longer split merely because the controller's explanation or tariff changes.
- Preserve the original explanations, full time span, endpoint SOC and any rate range in selected-period details. Timeline selection still follows the inspected clock time. Controller forecasts and live scheduling are unchanged.

# 1.8.5

- Keep an inspected schedule period selected until another period is activated. Touch panning, pointer-enter events after layout changes, and restored focus no longer overwrite the selection. Hover retains the native tooltip.
- Preserve timeline selection and horizontal position across Home Assistant panel recreation and temporary forecast gaps; keep separate state for each integration entry.
- Avoid redundant focus restoration and restore horizontal position after focus. Planning and inverter control behavior are unchanged.

# 1.8.4

- Preserve the requested outage duration while avoiding expensive routine top-ups of the extra planning allowance. Hold utility without charging when the requested hours remain covered; recharge normally during the cheap window. Genuine duration shortfalls and storm readiness retain recovery charging.
- Explain when the backup target is covered while its planning allowance is in use.
- Includes persistent timeline DOM and accurate short-recovery forecasting from 1.8.3.

# 1.8.3

- Reconcile live Overview content in place instead of destroying its interactive timeline during telemetry updates. Preserve native scroll/focus and open details, including when transient notices appear or disappear.
- Display the loaded dashboard bundle version rather than presenting the controller version as proof of a frontend update.
- Label reserve maintenance as Restore backup and simulate those brief top-ups at the live 30-second cadence rather than a full 15-minute charge bucket. Reserve protection and live control policy are unchanged.

# 1.8.2

- Preserve the selected clock time, horizontal timeline position, keyboard focus and panel scroll across telemetry refreshes. Updated forecasts can split or merge periods without resetting inspection to the beginning.
- Release the edited input after saving so fresh reserve and savings values can render; queue a follow-up refresh if polling is already in progress.
- Show projected monthly and annual savings beside the backup target; recorded historical savings remain unchanged.

# 1.8.1

- Correct the remaining savings-profile help text: all profiles keep the same backup-hours target.

# 1.8.0

- Use backup hours as the single normal reserve target; calculate the percentage automatically from demand, capacity and losses.
- Retire the editable percentage floor, ignore legacy values, and remove its entity on upgrade.
- Keep the requested backup time consistent across savings preferences; retain storm overrides and battery protections.
- Explain the calculated percentage alongside the hours target on Overview and Backup plan.

# Changelog

## 1.7.0

- Stop recycling expensive reserve-recovery energy. Once the daily battery allocation reaches the reserve, retain utility until the next configured low-price charging window. Restore a genuinely deficient backup reserve when needed; preserve that energy for backup instead of immediately discharging it again. Persist this daily reserve hold across restart.
- Apply the same stateful reserve logic to live control, the anticipated timeline and savings projections. Keep reserve floors, storm readiness, charging guard hysteresis, current caps, freshness checks and command safeguards intact.
- Make disabled automatic scheduling prominent and show modeled costs with and without the battery. Label projected daily/monthly/yearly values as current-price run rates.

## 1.6.1

- Use an independent copy of the real utility-charge guard in the schedule preview. A cleared historical alarm latch can recover with the SOC latch after the clear-reading period, instead of falsely projecting a whole day without charging. Cell readings remain fixed; unknown future cell-voltage recovery is not invented.
- Explain charging inhibition within the affected timeline periods. Model the recovery check at the preview's fifteen-minute resolution; live protections and their timing are unchanged.
- Apply estimated idle draw before clipping net charging to the target, so the preview reaches its target rather than falsely charging just below it all night.

## 1.6.0

- Add a horizontal rolling 24-hour schedule card to Overview, with charging, battery and utility periods, local-time labels, estimated SOC/reserve traces, duration totals and pointer/touch/keyboard period details.
- Build the preview with the same scheduling policy, active savings preference, checked weekday forecasts or live-load fallback, SOC, current charge limits and charge-target hysteresis. Preview computation never sends commands or mutates live settings/guard state.
- Label schedule estimates and their assumptions. Reflect manual holds, faults, pending transfers, startup settling, missing prices/limits, alarms and stale readings; do not invent future cell/alarm recovery. Handle 24 elapsed hours across daylight-saving changes.

## 1.5.0

- Add Aggressive Savings, More Savings and More Outage Protection with readable choice cards. Vary checked peak-forecast headroom by zero, one or two typical prediction errors; the outage profile also retains 50% more estimated backup time. User reserve floors, charging limits, storm readiness and BMS protections remain authoritative.
- Keep automatic scheduling active while history builds, using live-load fallback with the same economic and protection checks. Show which planning path is in use. Forecast quality gates apply equally to every profile.
- Migrate old preference names without changing entity IDs or automatic enablement. More Outage Protection replaces the previous utility-only Backup first behavior and can shave peaks above its larger reserve.

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
