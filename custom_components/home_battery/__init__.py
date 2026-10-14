"""Home Battery: local telemetry, human-readable controls and energy scheduling."""
from pathlib import Path
import voluptuous as vol
from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.helpers import entity_registry as er
from homeassistant.exceptions import HomeAssistantError
from .const import DEFAULTS, DOMAIN, PLATFORMS, VERSION
from .coordinator import BatteryCoordinator


async def async_setup(hass,config):
    hass.data.setdefault(DOMAIN,{})
    await hass.http.async_register_static_paths([StaticPathConfig(f"/{DOMAIN}/frontend.js",str(Path(__file__).parent/"frontend.js"),False)])
    websocket_api.async_register_command(hass,panel_state)
    return True


@websocket_api.websocket_command({vol.Required("type"):"home_battery/panel",vol.Required("entry_id"):str})
@websocket_api.async_response
async def panel_state(hass,connection,msg):
    coordinator=hass.data.get(DOMAIN,{}).get(msg["entry_id"])
    if not coordinator:
        connection.send_error(msg["id"],"not_found","Integration entry unavailable");return
    registry=er.async_get(hass)
    entities={entry.unique_id.removeprefix(coordinator.entry.entry_id+"_"):entry.entity_id
              for entry in er.async_entries_for_config_entry(registry,coordinator.entry.entry_id)}
    connection.send_result(msg["id"],{"data":coordinator.data,"attributes":coordinator.attributes,
                                    "settings":coordinator.settings,"entities":entities,
                                    "sources":{k:v for k,v in coordinator.sources.items() if k.endswith("_entity") or k=="bms_control_entities"},
                                    "forecast":coordinator.weather_forecast,"version":VERSION})


async def async_setup_entry(hass,entry):
    coordinator=BatteryCoordinator(hass,entry)
    hass.data[DOMAIN][entry.entry_id]=coordinator
    try:
        await coordinator.async_start()
        await hass.config_entries.async_forward_entry_setups(entry,PLATFORMS)
        await panel_custom.async_register_panel(hass,
            frontend_url_path=f"home-battery-{entry.entry_id[:8]}",webcomponent_name="home-battery-panel",
            sidebar_title=entry.title,sidebar_icon="mdi:home-battery-outline",
            module_url=f"/{DOMAIN}/frontend.js?v={VERSION}",config={"entry_id":entry.entry_id})
    except Exception:
        hass.data[DOMAIN].pop(entry.entry_id,None)
        await coordinator.async_close()
        raise
    entry.async_on_unload(entry.add_update_listener(async_options_updated))
    return True


async def async_options_updated(hass,entry):
    coordinator=hass.data[DOMAIN][entry.entry_id]
    # Entity edits apply live; source selection changes require a clean listener/ledger boundary.
    changed=any(coordinator.sources.get(k)!=v for k,v in entry.options.items() if k.endswith("_entity") or k in {"cell_entities","bms_control_entities","battery_heartbeat_topic","load_heartbeat_topic"})
    if changed:
        await hass.config_entries.async_reload(entry.entry_id)
    else:
        coordinator.settings.update({k:v for k,v in entry.options.items() if k in DEFAULTS})
        coordinator.previous=None
        coordinator.recompute()


async def async_unload_entry(hass,entry):
    if not await hass.config_entries.async_unload_platforms(entry,PLATFORMS): return False
    coordinator=hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.async_close()
    frontend.async_remove_panel(hass,f"home-battery-{entry.entry_id[:8]}")
    return True
