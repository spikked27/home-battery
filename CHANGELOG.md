# Changelog

## 1.1.0

- Restore critical-load usage and cell-difference trends, with 24-hour, 7-day and 30-day history windows and existing bridge history.
- Make backup hours the primary reserve preference; explain the larger-of-hours-or-percent rule and move the percentage floor to Advanced.
- Expand weather into current conditions, humidity, wind/gusts, rain probability, high/low forecast, pressure, official alert details and radar access.
- Suggest known Daly and inverter bridge sources from stable entity identities, preserving renamed entities and physical cell ordering; prefill the MQTT root from its retained discovery record when available.
- Ship local brand icons/logos for Home Assistant and HACS, plus a dashboard logo.
- Fix text encoding and round tiny savings values to zero rather than negative zero.

## 1.0.0

Initial complete integration: local MQTT adapter, guided setup, 25 bridge controls, built-in panel, reserve-first SUB/SBU scheduling, weather recommendations, public PSEG pricing, persistent cash-flow accounting, energy/cell diagnostics and commissioning controls.
