"""Operational availability and weather advice."""
from homeassistant.components.binary_sensor import BinarySensorEntity
from .const import DOMAIN
from .entity import BatteryEntity

async def async_setup_entry(hass,entry,async_add_entities):
    coordinator=hass.data[DOMAIN][entry.entry_id]
    async_add_entities(BatteryBinary(coordinator,key,name) for key,name in
                       {"fresh":"Telemetry fresh","healthy":"Battery and bridge ready","storm":"Storm reserve advised"}.items())

class BatteryBinary(BatteryEntity,BinarySensorEntity):
    @property
    def is_on(self):
        return bool(self.coordinator.data.get(self.key))
