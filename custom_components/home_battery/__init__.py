"""Home Battery: local telemetry, human-readable controls and energy scheduling."""
from pathlib import Path
from hashlib import sha256
import voluptuous as vol
from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.helpers import entity_registry as er
from homeassistant.exceptions import HomeAssistantError
from .const import DEFAULTS, DOMAIN, PLATFORMS, VERSION
from .coordinator import BatteryCoordinator
from .discovery import suggested_sources


async def async_setup(hass,config):
    hass.data.setdefault(DOMAIN,{})
    await hass.http.async_register_static_paths([
        StaticPathConfig(f"/{DOMAIN}/frontend.js",str(Path(__file__).parent/"frontend.js"),False),
        StaticPathConfig(f"/{DOMAIN}/charts.css",str(Path(__file__).parent/"charts.css"),False),
        StaticPathConfig(f"/{DOMAIN}/brand",str(Path(__file__).parent/"brand"),True),
        StaticPathConfig(f"/{DOMAIN}/map",str(Path(__file__).parent/"map"),False)])
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
    suggested=suggested_sources(hass)
    history_sources={"load":coordinator.sources.get("load_entity"),"current":coordinator.sources.get("current_entity") or entities.get("current"),"spread":entities.get("cell_spread")}
    if coordinator.sources.get("cell_entities") and coordinator.sources.get("cell_entities")==suggested.get("cell_entities"):
        soc=registry.async_get(suggested.get("soc_entity",""))
        if soc:
            candidates=[e.entity_id for e in registry.entities.values() if e.device_id==soc.device_id and e.unique_id=="daly_bms_cell_delta" and not e.disabled_by]
            if len(candidates)==1: history_sources["spread"]=candidates[0]
    connection.send_result(msg["id"],{"data":coordinator.data,"attributes":coordinator.attributes,
                                    "settings":coordinator.settings,"entities":entities,
                                    "sources":{k:v for k,v in coordinator.sources.items() if k.endswith("_entity") or k in {"bms_control_entities","nws_alert_zone"}},
                                    "history_sources":history_sources,"alerts":coordinator.nws_alert_details,
                                    "radar_location":{"latitude":round(hass.config.latitude,1),"longitude":round(hass.config.longitude,1)},
                                    "forecast":coordinator.weather_forecast,"forecast_updated":coordinator.forecast_time,"version":VERSION})


async def async_setup_entry(hass,entry):
    coordinator=BatteryCoordinator(hass,entry)
    hass.data[DOMAIN][entry.entry_id]=coordinator
    try:
        await coordinator.async_start()
        await hass.config_entries.async_forward_entry_setups(entry,PLATFORMS)
        # Content-address the bundle so preview/stable updates cannot reuse stale UI.
        bundle_hash=await hass.async_add_executor_job(lambda:sha256((Path(__file__).parent/"frontend.js").read_bytes()).hexdigest()[:12])
        await panel_custom.async_register_panel(hass,
            frontend_url_path=f"home-battery-{entry.entry_id[:8]}",webcomponent_name="home-battery-panel",
            sidebar_title=entry.title,sidebar_icon="mdi:home-battery-outline",
            module_url=f"/{DOMAIN}/frontend.js?v={VERSION}-{bundle_hash}",config={"entry_id":entry.entry_id})
    except Exception:
        hass.data[DOMAIN].pop(entry.entry_id,None)
        await coordinator.async_close()
        raise
    entry.async_on_unload(entry.add_update_listener(async_options_updated))
    return True


async def async_options_updated(hass,entry):
    coordinator=hass.data[DOMAIN][entry.entry_id]
    # Entity edits apply live; source selection changes require a clean listener/ledger boundary.
    changed=any(coordinator.sources.get(k)!=v for k,v in entry.options.items() if k.endswith("_entity") or k in {"cell_entities","bms_control_entities","battery_heartbeat_topic","load_heartbeat_topic","nws_alert_zone"})
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
