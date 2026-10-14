"""Measurements, monetary statistics and honest confidence metadata."""
from homeassistant.components.sensor import SensorEntity
from .const import DOMAIN
from .entity import BatteryEntity

SENSORS={
 "soc":("Battery state of charge","%","battery","measurement"),
 "load_w":("Critical-load power","W","power","measurement"),
 "charge_w":("Battery charging power","W","power","measurement"),
 "discharge_w":("Battery discharging power","W","power","measurement"),
 "battery_power":("Battery power (positive discharge)","W","power","measurement"),
 "voltage":("Battery voltage","V","voltage","measurement"),
 "current":("Battery current (positive charge)","A","current","measurement"),
 "temperature":("Battery temperature","°C","temperature","measurement"),
 "remaining_ah":("BMS remaining capacity","Ah",None,"measurement"),
 "energy_in":("Battery energy in (BMS bridge)","kWh","energy","total_increasing"),
 "energy_out":("Battery energy out (BMS bridge)","kWh","energy","total_increasing"),
 "integrated_energy_in":("Battery energy charged (manager)","kWh","energy","total_increasing"),
 "integrated_energy_out":("Battery energy discharged (manager)","kWh","energy","total_increasing"),
 "grid_voltage":("Utility voltage","V","voltage","measurement"),
 "highest_cell":("Highest cell","V","voltage","measurement"),
 "lowest_cell":("Lowest cell","V","voltage","measurement"),
 "cell_spread":("Cell voltage difference","V","voltage","measurement"),
 "reserve_soc":("Recommended outage reserve","%",None,"measurement"),
 "runtime_hours":("Estimated outage runtime","h","duration","measurement"),
 "economic_margin":("Estimated savings margin","USD/kWh",None,"measurement"),
 "current_price":("Electricity price now","USD/kWh",None,"measurement"),
 "overnight_price":("Low-price charging cost","USD/kWh",None,"measurement"),
 "estimated_savings_total":("Estimated net savings total","USD","monetary","total"),
 "savings_day":("Estimated savings today","USD","monetary",None),
 "savings_month":("Estimated savings this month","USD","monetary",None),
 "savings_year":("Estimated savings this year","USD","monetary",None),
 "plan":("Recommended action",None,None,None),"reason":("Decision explanation",None,None,None),
 "tariff":("Electricity price window",None,None,None),"mode":("Actual power source",None,None,None),
 "weather_mode":("Weather reserve mode",None,None,None),"price_status":("Price source",None,None,None),
 "scheduler_status":("Scheduler status",None,None,None),"alarms":("Battery alarms",None,None,None),
 "bridge_status":("Bridge status",None,None,None),"command_result":("Last command result",None,None,None),
 "inverter_status_code":("Raw inverter status code",None,None,None),
}


async def async_setup_entry(hass,entry,async_add_entities):
    async_add_entities(BatterySensor(hass.data[DOMAIN][entry.entry_id],key,*value) for key,value in SENSORS.items())


class BatterySensor(BatteryEntity,SensorEntity):
    def __init__(self,coordinator,key,name,unit,device_class,state_class):
        super().__init__(coordinator,key,name)
        self._attr_native_unit_of_measurement=unit
        self._attr_device_class=device_class
        self._attr_state_class=state_class
        if key in {"bridge_status","command_result","price_status"}: self._attr_entity_category="diagnostic"
        if unit: self._attr_suggested_display_precision=3 if device_class=="voltage" and "cell" in key else 2

    @property
    def native_value(self):
        return self.coordinator.data.get(self.key)

    @property
    def available(self):
        return self.native_value is not None
