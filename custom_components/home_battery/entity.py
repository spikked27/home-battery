"""Device-linked entities sharing one coordinator."""
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, VERSION


class BatteryEntity(CoordinatorEntity):
    _attr_has_entity_name=True
    def __init__(self,coordinator,key,name):
        super().__init__(coordinator)
        self.key=key
        self._attr_unique_id=f"{coordinator.entry.entry_id}_{key}"
        self._attr_name=name
        self._attr_device_info={"identifiers":{(DOMAIN,coordinator.entry.unique_id)},
                               "name":coordinator.entry.title,"manufacturer":"Home Battery",
                               "model":"Local battery energy manager","sw_version":VERSION}

    @property
    def available(self):
        return True

    @property
    def extra_state_attributes(self):
        return self.coordinator.attributes.get(self.key,{})
