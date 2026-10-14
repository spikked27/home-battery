"""Suggest known bridge sources by stable identities, never by display names."""
import asyncio
import json
import re
from homeassistant.components import mqtt
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er

DALY_FIELDS={"soc_entity":"soc","charge_power_entity":"battery_charging_power",
    "discharge_power_entity":"battery_discharging_power","voltage_entity":"pack_voltage",
    "current_entity":"current","temperature_entity":"highest_temperature",
    "remaining_ah_entity":"remaining_capacity","energy_in_entity":"battery_energy_in",
    "energy_out_entity":"battery_energy_out","alarms_entity":"alarms"}
CONTROL_IDS={"charge_mosfet","discharge_mosfet","set_board_number","set_inverter_protocol","disable_sleep","restart"}

def suggested_sources(hass):
    """Only preselect a single unambiguous bridge device; users review every source."""
    entries=[e for e in er.async_get(hass).entities.values() if e.platform=="mqtt" and not e.disabled_by]
    devices={e.device_id for e in entries if e.unique_id=="daly_bms_soc" and e.device_id}
    result={}
    if len(devices)==1:
        device=next(iter(devices))
        by_id={e.unique_id:e.entity_id for e in entries if e.device_id==device}
        result.update({key:by_id["daly_bms_"+suffix] for key,suffix in DALY_FIELDS.items() if "daly_bms_"+suffix in by_id})
        cells=[]
        for unique,entity in by_id.items():
            match=re.fullmatch(r"daly_bms_cell_(\d+)_voltage",unique)
            if match: cells.append((int(match[1]),entity))
        result["cell_entities"]=[entity for _,entity in sorted(cells)]
        result["bms_control_entities"]=[by_id["daly_bms_"+key] for key in sorted(CONTROL_IDS) if "daly_bms_"+key in by_id]
        result["battery_heartbeat_topic"]="daly_bms/state/pack_voltage"
    loads=[e.entity_id for e in entries if e.unique_id=="hpvinv09_telemetry_output_power"]
    if len(loads)==1: result["load_entity"]=loads[0]
    weather=hass.states.async_entity_ids("weather")
    if len(weather)==1: result["weather_entity"]=weather[0]
    return result

async def detected_root(hass):
    """Read one known retained HA discovery record; no serial access or publishing."""
    if not mqtt.is_connected(hass): return None
    future=hass.loop.create_future()
    @callback
    def received(msg):
        try:
            data=json.loads(msg.payload)
            topic=data.get("state_topic",data.get("stat_t",""))
            if topic.endswith("/telemetry/output_power") and not any(c in topic for c in ("+","#","\0")):
                if not future.done(): future.set_result(topic.removesuffix("/telemetry/output_power"))
        except (ValueError,TypeError,AttributeError): pass
    unsubscribe=await mqtt.async_subscribe(hass,"homeassistant/sensor/hpvinv09/telemetry_output_power/config",received)
    try:
        return await asyncio.wait_for(future,3)
    except TimeoutError: return None
    finally: unsubscribe()
