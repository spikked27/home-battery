"""Explicit commissioning, automation enablement and storm override."""
from homeassistant.components.switch import SwitchEntity
from .const import DOMAIN, SWITCHES
from .entity import BatteryEntity

async def async_setup_entry(hass,entry,async_add_entities):
    async_add_entities(BatterySwitch(hass.data[DOMAIN][entry.entry_id],key,name) for key,name in SWITCHES.items())

class BatterySwitch(BatteryEntity,SwitchEntity):
    _attr_entity_category="config"
    @property
    def is_on(self): return bool(self.coordinator.settings[self.key])
    async def async_turn_on(self,**kwargs): await self.coordinator.async_setting(self.key,True)
    async def async_turn_off(self,**kwargs): await self.coordinator.async_setting(self.key,False)
