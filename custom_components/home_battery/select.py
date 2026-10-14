"""All 25 established inverter controls and local strategy selections."""
import json
from pathlib import Path
from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN, SELECTS
from .entity import BatteryEntity

CATALOG=json.loads((Path(__file__).parent/"catalog.json").read_text())

async def async_setup_entry(hass,entry,async_add_entities):
    coordinator=hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BatterySelect(coordinator,key,key.replace("_"," ").title()) for key in SELECTS]+
                       [InverterSelect(coordinator,key,meta["name"]) for key,meta in CATALOG.items()])

class BatterySelect(BatteryEntity,SelectEntity):
    _attr_entity_category=EntityCategory.CONFIG
    @property
    def options(self): return SELECTS[self.key]
    @property
    def current_option(self): return self.coordinator.settings[self.key]
    async def async_select_option(self,option):
        if option not in self.options: raise HomeAssistantError("Unknown strategy")
        await self.coordinator.async_setting(self.key,option)

class InverterSelect(BatteryEntity,SelectEntity):
    _attr_entity_category=EntityCategory.CONFIG
    @property
    def options(self):
        value=self.coordinator.topics.get(f"control/{self.key}/attributes",{}).get("allowed_values",[])
        if self.key in {"utility_charge_current","total_charge_current"}:
            value=[v for v in value if float(v.split()[0])<=min(30,self.coordinator.settings["charge_cap_a"])]
        return value
    @property
    def current_option(self): return self.coordinator.topics.get(f"control/{self.key}/state")
    @property
    def available(self):
        return (self.coordinator.fresh_topic("status") and self.coordinator.topics.get("status",{}).get("status") in {"ready","write_in_progress"}
                and bool(self.options) and self.current_option is not None)
    @property
    def extra_state_attributes(self):
        return CATALOG[self.key]|self.coordinator.topics.get(f"control/{self.key}/attributes",{})
    async def async_select_option(self,option):
        if option not in self.options: raise HomeAssistantError("Value outside bridge range or charging ceiling")
        await self.coordinator.async_control(self.key,option)
