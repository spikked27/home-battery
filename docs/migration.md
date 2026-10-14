# Migrate an existing installation

1. Back up Home Assistant and the existing Pi bridge.
2. Install Home Battery alongside existing MQTT discovery entities. Do not add another serial owner.
3. Select the existing source entities and MQTT root. Leave automatic scheduling disabled.
4. Copy reserve/capacity/efficiency preferences into the integration's configuration entities.
5. Compare telemetry, source labels, highest/lowest groups, rates and recommendations with the prior dashboard.
6. Disable any older scheduler before enabling the integration scheduler. Never let two schedulers write competing preferences.
7. Update Energy dashboard selectors only after the new counters have been verified. Old cumulative counters and history remain intact.
8. Retire old helpers/packages only after all automations and dashboards referencing them have been migrated. This integration does not delete them automatically.

Rollback: disable Automatic scheduling, unload/remove Home Battery, and resume the previous dashboard/package. The Pi bridges and inverter settings are not reset by removal. The integration does not silently import another system's monetary history or claim that its new unique IDs preserve old statistics.
