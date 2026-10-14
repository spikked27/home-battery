# Home Battery

Local Home Assistant energy management for a critical-load battery system: readable controls, outage reserve, weather readiness, time-of-use scheduling and estimated net savings.

[![Tests](https://github.com/spikked27/home-battery/actions/workflows/tests.yml/badge.svg)](https://github.com/spikked27/home-battery/actions/workflows/tests.yml)
[![Open HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=spikked27&repository=home-battery&category=integration)

## What v1 includes

- Guided UI setup with searchable power, battery and weather entity selectors.
- A built-in responsive dashboard: Overview, Backup plan, Savings, Battery health, Weather and Advanced. No custom dashboard cards or separate frontend download.
- All 25 established DATOUBOSS HPVINV09 bridge configuration points, with bridge-advertised options, human-readable explanations and confidence metadata. Unknown enum codes remain explicitly unknown.
- Verified manual SUB/SBU commands with readback acknowledgement, exclusive command handling, non-retained MQTT messages and fault latching.
- Automatic SUB/SBU scheduling with reserve-first decisions, economical off-peak/peak use, federal-holiday handling, manual override hold, restart grace period and five-minute switching cooldown.
- Configurable outage hours, usable capacity, reserve floor/margin, storm reserve, efficiencies, overhead, wear cost and minimum economic margin.
- Automatic PSEG Long Island Rate 195 monthly supply lookup plus the verified 2026 delivery table, or manual three-period prices.
- Forward-only estimated daily/monthly/yearly net savings; battery charge/discharge energy sensors suitable for the HA Energy dashboard.
- Highest/lowest cell positions, cell spread, battery temperature, current, alarms and cumulative throughput.
- Fresh weather/forecast advisory, manual storm override, and a link to official radar.
- Persistent accounting, diagnostics, stable per-installation entity identities, and integration-owned configuration entities instead of dozens of helpers.

## Architecture and prerequisites

```text
Inverter ↔ local serial bridge ↔ MQTT ↔ Home Battery ↔ Home Assistant
Daly BMS ↔ existing BMS bridge ↔ MQTT/HA sensors ────┘
```

Home Battery does **not** open serial ports or replace a BMS. Configure HA's MQTT integration and a compatible HPVINV09 bridge before adding Home Battery. Existing MQTT discovery sensors can remain installed. A protocol contract and source-bridge installation documentation are in [docs/bridge.md](docs/bridge.md).

The verified hardware profile is DATOUBOSS/MFUZOP HPVINV09, firmware `0010.03 20260202`, 2400-baud RS232. Similar brands/model numbers are not proof of compatibility. Public v1 support means the established configuration/readback paths; it does not assert physical commissioning of every control.

## Install with HACS

1. In HACS → menu → Custom repositories, add `https://github.com/spikked27/home-battery`, category **Integration**.
2. Download Home Battery and restart Home Assistant.
3. Settings → Devices & services → Add integration → **Home Battery**.
4. Enter your bridge MQTT root (the prefix before `/status`, without wildcards).
5. Select battery SOC, **live critical-load AC power in W/kW**, separate nonnegative charging/discharging DC power, and the alarm sensor. Add optional temperature, pack voltage, current, remaining Ah, cumulative kWh, ordered cell sensors, weather and severe-alert sources.
6. The Home Battery sidebar panel appears automatically. Review assumptions in Backup plan and Advanced.

For a manual install, copy `custom_components/home_battery` into `/config/custom_components/` and restart. HACS custom-repository installation does not imply inclusion in HACS's default catalog.

## Commission scheduling

Scheduling starts **disabled**. Observe the recommendations first. Confirm that the selected meter measures the actual critical loads and that **SUB starts grid charging** and **SBU supplies those loads from battery** on your inverter. Enable the two commissioning switches, then Automatic scheduling.

Only source preference is automatically changed. BMS thresholds, MOSFETs, charge current, timers, and output settings are never changed by the scheduler. Manual controls pause scheduling for the configured hold. Failed/uncertain commands latch a fault and stop automatic writes until deliberately acknowledged with a ready bridge.

**Charge target is advisory:** a neutral grid-without-charging state is not verified for this firmware. Reaching the target keeps SUB; it does not promise that charging stops at that SOC. Hardware/BMS charge limits still determine termination. This is an energy-management system, not a protective controller; HA downtime suspends scheduling and leaves the inverter's current setting in place.

## Current limits are different quantities

Program 02 is combined solar + grid **battery-side DC charging amps**; program 11 is the grid contribution within that limit. They do not limit emergency AC battery output. The integration's charging ceiling never exceeds **30 A DC**. The AC supply budget is capped at **32 A**, representing an 80% planning allowance for a 40 A supply. That budget is not a verified hardware limiter. Program 56's grid-tie-current effect remains unverified, and automatic load-aware regulation is not claimed.

## Prices and savings

PSEG's current-month supply price refreshes every six hours. The delivery table is verified for **2026**; automatic prices pause in a later year until the table is reviewed. Failed refreshes retain the last successful current-month price for at most 48 hours. Taxes, riders, discounts and alternate suppliers are not included. Fixed service charges are not avoidable by battery operation.

Savings are estimated avoided AC purchase minus charging purchases, grid-mode idle consumption and optional wear. All DC charging is conservatively treated as grid-sourced while grid is available, so solar charging can overstate costs. Missing intervals and outages are excluded. Initial stored energy has unknown historical cost; pre-installation periods are not backfilled. Nominal/reported capacity is never called measured capacity.

## Energy dashboard

Choose **Battery energy in/out (BMS bridge)** when your source supplies trustworthy cumulative counters. Otherwise use the manager's integrated energy sensors. Choose **Battery power (positive discharge)** for instantaneous net power. Both paths are DC-side measurements, not household AC delivery. Do not select both sets of counters for the same battery.

## Maintenance

HACS handles version updates. Preferences and accounting are stored by HA; dashboard and device entities install together. Download integration diagnostics before filing a [bug](https://github.com/spikked27/home-battery/issues). Back up HA before migration; removing old helpers is a separate operation, and existing historical entity IDs are not silently reassigned.

See [feature support](docs/support.md), [migration](docs/migration.md), [development](docs/development.md) and [changelog](CHANGELOG.md).
