# Compatible bridge contract

Use a dedicated local bridge that owns the RS232 port exclusively. SolarAssistant and another serial process must not own the same port. HACS installs the HA integration; it does not deploy a Pi service or install serial dependencies.

Given configured MQTT root `R`:

| Topic | Payload |
|---|---|
| `R/status` | JSON: `status` (`ready`, `write_in_progress`, `unavailable`), `fault`, timestamp |
| `R/raw_readings` | JSON including `HSTS`: `ascii`, `age_seconds`; HSTS second token begins L=Line or B=Battery |
| `R/telemetry/grid_voltage` | Numeric volts |
| `R/control/NAME/attributes` | JSON: `allowed_values`, `verified_values`, description, manual_program, confidence |
| `R/control/NAME/state` | Confirmed user-facing value (e.g. `SUB`, `SBU`, `5 A`) |
| `R/control/NAME/set` | Non-retained QoS 0 user-facing value, accepted only through bridge whitelist |
| `R/last_result` | JSON: control NAME, status `verified`/`verified_no_change` or failure, ISO timestamp |

Status/raw/grid messages must be emitted periodically. Retained messages can populate display/configuration but cannot establish live telemetry or confirm a write. Commands must be single-flight, have a finite timeout, perform readback, and never replay retained requests.

The v1 adapter targets the previously developed HPVINV09 bridge contract, not arbitrary Voltronic firmware. The complete user-visible catalog is `custom_components/home_battery/catalog.json`. Existing Daly telemetry/control integrations remain independent and can supply source entities.

No MQTT broker credentials are duplicated in Home Battery. It uses Home Assistant's configured broker connection.
