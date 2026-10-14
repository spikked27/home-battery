"""Downloadable diagnostics without broker credentials, entity names or locations."""
from homeassistant.components.diagnostics import async_redact_data
from .const import DOMAIN, VERSION

async def async_get_config_entry_diagnostics(hass,entry):
    coordinator=hass.data[DOMAIN][entry.entry_id]
    return {"version":VERSION,"settings":coordinator.settings,"measurements":coordinator.data,
            "decision":coordinator.attributes.get("plan"),"accounting":coordinator.ledger,
            "telemetry_keys":sorted(coordinator.topics),"source_count":len(coordinator.sources.get("cell_entities",[])),
            "command_fault":bool(coordinator.command_error)}
