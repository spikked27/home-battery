"""UI setup with native entity selectors; no broker passwords stored here."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from .const import DOMAIN


def connection_schema(current):
    return vol.Schema({
        vol.Required("name",default=current.get("name","Home Battery")):str,
        vol.Required("mqtt_root",default=current.get("mqtt_root","hpvinv09/inverter")):str,
    })


def source_schema(current):
    fields = {}
    for key, device in [("soc_entity","battery"),("load_entity","power"),
                        ("charge_power_entity","power"),("discharge_power_entity","power"),
                        ("voltage_entity","voltage"),("current_entity","current"),
                        ("temperature_entity","temperature"),("remaining_ah_entity",None),
                        ("energy_in_entity","energy"),("energy_out_entity","energy"),
                        ("alarms_entity",None),("alert_entity",None)]:
        filt = {"domain":"sensor"}
        if device: filt["device_class"] = device
        required = key in {"soc_entity","load_entity","charge_power_entity","discharge_power_entity","alarms_entity"}
        marker = vol.Required if required else vol.Optional
        default = current.get(key,vol.UNDEFINED)
        fields[marker(key,default=default)] = selector.EntitySelector(selector.EntitySelectorConfig(filter=filt))
    fields[vol.Optional("weather_entity",default=current.get("weather_entity",vol.UNDEFINED))] = selector.EntitySelector(selector.EntitySelectorConfig(domain="weather"))
    fields[vol.Optional("cell_entities",default=current.get("cell_entities",[]))] = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor",device_class="voltage",multiple=True))
    fields[vol.Optional("bms_control_entities",default=current.get("bms_control_entities",[]))] = selector.EntitySelector(selector.EntitySelectorConfig(filter=[{"domain":d} for d in ("number","select","switch","button")],multiple=True))
    return vol.Schema(fields)


def validate_sources(hass,data):
    units={"soc_entity":{"%"},"load_entity":{"W","kW"},"charge_power_entity":{"W","kW"},"discharge_power_entity":{"W","kW"},"voltage_entity":{"V"},"current_entity":{"A"},"temperature_entity":{"°C","°F"},"remaining_ah_entity":{"Ah"},"energy_in_entity":{"kWh","Wh"},"energy_out_entity":{"kWh","Wh"}}
    errors = {}
    for key,expected in units.items():
        if not data.get(key): continue
        state = hass.states.get(data[key])
        if state is None or state.attributes.get("unit_of_measurement") not in expected or data[key].startswith(("sensor.home_battery_","sensor.critical_loads_")):
            errors[key]="invalid_source"
    if data.get("charge_power_entity") and data.get("charge_power_entity")==data.get("discharge_power_entity"):
        errors["discharge_power_entity"]="separate_directional_power"
    for entity in data.get("bms_control_entities",[]):
        if entity.split(".")[0] not in {"number","select","switch","button"} or "home_battery" in entity:
            errors["bms_control_entities"]="invalid_source"
    return errors


class HomeBatteryFlow(config_entries.ConfigFlow,domain=DOMAIN):
    VERSION=1
    def __init__(self):
        self.connection={}

    async def async_step_user(self,user_input=None):
        errors={}
        if user_input:
            root=user_input["mqtt_root"].strip("/")
            if not root or any(c in root for c in ("+","#","\0")):
                errors["mqtt_root"]="invalid_topic"
            else:
                await self.async_set_unique_id(root)
                self._abort_if_unique_id_configured()
                self.connection=dict(user_input,mqtt_root=root)
                return await self.async_step_sources()
        return self.async_show_form(step_id="user",data_schema=connection_schema(user_input or {}),errors=errors)

    async def async_step_sources(self,user_input=None):
        errors=validate_sources(self.hass,user_input) if user_input else {}
        if user_input is not None and not errors:
            return self.async_create_entry(title=self.connection["name"],data=self.connection|user_input)
        return self.async_show_form(step_id="sources",data_schema=source_schema(user_input or {}),errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return HomeBatteryOptions()


class HomeBatteryOptions(config_entries.OptionsFlow):
    async def async_step_init(self,user_input=None):
        current=dict(self.config_entry.data)|dict(self.config_entry.options)
        errors=validate_sources(self.hass,user_input) if user_input else {}
        if user_input is not None and not errors:
            return self.async_create_entry(title="",data=dict(self.config_entry.options)|user_input)
        return self.async_show_form(step_id="init",data_schema=source_schema(user_input or current),errors=errors)
