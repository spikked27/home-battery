"""Local MQTT transport, fresh telemetry, verified writes and persistent accounting."""
import asyncio
from collections import deque
from dataclasses import asdict
from datetime import timedelta
import json
import logging
import re
import time
from zoneinfo import ZoneInfo

from homeassistant.components import mqtt
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import DEFAULTS, DOMAIN, PSEG_URL
from .policy import cell_extremes, make_plan, money_rates, numeric, pseg_rates, price_window

LOGGER=logging.getLogger(__name__)


class BatteryCoordinator(DataUpdateCoordinator):
    def __init__(self,hass,entry):
        super().__init__(hass,LOGGER,name=entry.title,config_entry=entry)
        self.entry=entry
        self.settings={key:entry.options.get(key,value) for key,value in DEFAULTS.items()}
        self.sources=dict(entry.data)|dict(entry.options)
        self.data={}
        self.attributes={}
        self.topics={}
        self.received={}
        self.lock=asyncio.Lock()
        self.pending=None
        self.pending_key=None
        self.pending_value=None
        self.command_time=0
        self.command_error=None
        self.hold_until=0
        self.last_switch=0
        self.average=deque(maxlen=2880)
        self.store=Store(hass,1,f"{DOMAIN}.{entry.entry_id}")
        self.ledger={"avoided":0.,"charging":0.,"wear":0.,"energy_in":0.,"energy_out":0.,"periods":{},"tracked_seconds":0.}
        self.previous=None
        self.last_tick=0
        self.last_fetch=0
        self.supply=None
        self.rate_month=None
        self.weather_forecast=[]
        self.forecast_time=0
        self.stopped=False
        self.start_time=time.time()

    async def async_start(self):
        saved=await self.store.async_load()
        if saved:
            self.ledger.update(saved.get("ledger",{}))
            self.hold_until=saved.get("hold_until",0)
            self.command_error=saved.get("command_error")
        if not await mqtt.async_wait_for_mqtt_client(self.hass):
            raise HomeAssistantError("Configure the Home Assistant MQTT integration first")
        unsub=await mqtt.async_subscribe(self.hass,self.sources["mqtt_root"]+"/#",self._message,qos=0)
        self.entry.async_on_unload(unsub)
        self.entry.async_on_unload(async_track_time_interval(self.hass,self.async_tick,timedelta(seconds=30)))
        await self.async_tick()

    @callback
    def _message(self,msg):
        root=self.sources["mqtt_root"]+"/"
        key=msg.topic[len(root):]
        if len(msg.payload)>200000: return
        try:
            payload=json.loads(msg.payload) if key in {"status","raw_readings","last_result"} or key.endswith("/attributes") else msg.payload
        except (ValueError,TypeError):
            return
        if key in {"status","raw_readings","last_result"} or key.endswith("/attributes"):
            if not isinstance(payload,dict): return
        old=self.topics.get(key)
        self.topics[key]=payload
        # Retained values populate controls but cannot establish current telemetry or confirm writes.
        if not msg.retain: self.received[key]=time.time()
        if key=="control/output_priority/state" and old is not None and old!=payload and self.pending_key!="output_priority":
            self.hold_until=time.time()+self.settings["manual_override_minutes"]*60
            self.save()
        if key=="last_result" and not msg.retain and self.pending and not self.pending.done():
            stamp=dt_util.parse_datetime(payload.get("timestamp","")) if isinstance(payload,dict) else None
            if (isinstance(payload,dict) and payload.get("control")==self.pending_key and stamp
                and stamp.timestamp()>=self.command_time):
                if payload.get("status") in {"verified","verified_no_change"}:
                    self.pending.set_result(payload)
                elif payload.get("status") not in {"pending"}:
                    self.pending.set_exception(HomeAssistantError(str(payload.get("error",payload.get("status")))))
        self.recompute()

    def fresh_topic(self,key,age=60):
        return 0<=time.time()-self.received.get(key,0)<age

    def entity_number(self,key,units=None):
        state=self.hass.states.get(self.sources.get(key,""))
        if not state or state.state in {"unknown","unavailable"}: return None
        stamp=getattr(state,"last_reported",state.last_updated)
        if time.time()-stamp.timestamp()>self.settings["freshness_seconds"]: return None
        unit=state.attributes.get("unit_of_measurement")
        if units and unit not in units: return None
        value=numeric(state.state)
        if value is not None and unit=="kW": value*=1000
        if value is not None and unit=="Wh": value/=1000
        if value is not None and unit=="°F": value=(value-32)*5/9
        return value

    def measurements(self):
        d={key:self.entity_number(source,unit) for key,source,unit in [
            ("soc","soc_entity",{"%"}),("load_w","load_entity",{"W","kW"}),
            ("charge_w","charge_power_entity",{"W","kW"}),("discharge_w","discharge_power_entity",{"W","kW"}),
            ("voltage","voltage_entity",{"V"}),("current","current_entity",{"A"}),
            ("temperature","temperature_entity",{"°C","°F"}),("remaining_ah","remaining_ah_entity",{"Ah"}),
            ("energy_in","energy_in_entity",{"kWh","Wh"}),("energy_out","energy_out_entity",{"kWh","Wh"})]}
        raw=self.topics.get("raw_readings",{})
        mode=raw.get("HSTS",{}).get("ascii","") if isinstance(raw,dict) else ""
        tokens=mode.lstrip("(").split()
        d["mode"]={"L":"Line","B":"Battery"}.get(tokens[1][0] if len(tokens)>1 and tokens[1] else "","Unknown")
        d["inverter_status_code"]=tokens[0] if tokens else "Unknown"
        d["grid_voltage"]=numeric(self.topics.get("telemetry/grid_voltage")) if self.fresh_topic("telemetry/grid_voltage") else None
        alarms=self.hass.states.get(self.sources.get("alarms_entity",""))
        d["alarms"]=alarms.state if alarms else "unavailable"
        alarm_fresh=alarms and time.time()-getattr(alarms,"last_reported",alarms.last_updated).timestamp()<self.settings["freshness_seconds"]
        status=self.topics.get("status",{})
        d["healthy"]=bool(alarm_fresh and d["alarms"].lower() in {"no alarms","none","ok","0","off"}
                          and isinstance(status,dict) and status.get("status") in {"ready","write_in_progress"}
                          and not status.get("fault") and not self.command_error and d["inverter_status_code"]=="00")
        d["fresh"]=bool(self.fresh_topic("status") and self.fresh_topic("raw_readings")
                        and isinstance(raw,dict) and 0<=raw.get("HSTS",{}).get("age_seconds",999)<45
                        and d["mode"] in {"Line","Battery"} and all(d[k] is not None for k in ("soc","load_w","charge_w","discharge_w","grid_voltage")))
        if any(d[k] is not None and d[k]<0 for k in ("load_w","charge_w","discharge_w")): d["fresh"]=False
        d["average_load_w"]=sum(v for _,v in self.average)/len(self.average) if self.average else 0
        d["battery_power"]=d["discharge_w"]-d["charge_w"] if d["discharge_w"] is not None and d["charge_w"] is not None else None
        cells=[]
        for entity in self.sources.get("cell_entities",[]):
            state=self.hass.states.get(entity)
            if not state or state.attributes.get("unit_of_measurement")!="V" or time.time()-getattr(state,"last_reported",state.last_updated).timestamp()>self.settings["freshness_seconds"]:
                cells.append(None)
            else: cells.append(numeric(state.state))
        d["cells"]=cells
        return d

    def storm(self):
        if self.settings["storm_override"]: return True,"Manual storm override"
        if self.settings["weather_policy"]!="Automatic advice": return False,"Manual reserve"
        alert=self.hass.states.get(self.sources.get("alert_entity",""))
        warning=False
        if alert and time.time()-getattr(alert,"last_reported",alert.last_updated).timestamp()<900:
            text=str(alert.attributes.get("alerts",alert.attributes.get("events",alert.state))).lower()
            warning=any(x in text for x in ("tornado warning","hurricane","tropical storm","ice storm","blizzard","high wind warning","severe thunderstorm"))
        weather=self.hass.states.get(self.sources.get("weather_entity",""))
        configured=bool(self.sources.get("weather_entity") or self.sources.get("alert_entity"))
        stale_weather=bool(self.sources.get("weather_entity") and (not weather or time.time()-getattr(weather,"last_reported",weather.last_updated).timestamp()>=3600))
        stale_alert=bool(self.sources.get("alert_entity") and (not alert or time.time()-getattr(alert,"last_reported",alert.last_updated).timestamp()>=900))
        if configured and (stale_weather or stale_alert):
            return True,"Automatic advice: weather stale, reserve held"
        if weather and time.time()-getattr(weather,"last_reported",weather.last_updated).timestamp()<3600:
            unit=weather.attributes.get("wind_speed_unit","km/h")
            factor={"mph":1,"km/h":.621371,"m/s":2.23694,"kn":1.15078}.get(unit)
            forecast=self.weather_forecast if time.time()-self.forecast_time<3600 else []
            for row in [weather.attributes|{"condition":weather.state}]+forecast:
                speed=numeric(row.get("wind_speed"));gust=numeric(row.get("wind_gust_speed"))
                warning |= row.get("condition") in {"lightning","lightning-rainy","exceptional"}
                warning |= bool(factor and ((speed is not None and speed*factor>=self.settings["storm_wind_mph"]) or (gust is not None and gust*factor>=self.settings["storm_gust_mph"])))
        return warning,"Automatic advice" if weather or alert else "Automatic advice: no weather source"

    def prices(self,now):
        if self.settings["price_source"]=="Manual prices":
            return {"Super off-peak":self.settings["manual_super_rate"],"Off-peak":self.settings["manual_off_rate"],"Peak":self.settings["manual_peak_rate"]}
        if self.rate_month!=now.strftime("%B %Y") or time.time()-self.last_fetch>172800: return None
        return pseg_rates(now,self.supply)

    async def fetch_context(self,now):
        if self.settings["price_source"]=="PSEG Rate 195" and time.time()-getattr(self,"last_attempt",0)>21600:
            self.last_attempt=time.time()
            try:
                async with asyncio.timeout(30):
                    async with async_get_clientsession(self.hass).get(PSEG_URL) as response:
                        response.raise_for_status()
                        text=await response.text()
                text=re.sub(r"<[^>]+>"," ",text)
                matches=re.findall(r"The\s+"+re.escape(now.strftime("%B %Y"))+r"\s+PSC rate is\s*\$([0-9.]+)",text)
                value=numeric(matches[0]) if matches else None
                if value is not None and 0<value<1:
                    self.supply=value;self.last_fetch=time.time();self.rate_month=now.strftime("%B %Y")
            except (TimeoutError,OSError,ValueError) as err:
                LOGGER.warning("Published rate refresh failed: %s",type(err).__name__)
            except Exception as err:
                LOGGER.warning("Published rate unavailable: %s",type(err).__name__)
        entity=self.sources.get("weather_entity")
        if entity and time.time()-getattr(self,"forecast_attempt",0)>1800:
            self.forecast_attempt=time.time()
            try:
                result=await self.hass.services.async_call("weather","get_forecasts",{"entity_id":entity,"type":"hourly"},blocking=True,return_response=True)
                self.weather_forecast=result.get(entity,{}).get("forecast",[])[:24];self.forecast_time=time.time()
            except HomeAssistantError:
                self.weather_forecast=[]

    def recompute(self):
        now=self.local_now();d=self.measurements();storm,weather_mode=self.storm();rates=self.prices(now)
        plan=make_plan(now,d,self.settings,rates,storm)
        period=price_window(now,self.settings)
        extreme=cell_extremes(d["cells"])
        data=dict(d,**(extreme or {}),plan=plan.decision,reason=plan.reason,reserve_soc=plan.reserve_soc,
                  runtime_hours=plan.runtime_hours,economic_margin=plan.economic_margin,
                  tariff=period,weather_mode=weather_mode,storm=storm,current_price=rates[period] if rates else None,
                  overnight_price=rates["Super off-peak"] if rates else None,
                  price_status="Manual prices" if self.settings["price_source"]=="Manual prices" else "Published PSEG estimate" if rates else "Rates unavailable / review needed",
                  scheduler_status="Fault latched" if self.command_error else "Manual hold" if time.time()<self.hold_until else "Automatic" if self.settings["automatic_enabled"] else "Observe only",
                  command_result=self.command_error or self.topics.get("last_result",{}).get("status","No command"),
                  bridge_status=self.topics.get("status",{}).get("status","unavailable"))
        data["estimated_savings_total"]=self.ledger["avoided"]-self.ledger["charging"]-self.ledger["wear"]
        for kind,key in (("day",now.strftime("%Y-%m-%d")),("month",now.strftime("%Y-%m")),("year",now.strftime("%Y"))):
            totals=self.ledger["periods"].get(key,{})
            data[f"savings_{kind}"]=totals.get("avoided",0)-totals.get("charging",0)-totals.get("wear",0)
        data["integrated_energy_in"]=self.ledger["energy_in"];data["integrated_energy_out"]=self.ledger["energy_out"]
        self.attributes["plan"]=asdict(plan)|{"automatic_switching":self.settings["automatic_enabled"],"assumed_capacity_kwh":self.settings["capacity_kwh"]}
        self.attributes["current_price"]={"source_url":PSEG_URL,"month":self.rate_month,"last_fetch":self.last_fetch,"delivery_year":2026,"account_adjustments_included":False}
        self.attributes["highest_cell"]={"positions":extreme["highest_positions"] if extreme else [],"ordering":"Selected source list, left to right"}
        self.attributes["lowest_cell"]={"positions":extreme["lowest_positions"] if extreme else [],"ordering":"Selected source list, left to right"}
        self.attributes["estimated_savings_total"]={"tracked_seconds":self.ledger["tracked_seconds"],"method":"Forward cash flow; excludes outages; all charging assumed grid-sourced; initial stored energy cost unknown"}
        self.async_set_updated_data(data)
        return d,plan,rates,period

    async def async_tick(self,_now=None):
        if self.stopped: return
        now=self.local_now()
        await self.fetch_context(now)
        d,plan,rates,period=self.recompute()
        tick=time.time()
        current=money_rates(d,self.settings,rates[period] if rates else None)
        if self.previous and current and 0<tick-self.last_tick<=90:
            # Left rule. Break intervals at source/mode/price/calendar changes; never backfill gaps.
            old,old_d,old_period,old_date=self.previous
            if old_period==period and old_date==now.date() and old_d["mode"]==d["mode"]:
                hours=(tick-self.last_tick)/3600
                for key,value in old.items():
                    amount=value*hours;self.ledger[key]+=amount
                    for datekey in (now.strftime("%Y-%m-%d"),now.strftime("%Y-%m"),now.strftime("%Y")):
                        item=self.ledger["periods"].setdefault(datekey,{})
                        item[key]=item.get(key,0)+amount
                self.ledger["tracked_seconds"]+=tick-self.last_tick
        if getattr(self,"previous_energy",None) and d["fresh"] and 0<tick-self.last_tick<=90:
            old=self.previous_energy;hours=(tick-self.last_tick)/3600
            self.ledger["energy_in"]+=old[0]/1000*hours;self.ledger["energy_out"]+=old[1]/1000*hours
        self.previous_energy=(d["charge_w"],d["discharge_w"]) if d["fresh"] else None
        self.previous=(current,d,period,now.date()) if current else None;self.last_tick=tick
        if d["fresh"]:
            self.average.append((tick,d["load_w"]))
        while self.average and tick-self.average[0][0]>86400: self.average.popleft()
        self.save();self.recompute()
        if (self.settings["automatic_enabled"] and self.settings["commissioned"] and self.settings["switching_confirmed"]
            and not self.command_error and tick>=self.hold_until and tick-self.start_time>=90
            and tick-self.last_switch>=300 and plan.desired_priority):
            # Only two confirmed source preferences; never change BMS thresholds or output limits.
            try:
                await self.async_control("output_priority",plan.desired_priority,automatic=True)
            except HomeAssistantError as err:
                LOGGER.error("Scheduling stopped after command failure: %s",err)

    def save(self):
        self.store.async_delay_save(lambda:{"ledger":self.ledger,"hold_until":self.hold_until,"command_error":self.command_error},5)

    def local_now(self):
        now=dt_util.now()
        return now.astimezone(ZoneInfo("America/New_York")) if self.settings["price_source"]=="PSEG Rate 195" else now

    async def async_setting(self,key,value):
        if key=="automatic_enabled" and value and not (self.settings["commissioned"] and self.settings["switching_confirmed"]):
            raise HomeAssistantError("Confirm the critical-load meter and both source transitions before enabling scheduling")
        self.settings[key]=value
        self.hass.config_entries.async_update_entry(self.entry,options=dict(self.entry.options)|{key:value})
        self.previous=None
        self.recompute()

    async def async_control(self,key,value,automatic=False):
        from .select import CATALOG
        if key not in CATALOG: raise HomeAssistantError("Control outside verified registry")
        metadata=self.topics.get(f"control/{key}/attributes",{})
        options=metadata.get("allowed_values",[])
        if value not in options: raise HomeAssistantError("Value not advertised by the verified bridge")
        if key in {"utility_charge_current","total_charge_current"}:
            number=numeric(value.split()[0])
            if number is None or number>min(30,self.settings["charge_cap_a"]):
                raise HomeAssistantError("Battery charge ceiling would be exceeded")
        if key=="output_priority" and value=="SUB":
            for limit in ("utility_charge_current","total_charge_current"):
                current=self.topics.get(f"control/{limit}/state","")
                amps=numeric(current.split()[0]) if current else None
                if amps is None or amps>min(30,self.settings["charge_cap_a"]):
                    raise HomeAssistantError("Read or lower battery charging limits before grid charging")
            if automatic and self.topics.get("control/charger_priority/state")!="SNU (solar + utility)":
                raise HomeAssistantError("Automatic charging requires the confirmed SNU source mode")
        if not self.fresh_topic("status") or self.topics.get("status",{}).get("status")!="ready" or self.command_error:
            raise HomeAssistantError("Bridge is not ready, or a command fault is latched")
        if self.lock.locked(): raise HomeAssistantError("Another command is awaiting verification")
        if self.topics.get(f"control/{key}/state")==value:
            if not automatic:
                self.hold_until=time.time()+self.settings["manual_override_minutes"]*60
                self.save();self.recompute()
            return
        async with self.lock:
            self.pending=self.hass.loop.create_future();self.pending_key=key;self.pending_value=value;self.command_time=time.time()
            try:
                await mqtt.async_publish(self.hass,self.sources["mqtt_root"]+f"/control/{key}/set",value,qos=0,retain=False)
                await asyncio.wait_for(self.pending,50)
                # Await the subsequent confirmed state publication, not an optimistic value.
                for _ in range(12):
                    if self.topics.get(f"control/{key}/state")==value: break
                    await asyncio.sleep(.5)
                else: raise HomeAssistantError("Acknowledgement arrived without matching settings readback")
                self.last_switch=time.time()
                if not automatic: self.hold_until=time.time()+self.settings["manual_override_minutes"]*60
            except (TimeoutError,HomeAssistantError) as err:
                self.command_error=str(err) or "Command verification timed out"
                raise HomeAssistantError(self.command_error) from err
            finally:
                self.pending=None;self.pending_key=None;self.pending_value=None;self.save();self.recompute()

    async def async_close(self):
        self.stopped=True
        if self.pending and not self.pending.done(): self.pending.cancel()
        await self.store.async_save({"ledger":self.ledger,"hold_until":self.hold_until,"command_error":self.command_error})
