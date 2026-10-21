"""MQTT discovery for the verified registry; no raw-command topic."""
import datetime, json, os, queue, threading, time
from decimal import Decimal
import paho.mqtt.client as mqtt
from core import CONTROLS, BY_NAME, VERIFIED_VALUES, EXPANDED_RANGES, BATTERY_CHARGE_CAP_A, AC_SITE_BUDGET_A
from telemetry import VERSION, SENSORS, CONTROL_NAMES, decoded
ROOT=os.environ.get("MQTT_ROOT","hpvinv09/inverter")
DEVICE={"identifiers":["hpvinv09_unit"],"name":"HPVINV09 Local Inverter","manufacturer":"DATOUBOSS / MFUZOP","model":"Standalone local inverter bridge","sw_version":VERSION}
def legacy_label(c,v):
 if c.name=="output_priority":return {"00":"SUB","01":"SBU","02":"Code 02 (label unconfirmed)"}[v]
 if c.name=="charger_priority":return {"01":"SNU (solar + utility)","02":"Solar only (utility charging disabled)"}.get(v,"Code "+v+" (label unconfirmed)")
 if c.prefix.startswith("toggle:"):return "Enabled" if v=="1" else "Disabled"
 return v+(" "+c.unit if c.unit else "")

def label(c,v):
 if c.name in ('output_priority','charger_priority') or c.prefix.startswith('toggle:'):
  return legacy_label(c,v)
 # Padding belongs to serial messages, never user-facing quantities.
 number=format(Decimal(v).normalize(),'f')
 return number+(" "+c.unit if c.unit else "")

def option_value(c,requested):
 if c.name=="charger_priority" and requested=="Code 02 (label unconfirmed)":return "02"
 values=[v for v in c.values if requested in (label(c,v),legacy_label(c,v))]
 if len(values)!=1:raise ValueError('Value outside allowed options or site cap')
 return values[0]

from control_metadata import CONTROL_DETAILS as CURRENT_DETAILS

def canonical(c,value):
 for v in c.values:
  if Decimal(v)==Decimal(value):return v
 return None
class MqttBridge:
 def __init__(self,manager,audit,stop):
  self.manager=manager;self.audit=audit;self.stop=stop;self.jobs=queue.Queue(maxsize=1)
  self.client=mqtt.Client(client_id="hpvinv09-local-bridge",clean_session=True)
  username=os.environ.get("MQTT_USERNAME")
  if username:self.client.username_pw_set(username,os.environ.get("MQTT_PASSWORD",""))
  self.client.will_set(ROOT+"/availability","offline",qos=1,retain=True)
  self.client.on_connect=self.connected;self.client.on_message=self.message
  self.client.reconnect_delay_set(2,30);self.client.max_queued_messages_set(128)
  self.last_state=None
 def pub(self,topic,data,retain=False):
  return self.client.publish(topic,json.dumps(data) if not isinstance(data,str) else data,qos=1,retain=retain)
 def connected(self,client,userdata,flags,rc):
  if rc!=0:self.audit("mqtt_connection_failed",code=rc);return
  self.pub(ROOT+"/availability","offline",True);self.pub(ROOT+"/writes_available","offline",True)
  self.discovery()
  client.subscribe(ROOT+"/control/+/set",qos=0)
  client.subscribe("homeassistant/status",qos=0)
 def discovery(self):
  prefix=os.environ.get("DISCOVERY_PREFIX","homeassistant")
  for c in CONTROLS:
   key=c.name
   config={"name":CONTROL_NAMES.get(key,key.replace("_"," ").title()),"unique_id":"hpvinv09_"+key,"device":DEVICE,
    "command_topic":ROOT+"/control/"+key+"/set","state_topic":ROOT+"/control/"+key+"/state",
    "options":[label(c,v) for v in c.values],"availability":[{"topic":ROOT+"/availability"},{"topic":ROOT+"/writes_available"},{"topic":ROOT+"/control/"+key+"/availability"}],
    "availability_mode":"all","qos":0,"retain":False,"entity_category":"config",
    "json_attributes_topic":ROOT+"/control/"+key+"/attributes"}
   self.pub(prefix+"/select/hpvinv09/"+key+"/config",config,True)
   self.pub(ROOT+"/control/"+key+"/attributes",{"verified_values":[label(c,v) for v in VERIFIED_VALUES[key]],"allowed_values":[label(c,v) for v in c.values],"wire_verified_values":list(VERIFIED_VALUES[key]),"range_basis":"manual and site cap" if key in EXPANDED_RANGES else "device-tested values; full range unresolved","note":c.note,"protocol_command":c.prefix,"battery_charge_cap_a":BATTERY_CHARGE_CAP_A,"ac_site_budget_a":AC_SITE_BUDGET_A,"ac_budget_hardware_enforced":False,"automatic_load_aware_charging":False,**CURRENT_DETAILS.get(key,{})},True)
  for key,name,block,index,unit,device_class in SENSORS:
   config={"name":name,"unique_id":"hpvinv09_telemetry_"+key,
    "device":DEVICE,"state_topic":ROOT+"/telemetry/"+key,"unit_of_measurement":unit,"state_class":"measurement",
    "expire_after":60,"availability_topic":ROOT+"/availability"}
   if device_class:config['device_class']=device_class
   self.pub(prefix+"/sensor/hpvinv09/telemetry_"+key+"/config",config,True)
  self.pub(prefix+"/sensor/hpvinv09/bridge_status/config",{
   "name":"Bridge status","unique_id":"hpvinv09_bridge_status","device":DEVICE,
   "state_topic":ROOT+"/status","value_template":"{{ value_json.status }}",
   "json_attributes_topic":ROOT+"/status","entity_category":"diagnostic",
   "availability_topic":ROOT+"/availability"},True)
  self.pub(prefix+"/sensor/hpvinv09/last_command/config",{
   "name":"Last command","unique_id":"hpvinv09_last_command","device":DEVICE,
   "state_topic":ROOT+"/last_result","value_template":"{{ value_json.status }}",
   "json_attributes_topic":ROOT+"/last_result","entity_category":"diagnostic",
   "availability_topic":ROOT+"/availability"},True)
  # Expose raw diagnostics without guessing meanings of packed status flags.
  diagnostics=[
   ('status_code','Reported status code','HSTS',"{{ value_json.HSTS.ascii[1:].split()[0] }}"),
   ('operating_mode','Operating mode','HSTS',"{% set c=value_json.HSTS.ascii[1:].split()[1][0] %}{{ {'L':'Line','B':'Battery'}.get(c,'Code '+c) }}"),
   ('status_details','Inverter status details','HSTS',"{{ value_json.HSTS.ascii|trim }}"),
   ('bms_data_status','Inverter BMS data status','HBMS1',"{% set a=value_json.HBMS1.ascii[1:].split() %}{{ 'Not populated' if a[0]=='00' else 'Data present (link unverified)' }}"),
  ]
  for key,name,block,template in diagnostics:
   cfg={'name':name,'unique_id':'hpvinv09_diag_'+key,'device':DEVICE,
    'state_topic':ROOT+'/raw_readings','value_template':template,'expire_after':60,
    'availability':[{'topic':ROOT+'/availability'},
     {'topic':ROOT+'/raw_readings','value_template':"{{ 'online' if value_json."+block+".age_seconds <45 else 'offline' }}"}],
    'availability_mode':'all','icon':'mdi:information-outline',
    'json_attributes_topic':ROOT+'/raw_readings',
    'json_attributes_template':"{{ {'source_command':'"+block+"','raw_reply':value_json."+block+".ascii,'age_seconds':value_json."+block+".age_seconds,'interpretation':'Raw protocol status; detailed fault mapping unverified'}|tojson }}"}
   self.pub(prefix+'/sensor/hpvinv09/diag_'+key+'/config',cfg,True)
 def result(self,result):
  result=dict(result)
  result["timestamp"]=datetime.datetime.now(datetime.timezone.utc).isoformat()
  self.pub(ROOT+"/last_result",result,True)
  self.audit("mqtt_command_result",**result)
 def message(self,client,userdata,msg):
  if msg.topic=="homeassistant/status":
   if msg.payload==b"online":self.discovery()
   return
  if msg.retain:
   self.audit("mqtt_command_rejected",reason="Retained command",topic=msg.topic);self.result({"status":"rejected","error":"Retained commands are not accepted","topic":msg.topic});return
  try:
   key=msg.topic.split("/")[-2];c=BY_NAME[key];requested=msg.payload.decode("utf-8")
   value=option_value(c,requested)
   # No deferred writes while offline or while another command is pending.
   if not self.available(self.manager.state()):raise ValueError("Backend unavailable")
   self.jobs.put_nowait((key,value,time.monotonic()))
  except Exception as ex:
   self.audit("mqtt_command_rejected",reason=str(ex),topic=msg.topic)
   self.result({"status":"rejected","error":str(ex) or "Another command is queued","topic":msg.topic})
 def controls_available(self,s):
  # A normal transaction is busy, not disconnected. Keep confirmed values visible.
  if getattr(self,'worker_thread',None) is not None and not self.worker_thread.is_alive():return False
  return bool(s.get("ready") and not s.get("fault") and not s.get("write_lock") and
   (not s.get("write_latch") or s.get("inflight")) and
   "HBAT" in s.get("readings",{}) and s["readings"]["HBAT"]["age_seconds"]<45)
 def available(self,s):
  # Command admission remains exclusive; never queue a conflicting write.
  return self.controls_available(s) and not s.get("write_latch") and not s.get("inflight")
 def worker(self):
  while not self.stop.is_set():
   try:key,value,received=self.jobs.get(timeout=.5)
   except queue.Empty:continue
   try:
    if time.monotonic()-received>2:raise ValueError("Expired command")
    ticket=self.manager.submit(key,value)
    result=ticket.result if ticket.done.wait(45) else {"status":"pending","control":key}
   except Exception as ex:result={"status":"rejected","control":key,"error":str(ex)}
   self.result(result)
 def publish_state(self,s):
  readings=s.get("readings",{})
  online=bool(s.get("ready") and not s.get("fault") and "HBAT" in readings and readings["HBAT"]["age_seconds"]<45)
  self.pub(ROOT+"/availability","online" if online else "offline",True)
  self.pub(ROOT+"/writes_available","online" if self.controls_available(s) else "offline",True)
  self.pub(ROOT+"/status",{"status":"write_in_progress" if online and s.get("inflight") else "ready" if self.available(s) else "unavailable",
   "fault":s.get("fault"),"write_latch":s.get("write_latch"),"generation":s.get("generation"),
   "timestamp":datetime.datetime.now(datetime.timezone.utc).isoformat()},True)
  if online:
   # Do not publish partially refreshed settings before transaction verification.
   if not s.get("inflight"):
    for item in s["controls"]:
     c=BY_NAME[item["name"]];v=canonical(c,item["current"])
     self.pub(ROOT+"/control/"+c.name+"/availability","online" if v is not None else "offline",True)
     if v is not None:self.pub(ROOT+"/control/"+c.name+"/state",label(c,v),True)
   self.pub(ROOT+"/raw_readings",readings)
   data=decoded(s)
   for key,*_ in SENSORS:
    self.pub(ROOT+"/telemetry/"+key,str(data[key]) if key in data else 'None')
 def publish(self):
  while not self.stop.wait(3):
   try:self.publish_state(self.manager.state())
   except Exception as ex:self.audit("mqtt_publish_error",error=str(ex))
 def start(self):
  self.client.connect_async(os.environ["MQTT_HOST"],int(os.environ.get("MQTT_PORT","1883")),60)
  self.client.loop_start()
  self.worker_thread=threading.Thread(target=self.worker,daemon=True)
  self.publisher_thread=threading.Thread(target=self.publish,daemon=True)
  self.worker_thread.start();self.publisher_thread.start()
 def close(self):
  try:self.pub(ROOT+"/availability","offline",True).wait_for_publish(2)
  except Exception:pass
  self.client.disconnect();self.client.loop_stop()
