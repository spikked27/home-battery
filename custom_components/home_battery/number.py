"""Planning preferences belong to the integration rather than scattered helpers."""
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN, NUMBERS
from .entity import BatteryEntity

async def async_setup_entry(hass,entry,async_add_entities):
    coordinator=hass.data[DOMAIN][entry.entry_id]
    async_add_entities(BatteryNumber(coordinator,key,*value) for key,value in NUMBERS.items())

class BatteryNumber(BatteryEntity,NumberEntity):
    _attr_entity_category=EntityCategory.CONFIG
    _attr_mode=NumberMode.BOX
    def __init__(self,coordinator,key,name,minimum,maximum,step,unit):
        super().__init__(coordinator,key,name)
        self._attr_native_min_value=minimum;self._attr_native_max_value=maximum
        self._attr_native_step=step;self._attr_native_unit_of_measurement=unit

    @property
    def native_value(self):
        return self.coordinator.settings[self.key]

    async def async_set_native_value(self,value):
        if not self.native_min_value<=value<=self.native_max_value:
            raise HomeAssistantError("Setting outside supported range")
        proposed=self.coordinator.settings|{self.key:value}
        if proposed["minimum_reserve"]>proposed["charge_target"] or proposed["peak_start"]>=proposed["peak_end"] or proposed["charge_start"]==proposed["charge_end"]:
            raise HomeAssistantError("Reserve, charging or peak-window settings conflict")
        await self.coordinator.async_setting(self.key,value)
