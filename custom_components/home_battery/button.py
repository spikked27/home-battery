"""Two verified source actions, manual hold and deliberate fault acknowledgement."""
import time
from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN
from .entity import BatteryEntity

async def async_setup_entry(hass,entry,async_add_entities):
    async_add_entities(BatteryButton(hass.data[DOMAIN][entry.entry_id],key,name) for key,name in
                       {"use_battery":"Use battery now","use_grid":"Use grid and charge",
                        "resume_schedule":"Resume schedule after manual hold","acknowledge_fault":"Acknowledge command fault"}.items())

class BatteryButton(BatteryEntity,ButtonEntity):
    async def async_press(self):
        if self.key in {"use_battery","use_grid"}:
            await self.coordinator.async_source("SBU" if self.key=="use_battery" else "SUB")
        elif self.key=="resume_schedule":
            self.coordinator.hold_until=0;self.coordinator.save();self.coordinator.recompute()
        else:
            if not self.coordinator.fresh_topic("status") or self.coordinator.topics.get("status",{}).get("status")!="ready":
                raise HomeAssistantError("Bridge must be ready before acknowledging a command fault")
            self.coordinator.command_error=None;self.coordinator.save();self.coordinator.recompute()
