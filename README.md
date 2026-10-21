# Home Battery

<img src="https://raw.githubusercontent.com/spikked27/home-battery/main/custom_components/home_battery/brand/logo.png" width="112" alt="Home Battery logo">

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
- Critical-load usage and cell-difference history, with 24-hour / 7-day / 30-day windows and existing bridge history where available.
- Fresh weather/forecast advisory, built-in NWS zone alerts with five-minute refresh and fifteen-minute expiry, manual storm override, and animated regional RainViewer radar.
- Persistent accounting, diagnostics, stable per-installation entity identities, and integration-owned configuration entities instead of dozens of helpers.

## Projections and recorded savings

Before panel commissioning, Savings models a repeated 24-hour reference-load profile from HA Recorder hourly mean power. It requires all 24 hours and fresh telemetry. Charging is limited by the current inverter settings and assumes grid charging whenever SUB is selected, including reserve recovery outside cheap hours. Capacity, efficiency, idle use, reserve and model charge target are assumptions. Monthly and annual values are run rates at current prices, not forecasts or measured savings. Negative values mean the model costs more than buying the load directly from the grid.

After selecting and commissioning the connected critical-load meter, the main display switches to recorded operation with estimated tariff costs. This separate ledger starts prospectively; reference projections and legacy estimates are excluded. Changing the meter disables scheduling and clears its commissioning. Physical panel connection is not automatically detected.

Weather includes regional radar from RainViewer and OpenStreetMap, rendered with bundled Leaflet 1.9.4. Map tiles require internet and include provider attribution. The center uses HA location rounded to a tenth of a degree, with no home marker. Radar is informational; official alert freshness and the configured weather policy govern reserve advice. Provider availability is not guaranteed.

Charts use thin time-weighted mean lines with faint min/max ranges; missing intervals stay blank. Cell bars share one labelled voltage scale, with a full-scale toggle to distinguish small differences from their absolute magnitude.

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
4. Review your detected bridge MQTT root (the prefix before `/status`, without wildcards), or enter it if the known retained discovery record is unavailable.
5. Review suggested Daly BMS and inverter sources. Detection uses stable MQTT unique IDs, so renamed entities still work; cells are sorted numerically in physical group order. A single weather entity is also suggested. Multiple/unknown devices stay unselected. Confirm the **live critical-load AC power meter in W/kW** measures your intended loads; the default detected inverter output can be replaced by your panel meter. Optional missing sources stay blank.
6. Supply explicit live MQTT heartbeat topics for BMS and load measurements when readings can stay constant. For the included bridges, use `daly_bms/state/pack_voltage` and `YOUR_INVERTER_ROOT/telemetry/output_power`. Heartbeats must be repeated numeric/timestamp messages, not retained availability flags. Without a heartbeat, source timestamps must refresh within 90 seconds.
7. Optionally enter your NWS forecast-zone/county code for built-in US severe alerts. This takes precedence over an external alert sensor and tracks actual successful fetches even when the count remains zero.
8. The Home Battery sidebar panel appears automatically. Review assumptions in Backup plan and Advanced.

Requires Home Assistant 2026.3 or newer for bundled integration/HACS brand assets. Source detection does not install bridges or guess usable battery capacity, alert location, or meter commissioning. Review capacity, backup needs and commissioning before enabling scheduling. Custom MQTT discovery prefixes fall back to manual root entry.

For a manual install, copy `custom_components/home_battery` into `/config/custom_components/` and restart. HACS custom-repository installation does not imply inclusion in HACS's default catalog.

## Commission scheduling

Scheduling starts **disabled**. Observe the recommendations first. Confirm that the selected meter measures the actual critical loads and that **SUB starts grid charging** and **SBU supplies those loads from battery** on your inverter. Enable the two commissioning switches, then Automatic scheduling.

**Commission the hardware recovery threshold:** in lithium/BMS mode, program 40 can hold the inverter on utility even after SBU is stored. Set its return-to-battery SOC below the SOC where the controller should resume discharge, while keeping program 39 and all BMS protections appropriate for the battery. The tested site uses a 20% hardware grid-transfer floor and a 25% recovery threshold; this is a site policy, not a universal battery recommendation. The integration verifies a fresh actual Battery/Line mode after each source action and reports a fault if transfer does not occur. ACK/readback alone is insufficient.

Source actions coordinate two settings: SBU plus utility charging disabled for battery use; SUB plus SNU to allow grid charging. Charge-current caps are checked before permitting utility charging. The controller then verifies actual operating mode, allowing up to 150 seconds for transition/readback. A stored preference or a charging battery with no PV does not count as verified battery operation. BMS protections, MOSFETs, charge current, timers and output voltage settings are never changed by the scheduler. Manual controls pause scheduling for the configured hold. Failed/uncertain commands latch a fault and stop automatic writes until deliberately acknowledged with a ready bridge.

After reaching the reserve floor, the planner requires recovery to five SOC points above that floor (capped at the charge target) before returning from SUB to SBU. This hysteresis and the five-minute cooldown avoid rapid switching near the reserve boundary.

**Backup hours and percentage floor work together:** the planner estimates DC energy for the requested hours using observed load, efficiency, inverter overhead and margin. It keeps the larger of that percentage and the Advanced minimum reserve. A storm can raise it further. For example, a 2-hour estimate of 12% with a 20% floor keeps 20%; an estimate of 35% keeps 35%. Reported SOC and configured capacity are assumptions, so runtime is an estimate.

**Charge target is advisory:** a neutral grid-without-charging state is not verified for this firmware. Reaching the target keeps SUB; it does not promise that charging stops at that SOC. Hardware/BMS charge limits still determine termination. This is an energy-management system, not a protective controller; HA downtime suspends scheduling and leaves the inverter's current setting in place.

## Current limits are different quantities

Program 02 is combined solar + grid **battery-side DC charging amps**; program 11 is the grid contribution within that limit. They do not limit emergency AC battery output. The integration's charging ceiling never exceeds **30 A DC**. The AC supply budget is capped at **32 A**, representing an 80% planning allowance for a 40 A supply. That budget is not a verified hardware limiter. Program 56's grid-tie-current effect remains unverified, and automatic load-aware regulation is not claimed.

## Prices and savings

PSEG's current-month supply price refreshes every six hours. The delivery table is verified for **2026**; automatic prices pause in a later year until the table is reviewed. Failed refreshes retain the last successful current-month price for at most 48 hours. Taxes, riders, discounts and alternate suppliers are not included. Fixed service charges are not avoidable by battery operation.

New financial accounting waits for critical-load meter commissioning; existing historical estimates are retained. Savings are estimated avoided AC purchase minus charging purchases, grid-mode idle consumption and optional wear. All DC charging is conservatively treated as grid-sourced while grid is available, so solar charging can overstate costs. Missing intervals and outages are excluded. Initial stored energy has unknown historical cost; pre-installation periods are not backfilled. Nominal/reported capacity is never called measured capacity.

## Energy dashboard

Choose **Battery energy in/out (BMS bridge)** when your source supplies trustworthy cumulative counters. Otherwise use the manager's integrated energy sensors. Choose **Battery power (positive discharge)** for instantaneous net power. Both paths are DC-side measurements, not household AC delivery. Do not select both sets of counters for the same battery.

## Maintenance

HACS handles version updates. Preferences and accounting are stored by HA; dashboard and device entities install together. Download integration diagnostics before filing a [bug](https://github.com/spikked27/home-battery/issues). Back up HA before migration; removing old helpers is a separate operation, and existing historical entity IDs are not silently reassigned.

See [feature support](docs/support.md), [migration](docs/migration.md), [development](docs/development.md) and [changelog](CHANGELOG.md).
