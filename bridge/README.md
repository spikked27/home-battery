# Optional HPVINV09 Pi bridge

The MQTT integration requires a bridge. This directory contains the established dedicated RS232 bridge, generalized to environment-based port/root paths. It is a separate Linux process, not loaded by Home Assistant or installed by HACS. Existing working installations do not need to replace their bridge.

Supported profile: HPVINV09 firmware `0010.03 20260202`, 2400 baud 8N1, no flow control, CR framing for H reads and established CRC framing for whitelisted writes. Unknown commands are rejected. The serial worker checks ownership before opening, uses exclusive access, spaces queries by at least two seconds, audits all traffic and verifies complete settings readback after writes.

The 2026.10.31.1 bridge adds captured ACK/full-readback support for 5% SOC shutdown, 10% utility-transfer SOC and 44 V utility-transfer voltage. These are selectable values, not automatically applied defaults or recommendations for every battery. The low-SOC/voltage physical cutoff precedence remains uncommissioned; keep independent BMS protections and a battery-specific reserve. Coordination of Daly SOC alarms is a separate maintenance operation, not performed by this bridge.

Serial delivery uses a bounded complete write followed by a bounded CR-framed reply, without repeated `tcdrain` modem-status requests on FTDI adapters. Disconnects still fault the current exchange; uncertain writes are not retried.

## Foreground setup

Do not run alongside SolarAssistant or another owner of the serial port. Configure device permissions for the dedicated bridge account; do not grant general passwordless sudo. On Linux with Python 3.10+, `fuser` and `mountpoint` already installed:

```sh
python3 -m venv .venv
.venv/bin/pip install -r bridge/requirements.txt
mkdir -p "$HOME/home-battery-data"
export INVERTER_LAB="$HOME/home-battery-data"
export INVERTER_PORT="/dev/serial/by-id/YOUR_ADAPTER"
export MQTT_HOST="YOUR_BROKER"
export MQTT_PORT="1883"
export MQTT_ROOT="hpvinv09/inverter"
# Supply MQTT_USERNAME and MQTT_PASSWORD through your private environment.
# Keep credentials out of shell history, Git and diagnostic submissions.
.venv/bin/python bridge/standalone.py
```

Use Ctrl+C to stop. No installer automatically enables a service or modifies SolarAssistant. Audit/state files stay in `INVERTER_LAB`. A prior uncertain transaction creates a write-fault latch; inspect its evidence before manually clearing it. Never erase it just to force a retry.

The current bridge MQTT client is restricted to a trusted local broker. It does not implement TLS options; use a private network and scoped broker credentials. The bridge does not publish arbitrary command controls, BMS protection changes or firmware writes.

Default MQTT discovery identifiers are for one inverter per broker. To deploy several, assign distinct discovery identifiers/client IDs in the bridge as well as distinct MQTT roots; multi-inverter bridge deployment is not claimed by v1.

Runtime environment credentials are deliberately absent from this repository. No captured private installation logs are bundled.
