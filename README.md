# Home Battery

History charts support hover, touch and keyboard inspection of recorded values and timestamps. Cell bars use fixed BMS protection limits from the selected cell sensors' `cell_protection_low_v` and `cell_protection_high_v` attributes. Those attributes must agree across the selected groups; the panel does not guess a chemistry or automatically enlarge voltage differences. This display metadata never changes BMS protections.

<img src="https://raw.githubusercontent.com/spikked27/home-battery/main/custom_components/home_battery/brand/logo.png" width="112" alt="Home Battery logo">

Local Home Assistant energy management for a critical-load battery system: readable controls, outage reserve, weather readiness, time-of-use scheduling and estimated net savings.

[![Tests](https://github.com/spikked27/home-battery/actions/workflows/tests.yml/badge.svg)](https://github.com/spikked27/home-battery/actions/workflows/tests.yml)
[![Open HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=spikked27&repository=home-battery&category=integration)

## What v1 includes

Under **Backup plan → What should this battery power?**, search for the load sensor by its friendly name (live **W/kW**, not energy in kWh), choose **7, 14, 30 or 90 days** of history, and select **Save & learn**. Fourteen days is the default. The learning card shows usable recorded hours as days, the requested window, expected daily demand and typical error from chronological prediction checks. Missing data is never filled with zero; less history than requested is clearly disclosed. Hourly long-term statistics must be available in Home Assistant Recorder. No cloud or AI subscription is used.

Learning refreshes every fifteen minutes with recency-weighted weekday/weekend patterns. Savings estimates use learned day-type profiles when available. Learned demand influences peak energy reservation only after coverage and prediction checks pass; otherwise the live-load rule remains active. This is not yet a full multi-day charging optimizer. Selecting a different meter pauses automatic scheduling and clears its prior heartbeat/commissioning for review; changing the history period alone preserves scheduling. Existing accounting history is retained, never reassigned to the new meter.

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

Before panel commissioning, Savings models recorded hourly demand from the selected history period, using learned weekday/weekend profiles when available. It requires all 24 hours and fresh telemetry. Charging is limited by the current inverter settings and assumes grid charging whenever SUB is selected, including reserve recovery outside cheap hours. Capacity, efficiency, idle use, reserve and model charge target are assumptions. Monthly and annual values are run rates at current prices, not forecasts or measured savings. Negative values mean the model costs more than buying the load directly from the grid.

After selecting and commissioning the connected critical-load meter, the main display switches to recorded operation with estimated tariff costs. This separate ledger starts prospectively; reference projections and legacy estimates are excluded. Changing the meter disables scheduling and clears its commissioning. Physical panel connection is not automatically detected.

Weather includes regional radar from RainViewer and OpenStreetMap, rendered with bundled Leaflet 1.9.4. Map tiles require internet and include provider attribution. The center uses HA location rounded to a tenth of a degree, with no home marker. Radar is informational; official alert freshness and the configured weather policy govern reserve advice. Provider availability is not guaranteed.

Charts use thin time-weighted mean lines with faint min/max ranges; missing intervals stay blank. Cell bars use the configured BMS low/high protection voltages as a fixed scale, so small differences are not visually exaggerated.

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

The Overview energy diagram follows the inverter's actual operating mode and fresh measured battery/solar power. Its inverter node shows measured AC output; the selected reference or connected-panel meter is displayed separately and drives planning. Battery DC power includes inverter consumption, so it need not match AC output. Utility availability alone does not activate the utility-supply arrow. Charging arrows point into the battery, and stale readings do not animate a path.

## Commission scheduling

### Savings preference and learning

Overview includes a **Next 24 hours** timeline: teal for expected charging, amber for battery use and blue for utility. It shows the next expected change, estimated battery percentage, outage reserve, and time in each mode. Hover, focus or tap a period for its local time, rate and reason; swipe horizontally on narrow screens. The preview uses the same scheduling policy with checked load forecasts or live-load fallback. It is an illustration, not a queued schedule: current prices/weather and charging limits are held constant, and future outages, solar generation, cell-voltage changes and transfer delays are not simulated. A separate copy of the charging guard models latch recovery at fifteen-minute resolution without changing the live guard. Live protections and measurements decide every actual action. Paused controls and unavailable inputs are shown explicitly; an inactive schedule is labeled preview-only.

Learning does not gate automatic scheduling. With a commissioned source transition and scheduling enabled, the live-load rules continue to protect reserve, charge during the configured cheap window and use battery when the price difference covers estimated losses and wear. Missing/limited history falls back to current and averaged measured load for peak reservation; stale telemetry, alarms, manual holds and unverified switching can still pause control. A tiny load can remain on utility because inverter overhead would erase savings.

Choose a **Savings preference** in Backup plan or the Home Assistant select:

| Preference | Backup headroom | Checked peak forecast |
| --- | --- | --- |
| Aggressive Savings | Requested backup time and configured margin | Expected demand; no extra prediction-error allowance |
| More Savings (default) | Requested backup time and configured margin | Expected demand plus one typical prediction error |
| More Outage Protection | Requested backup time and configured margin | Expected demand plus twice the typical prediction error |

The estimated backup energy is converted into a percentage, capped at 100%. There is one normal backup target: hours. Legacy percentage-floor values are ignored and the retired entity is removed on upgrade. Storm readiness still takes precedence. Extra headroom is a heuristic, not a statistical confidence guarantee or a promised runtime. Every profile uses the same history-coverage, validation, freshness, economic and protection checks. Until a checked forecast is available, Aggressive Savings and More Savings intentionally use the same live-load fallback; All profiles honor the same backup-hours target; their differences concern peak-demand prediction headroom. All profiles can use energy above reserve for economical peak shaving.

Existing `Save money` preferences become `More Savings`; `Backup first` becomes `More Outage Protection`. The latter now permits economical discharge above the calculated reserve instead of keeping utility selected all the time. Existing entity IDs, automatic enablement and user reserve/charging settings are preserved. Selecting another physical load sensor still requires review of that new source; changing only the learning period does not disable scheduling.

Scheduling starts **disabled**. Confirm that **SUB starts grid charging** and **SBU supplies the inverter output from battery**, then enable the source-transition confirmation and Automatic scheduling. Scheduling uses the selected load meter for reserve and price planning; it does not require that meter to be commissioned as the connected panel. When using a reference meter, reserve/runtime estimates reflect that reference demand and savings remain projections. Only mark the meter commissioned when it measures the inverter-fed critical loads. Selecting a different meter disables scheduling for review; turning off source-transition confirmation also disables scheduling.

**Commission the hardware recovery threshold:** in lithium/BMS mode, program 40 can hold the inverter on utility even after SBU is stored. Set its return-to-battery SOC below the SOC where the controller should resume discharge, while keeping program 39 and all BMS protections appropriate for the battery. A 20% hardware grid-transfer floor and 25% recovery threshold were configured in the site test, but a lower threshold alone did not produce repeatable SUB-to-SBU handovers. These values are not universal battery recommendations. Keep scheduling disabled until actual transfers are commissioned. The integration verifies a fresh actual Battery/Line mode after each source action and reports a fault if transfer does not occur. ACK/readback alone is insufficient.

Source actions coordinate two settings: SBU plus utility charging disabled for battery use; SUB plus SNU to allow grid charging. Charge-current caps are checked before permitting utility charging. The controller then verifies actual operating mode, allowing a 12-minute telemetry observation window after verified settings readback. Two captured transfers occurred approximately ten minutes after utility entry, while voltage was already above the stored return threshold; the exact firmware timer conditions remain unconfirmed. The service returns after settings readback so Home Assistant remains responsive. A pending transfer is shown as a normal waiting state, with actual source displayed separately. Pending observations, deadlines, manual holds and switching times survive restart; no commands are replayed. A restart during the two-setting write sequence pauses control for review instead of guessing how far it completed. A stored preference or a charging battery with no PV does not count as verified battery operation. BMS protections, MOSFETs, charge current, timers and output voltage settings are never changed by the scheduler. Manual controls pause scheduling for the configured hold. Failed/uncertain commands latch a fault and stop automatic writes until deliberately acknowledged with a ready bridge.

After reaching the reserve floor outside the low-price charging window, the planner keeps utility selected until the next charging window. This daily reserve hold persists across restart and prevents recharging at an expensive price merely to discharge that energy again. If SOC falls below the required reserve, utility charging can restore it; recovered reserve stays available for outages. Storm readiness and protection-recovery behavior still take precedence. The same reserve-session logic runs in the live controller, timeline and savings model. The five-minute source cooldown and separate five-point SOC / 50 mV utility-charge target hysteresis remain in place.

**One backup target, expressed in hours:** the planner estimates DC energy for the requested hours using the greater of live and rolling-average load, conversion losses, inverter overhead and the estimate margin. It divides that energy by configured battery capacity to derive the read-only outage-reserve percentage. Savings profiles do not multiply the requested hours. A storm can temporarily raise the percentage. For example, 2 hours at 300 W, 90% discharge efficiency, 45 W overhead, 20% allowance and 5.2 kWh capacity calculates approximately 17.5%. If the target exceeds available capacity, the reserve is capped at 100% and the planner keeps utility selected. Reported SOC and capacity are assumptions, so runtime is an estimate.

**Utility-charge guard:** charge target is enforced by disabling utility charging while leaving the output preference alone. An optional per-cell ceiling is configured in Advanced (default 0, disabled; choose for the actual cell chemistry). It is a supervisory soft limit, not a BMS protection threshold. Reaching either limit persists a latch; recharge requires five SOC points or 50 mV of recovery for the limits reached, plus three minutes of clear readings. Restart preserves latches and restarts the recovery observation. Battery/inverter alarms or missing telemetry also block charging. A manual hold or disabled schedule does not defeat charge inhibition. A failed inhibition is reported and requires deliberate command-fault acknowledgement rather than endless retries.

Scheduled grid hold need not charge: Save for peak, Hold reserve and Target reached use grid with utility charging disabled. Low-price charging, reserve recovery and storm/backup readiness permit charging only below the guard limits. A manual grid-and-charge action respects the same limits. The guard does not force a load transfer or operate BMS MOSFETs. It cannot stop PV charging. HA/MQTT downtime suspends this supervision and leaves the inverter's last setting in place; independent hardware/BMS protection remains necessary.

The optional Daly alarm decoder in `bridge/daly_alarm_status.py` exposes the exact eight-byte `0x98` payload, stable codes and sample timestamp as attributes on the existing alarm sensor. It fixes upstream duplicate high/low voltage labels. For isolated high-SOC or high cell/pack-voltage flags, recovery discharge is permitted only with a fresh explicit BMS discharge permission, the expected number of cell readings all at least 3.3 V and below the enabled cell ceiling, a 0–45 °C reading and a ready inverter. These are conservative recovery gates, not general operating limits. Charging remains blocked, the alarm stays visible, and the outage reserve is respected. Unknown/mixed faults or a BMS discharge block use available utility with charging disabled. No protection bits or MOSFET settings are overridden. This follows DALY overcharge recovery guidance: https://zh.dalybms.com/news/lithium-ion-battery-bms-when-does-overcharge-protection-trigger-how-to-recover/ . The bridge must attach discharge_mosfet and cell_count to each fresh alarm sample; old diagnostics fail closed. Never use this to clear/reset or override BMS protection.

Program 02 is combined solar + grid **battery-side DC charging amps**; program 11 is the grid contribution within that limit. They do not limit emergency AC battery output. The integration's charging ceiling never exceeds **30 A DC**. The AC supply budget is capped at **32 A**, representing an 80% planning allowance for a 40 A supply. That budget is not a verified hardware limiter. Program 56's grid-tie-current effect remains unverified, and automatic load-aware regulation is not claimed.

## Prices and savings

PSEG's current-month supply price refreshes every six hours. The delivery table is verified for **2026**; automatic prices pause in a later year until the table is reviewed. Failed refreshes retain the last successful current-month price for at most 48 hours. Taxes, riders, discounts and alternate suppliers are not included. Fixed service charges are not avoidable by battery operation.

New financial accounting waits for critical-load meter commissioning; existing historical estimates are retained. Savings are estimated avoided AC purchase minus charging purchases, grid-mode idle consumption and optional wear. All DC charging is conservatively treated as grid-sourced while grid is available, so solar charging can overstate costs. Missing intervals and outages are excluded. Initial stored energy has unknown historical cost; pre-installation periods are not backfilled. Nominal/reported capacity is never called measured capacity.

## Energy dashboard

Choose **Battery energy in/out (BMS bridge)** when your source supplies trustworthy cumulative counters. Otherwise use the manager's integrated energy sensors. Choose **Battery power (positive discharge)** for instantaneous net power. Both paths are DC-side measurements, not household AC delivery. Do not select both sets of counters for the same battery.

## Maintenance

HACS handles version updates. Preferences and accounting are stored by HA; dashboard and device entities install together. Download integration diagnostics before filing a [bug](https://github.com/spikked27/home-battery/issues). Back up HA before migration; removing old helpers is a separate operation, and existing historical entity IDs are not silently reassigned.

See [feature support](docs/support.md), [migration](docs/migration.md), [development](docs/development.md) and [changelog](CHANGELOG.md).

Outside the low-price charging window, small reserve fluctuations within the backup estimate allowance use utility without charging. Discretionary battery use still stops at the calculated reserve. Recovery charging is permitted only when estimated remaining backup falls below the requested hours, or storm readiness requires it. The allowance is extra planning headroom, not a second user reserve minimum.


## Cold-weather charging

In Backup plan, enable **Temperature-aware charging** to align needed charging with colder useful hours of the configured overnight window. The selected coldest battery probe drives charge permission; weather only helps choose timing. Daly minimum probes are discovered by the selected battery device's stable identity, including renamed entities. Other installations can choose **Coldest battery temperature** in integration options. If no minimum probe is available, the selected temperature source is used and shown explicitly.

The model reads seven days of hourly battery temperature and charging-power statistics in Celsius/W, then continues collecting live samples. It uses passive intervals with bounded gaps and checks its cooling-rate prediction against held-out observations. While history is insufficient or noisy, ordinary charging remains active. The planner does not credit speculative self-heating. It keeps a started overnight charge stable and begins earlier if cooling predicts a cold boundary or remaining charging time is tight. Completion times remain estimates.

**Prioritize cold-weather availability** permits needed charging before cheap hours only when a learned cold boundary is approaching. The default early-charge cost cap is USD 0.25 per local calendar day; zero disables paid advances. The measured cost/energy and model survive restart. Charge inhibition does not wait for source-switch cooldown. A paid advance is one stable attempt per upcoming overnight window; after it stops, falling SOC cannot re-arm repeated paid-charge pulses. Its marker survives restart. Unknown cost during a long interrupted early-charge interval suspends further paid advances for that day. This is a supervisory estimate, not a hardware spending guarantee; HA/MQTT/bridge availability remains required.

The default software charging floor is 8°C. Configure it above your BMS cutoff and for your actual cells/probe placement. Missing or cold battery temperatures inhibit utility charging. This cannot stop PV, heat an already-cold pack, override BMS protection, command an arbitrary discharge current, or force MOSFETs. No current limits or inverter/BMS protection settings are changed. No deliberate charge/discharge cycling is used for warmth. An appropriately controlled enclosure heater is needed if natural warming and scheduled charging are insufficient.

Overview and Weather show status, probe temperature, planned start and early-charge spending. Backup plan contains controls and model diagnostics. Observed temperature change during charging is an association, not a proven heating effect. Long-run savings projections exclude unpredictable weather-dependent advances; the recorded operation ledger includes actual charging costs.
