"""Local MQTT transport, fresh telemetry, verified writes and persistent accounting."""
import asyncio
from collections import deque
from dataclasses import asdict
from datetime import timedelta
from functools import partial
import json
import logging
import re
import time
from zoneinfo import ZoneInfo

from homeassistant.components import mqtt
from homeassistant.const import UnitOfTemperature
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import DEFAULTS, DOMAIN, PSEG_URL
from .charge_guard import ChargeGuard, CHARGE_OFF, CHARGE_ON, high_charge_discharge_allowed
from .policy import cell_extremes, plan_with_reserve_hold, money_rates, numeric, pseg_rates, price_window, normalize_planning_goal, planning_profile
from .projection import project_savings
from .learning import learn_load,HISTORY_DAYS
from .schedule import preview_schedule
from .thermal import ThermalHistory, thermal_advice
from .discovery import suggested_sources

LOGGER=logging.getLogger(__name__)
# Two captured handovers took approximately ten minutes from utility entry.
# Allow additional polling/settling time; this is an observation window, not a
# promise that firmware will always transfer after a fixed ten-minute timer.
SOURCE_TRANSFER_WINDOW=12*60


class BatteryCoordinator(DataUpdateCoordinator):
    def __init__(self,hass,entry):
        super().__init__(hass,LOGGER,name=entry.title,config_entry=entry)
        self.entry=entry
        self.settings={key:entry.options.get(key,entry.data.get(key,value)) for key,value in DEFAULTS.items()}
        self.settings['learning_history_days']=int(self.settings['learning_history_days'])
        self.settings['planning_goal']=normalize_planning_goal(self.settings['planning_goal'])
        self.sources=dict(entry.data)|dict(entry.options)
        detected=suggested_sources(hass)
        if not self.sources.get('cold_temperature_entity'):
            self.sources['cold_temperature_entity']=(detected.get('cold_temperature_entity') if detected.get('soc_entity')==self.sources.get('soc_entity') else None) or self.sources.get('temperature_entity') or ''
        self.thermal=ThermalHistory();self.thermal_attempt=0
        self.data={}
        self.transfer_status=""
        self.source_transfer=None
        self.source_intent=None
        self.charge_guard=ChargeGuard()
        self.guard_stop_failed=False
        self.source_lock=asyncio.Lock()
        self.attributes={}
        self.topics={}
        self.received={}
        self.source_seen={}
        self.lock=asyncio.Lock()
        self.tick_lock=asyncio.Lock()
        self.pending=None
        self.pending_key=None
        self.pending_value=None
        self.command_time=0
        self.command_error=None
        self.hold_until=0
        self.reserve_hold=False
        self.last_switch=0
        self.average=deque(maxlen=2880)
        self.store=Store(hass,1,f"{DOMAIN}.{entry.entry_id}")
        self.ledger={"avoided":0.,"charging":0.,"wear":0.,"energy_in":0.,"energy_out":0.,"periods":{},"tracked_seconds":0.}
        self.recorded={"avoided":0.,"charging":0.,"wear":0.,"periods":{},"tracked_seconds":0.,"since":None}
        self.load_profile=[]
        self.profile_seen=0
        self.profile_attempt=0
        self.learning={'status':'Waiting for history','history_days':self.settings['learning_history_days'],'recorded_hours':0,'available_days':0}
        self.projection_cache=(None,None)
        self.previous=None
        self.last_tick=0
        self.last_fetch=0
        self.supply=None
        self.rate_month=None
        self.weather_forecast=[]
        self.forecast_time=0
        self.nws_alerts=[]
        self.nws_alert_details=[]
        self.nws_seen=0
        self.nws_attempt=0
        self.stopped=False
        self.refresh_handle=None
        self.start_time=time.time()

    async def async_start(self):
        saved=await self.store.async_load()
        self._restore_state(saved)
        if not await mqtt.async_wait_for_mqtt_client(self.hass):
            raise HomeAssistantError("Configure the Home Assistant MQTT integration first")
        unsub=await mqtt.async_subscribe(self.hass,self.sources["mqtt_root"]+"/#",self._message,qos=0)
        self.entry.async_on_unload(unsub)
        for key in ("battery_heartbeat_topic","load_heartbeat_topic"):
            if self.sources.get(key):
                def heartbeat(msg,source=key):
                    if not msg.retain and (numeric(msg.payload) is not None or dt_util.parse_datetime(msg.payload)):
                        self.source_seen[source]=time.time()
                        self.queue_refresh()
                self.entry.async_on_unload(await mqtt.async_subscribe(self.hass,self.sources[key],heartbeat,qos=0))
        self.entry.async_on_unload(async_track_time_interval(self.hass,self.async_tick,timedelta(seconds=30)))
        await self.async_tick()

    def _restore_state(self,saved):
        if not saved: return
        self.ledger.update(saved.get("ledger",{}))
        self.recorded.update(saved.get("recorded",{}))
        self.hold_until=saved.get("hold_until",0)
        self.reserve_hold=bool(saved.get('reserve_hold',False))
        self.last_switch=saved.get("last_switch",0)
        self.command_error=saved.get("command_error")
        self.source_transfer=saved.get("source_transfer")
        self.source_intent=saved.get("source_intent")
        self.charge_guard=ChargeGuard(saved.get("charge_guard"))
        self.guard_stop_failed=saved.get("guard_stop_failed",False)
        if saved.get('thermal_source')==self.sources.get('cold_temperature_entity'):
            self.thermal=ThermalHistory(saved.get('thermal'))
        if self.source_intent:
            self.source_transfer=None
            self.command_error="Source change interrupted by restart; inspect actual source and stored settings in Advanced before acknowledging. No commands replayed."

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
            self.source_transfer=None
            self.transfer_status="Source preference changed outside this request"
            self.save()
        if key=="last_result" and not msg.retain and self.pending and not self.pending.done():
            stamp=dt_util.parse_datetime(payload.get("timestamp","")) if isinstance(payload,dict) else None
            if (isinstance(payload,dict) and payload.get("control")==self.pending_key and stamp
                and stamp.timestamp()>=self.command_time):
                if payload.get("status") in {"verified","verified_no_change"}:
                    self.pending.set_result(payload)
                elif payload.get("status") not in {"pending"}:
                    self.pending.set_exception(HomeAssistantError(str(payload.get("error",payload.get("status")))))
        self.queue_refresh()

    @callback
    def queue_refresh(self):
        """Coalesce a bridge publication burst into one coherent UI snapshot."""
        if self.stopped or self.refresh_handle: return
        def flush():
            self.refresh_handle=None
            if not self.stopped: self.recompute()
        self.refresh_handle=self.hass.loop.call_later(1,flush)

    def fresh_topic(self,key,age=60):
        return 0<=time.time()-self.received.get(key,0)<age

    def entity_number(self,key,units=None):
        state=self.hass.states.get(self.sources.get(key) or "")
        if not state or state.state in {"unknown","unavailable"}: return None
        stamp=getattr(state,"last_reported",state.last_updated)
        heartbeat="load_heartbeat_topic" if key=="load_entity" else "battery_heartbeat_topic"
        age=time.time()-self.source_seen.get(heartbeat,0) if self.sources.get(heartbeat) else time.time()-stamp.timestamp()
        if not 0<=age<self.settings["freshness_seconds"]: return None
        unit=state.attributes.get("unit_of_measurement")
        if units and unit not in units: return None
        value=numeric(state.state)
        if value is not None and unit=="kW": value*=1000
        if value is not None and unit=="Wh": value/=1000
        if value is not None and unit==UnitOfTemperature.FAHRENHEIT: value=(value-32)*5/9
        return value

    def measurements(self):
        d={key:self.entity_number(source,unit) for key,source,unit in [
            ("soc","soc_entity",{"%"}),("load_w","load_entity",{"W","kW"}),
            ("charge_w","charge_power_entity",{"W","kW"}),("discharge_w","discharge_power_entity",{"W","kW"}),
            ("voltage","voltage_entity",{"V"}),("current","current_entity",{"A"}),
            ("temperature","temperature_entity",{UnitOfTemperature.CELSIUS,UnitOfTemperature.FAHRENHEIT}),("remaining_ah","remaining_ah_entity",{"Ah"}),
            ("cold_temperature","cold_temperature_entity",{UnitOfTemperature.CELSIUS,UnitOfTemperature.FAHRENHEIT}),
            ("energy_in","energy_in_entity",{"kWh","Wh"}),("energy_out","energy_out_entity",{"kWh","Wh"})]}
        raw=self.topics.get("raw_readings",{})
        d['cold_temperature_source']=self.sources.get('cold_temperature_entity')
        mode=raw.get("HSTS",{}).get("ascii","") if isinstance(raw,dict) else ""
        tokens=mode.lstrip("(").split()
        d["mode"]={"L":"Line","B":"Battery"}.get(tokens[1][0] if len(tokens)>1 and tokens[1] else "","Unknown")
        d["priority"]=self.topics.get("control/output_priority/state")
        d["inverter_status_code"]=tokens[0] if tokens else "Unknown"
        d["grid_voltage"]=numeric(self.topics.get("telemetry/grid_voltage")) if self.fresh_topic("telemetry/grid_voltage") else None
        alarms=self.hass.states.get(self.sources.get("alarms_entity",""))
        d["alarms"]=alarms.state if alarms else "unavailable"
        alarm_age=time.time()-self.source_seen.get("battery_heartbeat_topic",0) if self.sources.get("battery_heartbeat_topic") else time.time()-getattr(alarms,"last_reported",alarms.last_updated).timestamp() if alarms else 999
        alarm_fresh=alarms and 0<=alarm_age<self.settings["freshness_seconds"]
        d["has_bms_alarm"]=not bool(alarm_fresh and d["alarms"].lower() in {"no alarms","none","ok","0","off"})
        details=alarms.attributes if alarms else {}
        sampled=dt_util.parse_datetime(details.get("sampled_at",""))
        codes=details.get("alarm_codes")
        d["alarm_codes"]=codes if isinstance(codes,list) and all(isinstance(c,str) for c in codes) else None
        if sampled and 0<=time.time()-sampled.timestamp()<60 and d["alarm_codes"]:
            d["has_bms_alarm"]=True
        d["soc_warning_only"]=bool(alarm_fresh and sampled and 0<=time.time()-sampled.timestamp()<60
            and details.get("decoder_version")==1 and d["alarm_codes"]==["soc_high_l1"])
        status=self.topics.get("status",{})
        d["bridge_ready"]=bool(isinstance(status,dict) and status.get("status") in {"ready","write_in_progress"}
            and not status.get("fault") and d["inverter_status_code"]=="00")
        d["healthy"]=bool(alarm_fresh and (not d["has_bms_alarm"] or d["soc_warning_only"])
                          and isinstance(status,dict) and status.get("status") in {"ready","write_in_progress"}
                          and not status.get("fault") and d["inverter_status_code"]=="00")
        d["fresh"]=bool(self.fresh_topic("status") and self.fresh_topic("raw_readings")
                        and isinstance(raw,dict) and 0<=raw.get("HSTS",{}).get("age_seconds",999)<45
                        and d["mode"] in {"Line","Battery"} and all(d[k] is not None for k in ("soc","load_w","charge_w","discharge_w","grid_voltage")))
        if any(d[k] is not None and d[k]<0 for k in ("load_w","charge_w","discharge_w")): d["fresh"]=False
        d["average_load_w"]=sum(v for _,v in self.average)/len(self.average) if self.average else 0
        d['peak_forecast_wh']=None
        model=self.learning
        if (model.get('status')=='Ready' and model.get('coverage_percent',0)>=80
            and model.get('validation_hours',0)>=24 and time.time()-self.profile_seen<10800
            and model.get('forecast_date')==self.local_now().date().isoformat()):
            profile=model.get('today_profile_w',[])
            start,end=(15,19) if self.settings['price_source']=='PSEG Rate 195' else (self.settings['peak_start'],self.settings['peak_end'])
            if len(profile)==24 and all(numeric(v) is not None for v in profile):
                uncertainty=(model.get('typical_error_w') or 0)*planning_profile(self.settings)['forecast_error_multiplier']
                d['peak_forecast_wh']=sum(((v+uncertainty)/(self.settings['discharge_efficiency']/100)+self.settings['overhead_w'])*max(0,min(h+1,end)-max(h,start)) for h,v in enumerate(profile))
        d["battery_power"]=d["discharge_w"]-d["charge_w"] if d["discharge_w"] is not None and d["charge_w"] is not None else None
        cells=[]
        for entity in self.sources.get("cell_entities",[]):
            state=self.hass.states.get(entity)
            age=time.time()-self.source_seen.get("battery_heartbeat_topic",0) if self.sources.get("battery_heartbeat_topic") else time.time()-getattr(state,"last_reported",state.last_updated).timestamp() if state else 999
            if not state or state.attributes.get("unit_of_measurement")!="V" or not 0<=age<self.settings["freshness_seconds"]:
                cells.append(None)
            else: cells.append(numeric(state.state))
        d["cells"]=cells
        # Display-only bounds from the selected cells' BMS readback metadata.
        # Never infer chemistry or use these UI bounds to control equipment.
        limits=[]
        for entity in self.sources.get("cell_entities",[]):
            state=self.hass.states.get(entity)
            a=state.attributes if state else {}
            low=numeric(a.get("cell_protection_low_v"));high=numeric(a.get("cell_protection_high_v"))
            if low is not None and high is not None and 0<low<high<6:
                limits.append((low,high))
        d["cell_voltage_limits"]={"low":limits[0][0],"high":limits[0][1]} if limits and len(limits)==len(cells) and len(set(limits))==1 else None
        d["high_charge_recovery"]=bool(alarm_fresh and sampled and 0<=time.time()-sampled.timestamp()<30
            and details.get("decoder_version")==1 and high_charge_discharge_allowed(
                d["alarm_codes"],cells,d["temperature"],self.settings["charge_cell_ceiling"],
                details.get("discharge_mosfet"),details.get("cell_count")))
        # Directional permission: charge-side alarms keep charging inhibited,
        # while BMS-permitted discharge can lower high SOC/voltage. Never clear
        # the alarm, switch MOSFETs or permit unknown/mixed faults.
        if d["has_bms_alarm"]:
            d["healthy"]=bool(d["high_charge_recovery"] and isinstance(status,dict)
                and status.get("status") in {"ready","write_in_progress"}
                and not status.get("fault") and d["inverter_status_code"]=="00")
        for key in ("grid_voltage","grid_frequency","output_voltage","output_frequency","output_apparent_power","output_power","output_load","battery_voltage","battery_soc","battery_charge_current","battery_discharge_current","pv_voltage","pv_current","pv_power","inverter_temperature"):
            topic="telemetry/"+key
            d["inverter_"+key]=numeric(self.topics.get(topic)) if self.fresh_topic(topic) else None
        return d

    def storm(self):
        if self.settings["storm_override"]: return True,"Manual storm override"
        if self.settings["weather_policy"]!="Automatic advice": return False,"Manual reserve"
        alert=self.hass.states.get(self.sources.get("alert_entity",""))
        warning=False
        zone=self.sources.get("nws_alert_zone")
        if zone:
            if time.time()-self.nws_seen>=900:
                return True,"Automatic advice: alerts stale, reserve held"
            text=" ".join(self.nws_alerts).lower()
            warning=any(x in text for x in ("tornado","hurricane","tropical storm","ice storm","blizzard","high wind","severe thunderstorm","winter storm","flash flood"))
        elif alert and time.time()-getattr(alert,"last_reported",alert.last_updated).timestamp()<900:
            text=str(alert.attributes.get("alerts",alert.attributes.get("events",alert.state))).lower()
            warning=any(x in text for x in ("tornado warning","hurricane","tropical storm","ice storm","blizzard","high wind warning","severe thunderstorm"))
        weather=self.hass.states.get(self.sources.get("weather_entity",""))
        configured=bool(self.sources.get("weather_entity") or self.sources.get("alert_entity") or zone)
        forecast_current=any((stamp:=dt_util.parse_datetime(row.get("datetime",""))) and 0<=stamp.timestamp()-time.time()<=86400 for row in self.weather_forecast)
        weather_fresh=bool(weather and weather.state not in {"unknown","unavailable"} and
                           (time.time()-getattr(weather,"last_reported",weather.last_updated).timestamp()<3600 or
                            (time.time()-self.forecast_time<3600 and forecast_current)))
        stale_weather=bool(self.sources.get("weather_entity") and not weather_fresh)
        stale_alert=bool(not zone and self.sources.get("alert_entity") and (not alert or time.time()-getattr(alert,"last_reported",alert.last_updated).timestamp()>=900))
        if configured and (stale_weather or stale_alert):
            return True,"Automatic advice: weather stale, reserve held"
        if weather_fresh:
            unit=weather.attributes.get("wind_speed_unit","km/h")
            factor={"mph":1,"km/h":.621371,"m/s":2.23694,"kn":1.15078}.get(unit)
            forecast=self.weather_forecast if time.time()-self.forecast_time<3600 else []
            for row in [weather.attributes|{"condition":weather.state}]+forecast:
                speed=numeric(row.get("wind_speed"));gust=numeric(row.get("wind_gust_speed"))
                warning |= row.get("condition") in {"lightning","lightning-rainy","exceptional"}
                warning |= bool(factor and ((speed is not None and speed*factor>=self.settings["storm_wind_mph"]) or (gust is not None and gust*factor>=self.settings["storm_gust_mph"])))
        return warning,"Automatic advice" if weather or alert or zone else "Automatic advice: no weather source"

    def prices(self,now):
        if self.settings["price_source"]=="Manual prices":
            return {"Super off-peak":self.settings["manual_super_rate"],"Off-peak":self.settings["manual_off_rate"],"Peak":self.settings["manual_peak_rate"]}
        if self.rate_month!=now.strftime("%B %Y") or time.time()-self.last_fetch>172800: return None
        return pseg_rates(now,self.supply)

    async def fetch_context(self,now):
        if self.settings.get('thermal_enabled') and time.time()-self.thermal_attempt>=3600:
            self.thermal_attempt=time.time()
            try:
                from homeassistant.components.recorder import get_instance
                from homeassistant.components.recorder.statistics import statistics_during_period
                temp=self.sources.get('cold_temperature_entity');power=self.sources.get('charge_power_entity')
                if temp and power:
                    rows=await get_instance(self.hass).async_add_executor_job(partial(statistics_during_period,
                        self.hass,now-timedelta(days=7),now,{temp,power},'hour',{'temperature':'°C','power':'W'},{'mean'}))
                    self.thermal.seed(rows.get(temp,[]),rows.get(power,[]))
            except Exception as err:
                LOGGER.debug('Thermal history unavailable: %s',type(err).__name__)
        if time.time()-self.profile_attempt>=900:
            self.profile_attempt=time.time()
            try:
                from homeassistant.components.recorder import get_instance
                from homeassistant.components.recorder.statistics import statistics_during_period
                entity=self.sources["load_entity"]
                days=int(self.settings['learning_history_days'])
                rows=await get_instance(self.hass).async_add_executor_job(partial(statistics_during_period,self.hass,now-timedelta(days=days),now,{entity},"hour",None,{"mean"}))
                state=self.hass.states.get(entity)
                factor=1000 if state and state.attributes.get("unit_of_measurement")=="kW" else 1
                self.learning=await self.hass.async_add_executor_job(learn_load,rows.get(entity,[]),now,days,factor)
                self.learning['source']=entity
                groups={hour:[] for hour in range(24)}
                for row in rows.get(entity,[]):
                    value=numeric(row.get("mean"));stamp=numeric(row.get("start"))
                    if value is not None and stamp is not None and 0<=value*factor<=10000:
                        groups[dt_util.utc_from_timestamp(stamp).astimezone(now.tzinfo).hour].append(value*factor)
                if all(groups.values()):
                    self.load_profile=self.learning['profile_w'] or [sum(groups[h])/len(groups[h]) for h in range(24)]
                    self.profile_seen=time.time()
            except Exception as err:
                self.learning=dict(self.learning,status='History unavailable',detail='Home Assistant could not read this sensor’s recorded history. Live scheduling keeps its existing safeguards.')
                LOGGER.debug("Reference load history unavailable: %s",type(err).__name__)
        zone=self.sources.get("nws_alert_zone")
        if zone and time.time()-self.nws_attempt>=300:
            self.nws_attempt=time.time()
            try:
                async with asyncio.timeout(15):
                    async with async_get_clientsession(self.hass).get("https://api.weather.gov/alerts/active/zone/"+zone,headers={"User-Agent":"HomeBattery/1.0 (https://github.com/spikked27/home-battery)"}) as response:
                        response.raise_for_status();payload=await response.json()
                if not isinstance(payload.get("features"),list): raise ValueError("Invalid NWS response")
                self.nws_alerts=[str(item.get("properties",{}).get("event","Unknown alert")) for item in payload["features"]]
                self.nws_alert_details=[{key:item.get("properties",{}).get(key) for key in ("event","headline","severity","onset","expires","description","instruction")} for item in payload["features"]]
                self.nws_seen=time.time()
            except Exception as err:
                LOGGER.warning("NWS alerts unavailable: %s",type(err).__name__)
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
        self._update_source_transfer(d)
        values=[numeric(str(self.topics.get(f'control/{key}/state','')).split(' ')[0]) for key in ('utility_charge_current','total_charge_current')]
        amps=min(values) if all(v is not None for v in values) else None
        weather=self.hass.states.get(self.sources.get('weather_entity',''))
        unit=weather.attributes.get('temperature_unit') if weather else None
        forecast=[]
        if time.time()-self.forecast_time<3600:
            for row in self.weather_forecast:
                stamp=dt_util.parse_datetime(row.get('datetime',''));temp=numeric(row.get('temperature'))
                if stamp and temp is not None and unit in {'°C','°F'}:
                    forecast.append([stamp.timestamp(),(temp-32)*5/9 if unit=='°F' else temp])
        d['thermal_context']={'model':self.thermal.model(now.tzinfo),'charge_amps':amps,
            'started_window_end':self.thermal.started_window_end,'budget_uncertain':self.thermal.budget_uncertain,
            'cost':self.thermal.cost if self.thermal.day==now.date().isoformat() else 0.,
            'energy':self.thermal.energy if self.thermal.day==now.date().isoformat() else 0.,
            'weather':forecast,'price':rates[price_window(now,self.settings)] if rates else None}
        thermal=thermal_advice(now,d,self.settings,d['thermal_context'])
        plan,held=plan_with_reserve_hold(now,d,self.settings,rates,storm,self.reserve_hold)
        d['scheduled_charge_block']=bool(self.settings.get('thermal_enabled') and self.settings['automatic_enabled']
            and time.time()>=self.hold_until
            and plan.decision not in {'Recharge','Recover reserve','Charge','Keep ready','Cold-weather charge'})
        if held!=self.reserve_hold:
            self.reserve_hold=held;self.save()
        d['reserve_hold']=held
        period=price_window(now,self.settings)
        extreme=cell_extremes(d["cells"])
        charge_reason=self.charge_guard.evaluate(d,self.settings,time.time())
        data=dict(d,**(extreme or {}),plan=plan.decision,reason=plan.reason,reserve_soc=plan.reserve_soc,
                  thermal=thermal,thermal_status=thermal['status'],thermal_early_charge_cost=thermal.get('cost_today',0),
                  runtime_hours=plan.runtime_hours,economic_margin=plan.economic_margin,
                  tariff=period,weather_mode=weather_mode,storm=storm,current_price=rates[period] if rates else None,
                  overnight_price=rates["Super off-peak"] if rates else None,
                  price_status="Manual prices" if self.settings["price_source"]=="Manual prices" else "Published PSEG estimate" if rates else "Rates unavailable / review needed",
                  scheduler_status="Fault latched" if self.command_error else "Observe only" if not self.settings["automatic_enabled"] else "Manual hold" if time.time()<self.hold_until else "Automatic",
                  command_result=self.command_error or self.transfer_status or self.topics.get("last_result",{}).get("status","No command"),
                  source_transfer=dict(self.source_transfer) if self.source_transfer else None,
                  bridge_status=self.topics.get("status",{}).get("status","unavailable"),
                  charge_guard_status=charge_reason or "Utility charging permitted below target",
                  utility_charging_blocked=bool(charge_reason))
        self.attributes["charge_guard_status"]={"latches":self.charge_guard.saved(),
            "cell_ceiling_v":self.settings["charge_cell_ceiling"],"resume_soc_gap":5,
            "resume_cell_gap_v":.05,"recovery_seconds":180,
            "scope":"Utility charging only; HA/MQTT required; does not replace BMS or inhibit PV"}
        self.attributes["alarms"]={"codes":d["alarm_codes"],"soc_warning_only":d["soc_warning_only"]}
        self.attributes['thermal_status']=thermal
        self.attributes['thermal_early_charge_cost']={'scope':'Measured grid charging cost during cold-weather advances only; excludes ordinary overnight charging','supervisory_budget':True}
        data["estimated_savings_total"]=self.ledger["avoided"]-self.ledger["charging"]-self.ledger["wear"]
        for kind,key in (("day",now.strftime("%Y-%m-%d")),("month",now.strftime("%Y-%m")),("year",now.strftime("%Y"))):
            totals=self.ledger["periods"].get(key,{})
            data[f"savings_{kind}"]=totals.get("avoided",0)-totals.get("charging",0)-totals.get("wear",0)
            recorded=self.recorded["periods"].get(key,{})
            data[f"recorded_savings_{kind}"]=recorded.get("avoided",0)-recorded.get("charging",0)-recorded.get("wear",0)
        data["recorded_savings_total"]=self.recorded["avoided"]-self.recorded["charging"]-self.recorded["wear"]
        data["savings_mode"]="Recorded" if self.settings["commissioned"] else "Projected"
        profile=self.load_profile if time.time()-self.profile_seen<10800 else []
        charge_values=[numeric(str(self.topics.get(f"control/{key}/state","")).split(" ")[0]) for key in ("utility_charge_current","total_charge_current")]
        amps=min(charge_values) if all(v is not None for v in charge_values) else None
        pack_voltage=round(d["voltage"] or d.get("inverter_battery_voltage") or 0)
        pause=(self.command_error or ('Manual control hold is active.' if time.time()<self.hold_until else '')
               or ('Waiting for the current source transfer.' if self.source_transfer else '')
               or ('Waiting for restart telemetry to settle.' if time.time()-self.start_time<90 else ''))
        data['schedule_preview']=({'status':'Paused','message':pause,'segments':[],'points':[]} if pause else
            preview_schedule(now,d,self.settings,rates,amps,pack_voltage,
                weekly=self.learning.get('profiles_by_weekday') if d['peak_forecast_wh'] is not None else None,
                error_w=self.learning.get('typical_error_w') or 0,storm=storm,
                guard=self.charge_guard.saved()))
        weekly=self.learning.get('profiles_by_weekday') if profile and self.learning.get('status')=='Ready' else None
        key=repr((profile,weekly,self.settings,rates,amps,pack_voltage,storm,now.date()))
        if key!=self.projection_cache[0]:
            projected=project_savings(now,profile,self.settings,rates,amps,pack_voltage,storm,weekly_profiles=weekly) if profile else None
            self.projection_cache=(key,projected)
        projected=self.projection_cache[1]
        for period_key in ("day","month","year"):
            data[f"projected_savings_{period_key}"]=projected[period_key] if projected and d["fresh"] else None
        self.attributes["projected_savings_day"]=(projected or {})|{"profile_updated":self.profile_seen,"source":self.sources["load_entity"],"load_kwh_day":sum(profile)/1000 if profile else None,"status":"Ready" if projected and d["fresh"] else "Waiting for a full daily load profile, current rates and fresh telemetry"}
        self.attributes["recorded_savings_total"]={"since":self.recorded["since"],"method":"Measured operation; estimated tariff costs. Reference projections and legacy estimates excluded."}
        data["integrated_energy_in"]=self.ledger["energy_in"];data["integrated_energy_out"]=self.ledger["energy_out"]
        data["weather_alert_count"]=len(self.nws_alerts) if self.sources.get("nws_alert_zone") and time.time()-self.nws_seen<900 else None
        self.attributes["weather_alert_count"]={"events":self.nws_alerts,"last_successful_fetch":self.nws_seen,"source":"National Weather Service"}
        self.attributes["plan"]=asdict(plan)|{"automatic_switching":self.settings["automatic_enabled"],"assumed_capacity_kwh":self.settings["capacity_kwh"],"reserve_hold":self.reserve_hold}
        self.attributes["current_price"]={"source_url":PSEG_URL,"month":self.rate_month,"last_fetch":self.last_fetch,"delivery_year":2026,"account_adjustments_included":False}
        self.attributes["highest_cell"]={"positions":extreme["highest_positions"] if extreme else [],"ordering":"Selected source list, left to right"}
        self.attributes["lowest_cell"]={"positions":extreme["lowest_positions"] if extreme else [],"ordering":"Selected source list, left to right"}
        self.attributes["estimated_savings_total"]={"tracked_seconds":self.ledger["tracked_seconds"],"method":"Forward cash flow; excludes outages; all charging assumed grid-sourced; initial stored energy cost unknown"}
        self.async_set_updated_data(data)
        return d,plan,rates,period

    async def async_tick(self,_now=None):
        if self.tick_lock.locked() or self.stopped: return
        async with self.tick_lock:
            await self._async_tick(_now)

    async def _async_tick(self,_now=None):
        if self.stopped: return
        # Local charge inhibition must not wait for tariff/weather HTTP requests.
        await self._async_inhibit_charging(self.measurements())
        now=self.local_now()
        await self.fetch_context(now)
        if self.stopped: return
        d,plan,rates,period=self.recompute()
        if self.settings.get('thermal_enabled') and plan.decision=='Charge':
            self.thermal.started_window_end=self.data.get('thermal',{}).get('window_end')
        self.thermal.observe(now,d,self.settings,rates[period] if rates else None,plan.decision=='Cold-weather charge')
        # Stop permission is independent of manual holds, automatic scheduling,
        # economics and source-transition cooldown. Never switch output to do it.
        await self._async_inhibit_charging(d)
        tick=time.time()
        current=money_rates(d,self.settings,rates[period] if rates else None)
        if self.previous and current and 0<tick-self.last_tick<=90:
            # Left rule. Break intervals at source/mode/price/calendar changes; never backfill gaps.
            old,old_d,old_period,old_date=self.previous
            if old_period==period and old_date==now.date() and old_d["mode"]==d["mode"]:
                hours=(tick-self.last_tick)/3600
                for key,value in old.items():
                    amount=value*hours;self.ledger[key]+=amount
                    self.recorded[key]+=amount
                    if self.recorded["since"] is None: self.recorded["since"]=now.isoformat()
                    for datekey in (now.strftime("%Y-%m-%d"),now.strftime("%Y-%m"),now.strftime("%Y")):
                        item=self.ledger["periods"].setdefault(datekey,{})
                        item[key]=item.get(key,0)+amount
                        rec=self.recorded["periods"].setdefault(datekey,{})
                        rec[key]=rec.get(key,0)+amount
                self.ledger["tracked_seconds"]+=tick-self.last_tick
                self.recorded["tracked_seconds"]+=tick-self.last_tick
        if getattr(self,"previous_energy",None) and d["fresh"] and 0<tick-self.last_tick<=90:
            old=self.previous_energy;hours=(tick-self.last_tick)/3600
            self.ledger["energy_in"]+=old[0]/1000*hours;self.ledger["energy_out"]+=old[1]/1000*hours
        self.previous_energy=(d["charge_w"],d["discharge_w"]) if d["fresh"] else None
        self.previous=(current,d,period,now.date()) if current else None;self.last_tick=tick
        if d["fresh"]:
            self.average.append((tick,d["load_w"]))
        while self.average and tick-self.average[0][0]>86400: self.average.popleft()
        self.save();self.recompute()
        protection_hold=plan.decision=="Protection hold" and (d["mode"]!="Line" or d["priority"]!="SUB")
        if (self.settings["automatic_enabled"] and self.settings["switching_confirmed"]
            and not self.command_error and plan.desired_priority and (protection_hold or (
                not self.source_transfer and tick>=self.hold_until and tick-self.start_time>=90 and tick-self.last_switch>=300))):
            # Only two confirmed source preferences; never change BMS thresholds or output limits.
            try:
                if plan.desired_priority=="SUB":
                    await self.async_source("SUB",automatic=True,allow_charging=plan.decision in {"Recharge","Recover reserve","Charge","Keep ready","Cold-weather charge"})
                else:
                    await self.async_source(plan.desired_priority,automatic=True)
            except HomeAssistantError as err:
                LOGGER.error("Scheduling stopped after command failure: %s",err)

    def save(self):
        self.store.async_delay_save(self._saved_state,5)

    def _saved_state(self):
        return {"ledger":self.ledger,"recorded":self.recorded,"hold_until":self.hold_until,
                "command_error":self.command_error,"source_transfer":self.source_transfer,
                "source_intent":self.source_intent,"last_switch":self.last_switch,
                "charge_guard":self.charge_guard.saved(),"guard_stop_failed":self.guard_stop_failed,"reserve_hold":self.reserve_hold,
                "thermal":self.thermal.saved(),"thermal_source":self.sources.get('cold_temperature_entity')}

    async def _async_inhibit_charging(self,d):
        reason=self.charge_guard.evaluate(d,self.settings,time.time())
        # Scheduled stop permission is recalculated each tick. It is not a
        # protection latch and must never leak into future preview intervals.
        scheduled_stop=d.get('scheduled_charge_block',False)
        if (not reason and not scheduled_stop) or self.topics.get("control/charger_priority/state")==CHARGE_OFF: return
        if not d["fresh"] and time.time()-self.start_time<90: return
        if self.guard_stop_failed or self.lock.locked() or self.source_lock.locked(): return
        if not self.fresh_topic("status") or self.topics.get("status",{}).get("status")!="ready": return
        try:
            await self.async_control("charger_priority",CHARGE_OFF,automatic=True,charge_inhibit=True)
        except HomeAssistantError as err:
            self.guard_stop_failed=True
            LOGGER.error("Utility-charge inhibition failed; no automatic retries: %s",err)
            await self.store.async_save(self._saved_state())

    def local_now(self):
        now=dt_util.now()
        return now.astimezone(ZoneInfo("America/New_York")) if self.settings["price_source"]=="PSEG Rate 195" else now

    async def async_setting(self,key,value):
        if key=="automatic_enabled" and value and not self.settings["switching_confirmed"]:
            raise HomeAssistantError("Confirm both source transitions before enabling scheduling")
        self.settings[key]=value
        changed={key:value}
        if key=="switching_confirmed" and not value:
            self.settings["automatic_enabled"]=False
            changed["automatic_enabled"]=False
        self.hass.config_entries.async_update_entry(self.entry,options=dict(self.entry.options)|changed)
        self.previous=None
        self.recompute()

    async def async_load_setup(self,entity,days):
        from .config_flow import validate_sources
        from homeassistant.helpers import entity_registry as er
        record=er.async_get(self.hass).async_get(entity)
        bms=er.async_get(self.hass).async_get(self.sources.get('soc_entity',''))
        derived=entity.startswith(('sensor.it_closet_battery_','sensor.daly_bms_')) or entity in {self.sources.get('charge_power_entity'),self.sources.get('discharge_power_entity')}
        derived |= bool(record and (record.platform==DOMAIN or (bms and bms.device_id and record.device_id==bms.device_id)))
        if days not in HISTORY_DAYS or not entity.startswith('sensor.') or derived or validate_sources(self.hass,{'load_entity':entity}):
            raise HomeAssistantError('Choose a source power sensor in W or kW, and 7, 14, 30 or 90 days of history')
        if self.source_lock.locked() or self.pending or self.source_transfer:
            raise HomeAssistantError('Wait for the current source change to finish before changing learning settings')
        changed=entity!=self.sources.get('load_entity')
        options=dict(self.entry.options,load_entity=entity,learning_history_days=int(days))
        if changed:
            options.update(load_heartbeat_topic='',commissioned=False,automatic_enabled=False)
        self.hass.config_entries.async_update_entry(self.entry,options=options)
        if not changed:
            self.settings['learning_history_days']=int(days)
            self.profile_attempt=0;self.profile_seen=0;self.load_profile=[]
            self.learning={'status':'Learning','history_days':days,'recorded_hours':0,'available_days':0}
            self.projection_cache=(None,None);self.recompute()
        return changed

    async def async_source(self,value,automatic=False,allow_charging=True):
        """Coordinate charging permission and output preference; verify real transfer."""
        if value not in {"SBU","SUB"}: raise HomeAssistantError("Only confirmed battery/grid source actions are supported")
        if self.source_lock.locked(): raise HomeAssistantError("Another source transition is in progress")
        if self.command_error: raise HomeAssistantError("A command fault is latched; review Advanced before another source request")
        # Repeated taps are idempotent: preserve the original observation and
        # deadline rather than sending the same preference again.
        if self.source_transfer and self.source_transfer["value"]==value: return
        d=self.measurements()
        safe_grid_hold=value=="SUB" and d.get("bridge_ready") and d.get("has_bms_alarm")
        if not d["fresh"] or (not d["healthy"] and not safe_grid_hold): raise HomeAssistantError("Fresh healthy telemetry is required before source switching")
        blocked=self.charge_guard.evaluate(d,self.settings,time.time())
        if value=="SUB" and allow_charging and not blocked:
            for key in ("utility_charge_current","total_charge_current"):
                amps=numeric(str(self.topics.get(f"control/{key}/state","")).split(" ")[0])
                if amps is None or amps>min(30,self.settings["charge_cap_a"]):
                    raise HomeAssistantError("Read or lower charging limits before permitting utility charging")
        options=self.topics.get("control/charger_priority/attributes",{}).get("allowed_values",[])
        candidates=(CHARGE_OFF,"Code 02 (label unconfirmed)") if value=="SBU" or blocked or not allow_charging else (CHARGE_ON,)
        charging=next((v for v in candidates if v in options),None)
        if charging is None: raise HomeAssistantError("Bridge does not advertise the commissioned charging-source mode")
        if automatic and self.source_transfer and not safe_grid_hold: return
        async with self.source_lock:
            # An explicit new source request supersedes the old observation.
            self.source_transfer=None
            self.source_intent={"value":value,"charging":charging}
            await self.store.async_save(self._saved_state())
            try:
                await self.async_control("charger_priority",charging,automatic=automatic,source_transaction=True)
                await self.async_control("output_priority",value,automatic=automatic,source_transaction=True)
            except HomeAssistantError as err:
                self.command_error=str(err)
                self.source_intent=None
                await self.store.async_save(self._saved_state())
                raise
            self.source_intent=None
            await self.store.async_save(self._saved_state())

    async def async_control(self,key,value,automatic=False,source_transaction=False,charge_inhibit=False):
        inhibit=charge_inhibit and key=="charger_priority" and value==CHARGE_OFF
        if charge_inhibit and not inhibit: raise HomeAssistantError("Inhibit path only permits utility charging off")
        if self.source_lock.locked() and not source_transaction:
            raise HomeAssistantError("A coordinated source transition is in progress")
        if self.stopped: raise HomeAssistantError("Integration is unloaded; commands are disabled")
        if not mqtt.is_connected(self.hass): raise HomeAssistantError("MQTT is disconnected; no command was sent")
        from .select import CATALOG
        if key not in CATALOG: raise HomeAssistantError("Control outside verified registry")
        metadata=self.topics.get(f"control/{key}/attributes",{})
        options=metadata.get("allowed_values",[])
        if value not in options: raise HomeAssistantError("Value not advertised by the verified bridge")
        if key=="charger_priority" and value!=CHARGE_OFF:
            reason=self.charge_guard.evaluate(self.measurements(),self.settings,time.time())
            if reason: raise HomeAssistantError("Utility charging blocked: "+reason)
            for limit in ("utility_charge_current","total_charge_current"):
                amps=numeric(str(self.topics.get(f"control/{limit}/state","")).split(" ")[0])
                if amps is None or amps>min(30,self.settings["charge_cap_a"]):
                    raise HomeAssistantError("Read or lower charging limits before permitting utility charging")
        if key in {"utility_charge_current","total_charge_current"}:
            number=numeric(value.split()[0])
            if number is None or number>min(30,self.settings["charge_cap_a"]):
                raise HomeAssistantError("Battery charge ceiling would be exceeded")
        if key=="output_priority" and value=="SUB" and self.topics.get("control/charger_priority/state")!=CHARGE_OFF:
            for limit in ("utility_charge_current","total_charge_current"):
                current=self.topics.get(f"control/{limit}/state","")
                amps=numeric(current.split()[0]) if current else None
                if amps is None or amps>min(30,self.settings["charge_cap_a"]):
                    raise HomeAssistantError("Read or lower battery charging limits before grid charging")
            if automatic and self.topics.get("control/charger_priority/state") not in {CHARGE_ON,CHARGE_OFF}:
                raise HomeAssistantError("Automatic grid operation requires a confirmed charging-source mode")
        if not self.fresh_topic("status") or self.topics.get("status",{}).get("status")!="ready" or (self.command_error and not inhibit):
            raise HomeAssistantError("Bridge is not ready, or a command fault is latched")
        if self.lock.locked(): raise HomeAssistantError("Another command is awaiting verification")
        async with self.lock:
            if key=="output_priority" or (key=="charger_priority" and not inhibit): self.source_transfer=None
            already=automatic and self.topics.get(f"control/{key}/state")==value
            self.pending=self.hass.loop.create_future();self.pending_key=key;self.pending_value=value;self.command_time=time.time()
            if not inhibit: self.transfer_status="Requesting source preference" if key=="output_priority" else ""
            self.recompute()
            try:
                if not already:
                    await mqtt.async_publish(self.hass,self.sources["mqtt_root"]+f"/control/{key}/set",value,qos=0,retain=False)
                    await asyncio.wait_for(self.pending,50)
                    for _ in range(12):
                        if self.topics.get(f"control/{key}/state")==value: break
                        await asyncio.sleep(.5)
                    else: raise HomeAssistantError("Acknowledgement arrived without matching settings readback")
                if key=="output_priority" and value in {"SBU","SUB"}:
                    # ACK/readback completes the service call. Observe actual
                    # power transfer independently, without blocking HA for minutes.
                    self.source_transfer={"value":value,"not_before":None if already else self.command_time,
                                          "deadline":time.time()+SOURCE_TRANSFER_WINDOW}
                    self._update_source_transfer(self.measurements())
                if not inhibit: self.last_switch=time.time()
                if not automatic: self.hold_until=time.time()+self.settings["manual_override_minutes"]*60
            except (TimeoutError,HomeAssistantError) as err:
                self.command_error=str(err) or "Command verification timed out"
                self.transfer_status=""
                raise HomeAssistantError(self.command_error) from err
            finally:
                if self.pending and not self.pending.done(): self.pending.cancel()
                self.pending=None;self.pending_key=None;self.pending_value=None;self.save();self.recompute()

    def _update_source_transfer(self,d):
        """Observe fresh telemetry only. Never retransmit a source command."""
        transfer=self.source_transfer
        if not transfer: return
        expected="Battery" if transfer["value"]=="SBU" else "Line"
        raw=self.topics.get("raw_readings",{}).get("HSTS",{})
        age=numeric(raw.get("age_seconds"))
        sampled=self.received.get("raw_readings",0)-(age if age is not None else 999999)
        pv=d.get("inverter_pv_power")
        charge_ok=expected!="Battery" or pv is None or pv>5 or (d["charge_w"] is not None and d["charge_w"]<=5)
        mode_permitted=d["healthy"] or (expected=="Line" and d.get("bridge_ready"))
        if (d["fresh"] and mode_permitted and charge_ok and d["mode"]==expected
            and (transfer["not_before"] is None or sampled>=transfer["not_before"])):
            self.transfer_status=f"{expected if expected=='Battery' else 'Utility'} operation verified"
            self.source_transfer=None
            self.save()
        elif time.time()>=transfer["deadline"] and not d["fresh"] and time.time()-self.start_time<90:
            # On a restart after the deadline, wait briefly for live telemetry
            # before deciding whether the inverter already completed transfer.
            self.transfer_status="Waiting for fresh telemetry to confirm inverter transfer"
        elif time.time()>=transfer["deadline"]:
            self.command_error=f"{expected} transfer not verified after 12 minutes; actual source {d['mode']}. Check inverter conditions in Advanced. No retry sent."
            self.transfer_status=""
            self.source_transfer=None
            self.save()
        else:
            self.transfer_status=f"Waiting for inverter transfer to {expected.lower()}; actual source {d['mode']}"

    async def async_close(self):
        self.stopped=True
        if self.refresh_handle:
            self.refresh_handle.cancel();self.refresh_handle=None
        if self.pending and not self.pending.done(): self.pending.cancel()
        await self.store.async_save(self._saved_state())
