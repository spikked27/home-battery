"""Freshness-checked telemetry using previously established field mappings."""
import math
from core import parse
VERSION='2026.10.31.1'
# key, name, block, zero-based field, unit, Home Assistant device class
SENSORS=[
 ('grid_voltage','Utility voltage','HGRID',0,'V','voltage'),
 ('grid_frequency','Utility frequency','HGRID',1,'Hz','frequency'),
 ('output_voltage','AC output voltage','HOP',0,'V','voltage'),
 ('output_frequency','AC output frequency','HOP',1,'Hz','frequency'),
 ('output_apparent_power','AC apparent power','HOP',2,'VA','apparent_power'),
 ('output_power','AC output power','HOP',3,'W','power'),
 ('output_load','Inverter load','HOP',4,'%',None),
 ('battery_voltage','Battery voltage from inverter','HBAT',1,'V','voltage'),
 ('battery_soc','Battery SOC from inverter','HBAT',2,'%','battery'),
 ('battery_charge_current','Battery charging current from inverter','HBAT',3,'A','current'),
 ('battery_discharge_current','Battery discharging current from inverter','HBAT',4,'A','current'),
 ('pv_voltage','Solar input voltage','HPV',0,'V','voltage'),
 ('pv_current','Solar input current','HPV',1,'A','current'),
 ('pv_power','Solar input power','HPV',2,'W','power'),
 ('inverter_temperature','Inverter temperature','HTEMP',1,'°C','temperature'),
]
from control_metadata import CONTROL_NAMES

def decoded(state):
 if not state.get('ready') or state.get('fault'):return {}
 result={}
 for key,name,block,index,unit,device in SENSORS:
  try:
   item=state['readings'][block]
   if not 0<=item['age_seconds']<45:continue
   value=float(parse(bytes.fromhex(item['raw_hex']),block)[index])
   if not math.isfinite(value) or value<0:continue
   result[key]=value
  except (KeyError,ValueError,IndexError,TypeError):continue
 return result
