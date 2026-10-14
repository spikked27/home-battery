"""Exclusive serial worker, audited transactions and fresh telemetry cache."""
import copy, datetime, fcntl, json, os, pathlib, queue, subprocess, threading, time
from core import *
LAB=pathlib.Path(os.environ.get('INVERTER_LAB','/var/lib/home-battery'))
PORT=os.environ.get("INVERTER_PORT", "")
READS={"QPRTL","HIMSG1",*COUNTS}
POLL=("HGRID","HOP","HBAT","HPV","HTEMP","HSTS","HEEP1","HEEP2","HBMS1","HBMS2")
class Audit:
 def __init__(self,path):
  self.file=open(path,"a",buffering=1);self.lock=threading.Lock()
 def __call__(self,event,**kw):
  with self.lock:
   self.file.write(json.dumps({"timestamp":datetime.datetime.now(datetime.timezone.utc).isoformat(),"event":event,**kw})+"\n")
 def close(self):self.file.close()
class PollPreempted(Exception):pass
class SerialBackend:
 def __init__(self,audit,interval=2.1,device_path=None):
  import serial
  self.audit=audit;self.last=0;self.interval=interval;self.port=None;self.interruptible=False;self.should_preempt=lambda:False
  self.lock=open(LAB/"controller.lock","a")
  try:
   fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
   self.device=os.path.realpath(device_path or PORT)
   if not os.path.exists(self.device):raise RuntimeError("FTDI missing")
   if subprocess.run(["mountpoint","-q",self.device]).returncode==0:raise RuntimeError("Device already overlaid")
   owners=subprocess.run((["sudo","-n"] if os.geteuid()!=0 else [])+["fuser",self.device],capture_output=True,text=True,timeout=5)
   if owners.returncode!=1:raise RuntimeError("Port occupied or ownership check failed")
   self.port=serial.Serial(port=None,baudrate=2400,timeout=.1,write_timeout=2,exclusive=True,xonxoff=False,rtscts=False,dsrdtr=False)
   self.port.dtr=False;self.port.rts=False;self.port.port=self.device;self.port.open()
   fcntl.ioctl(self.port.fileno(),0x540C)
  except BaseException:
   self.close();raise
 def query(self,cmd):
  if cmd in READS:request=cmd.encode()+b"\r"
  else:
   locate_backend(cmd);request=frame(cmd,True)
  while self.interval-(time.monotonic()-self.last)>0:
   if self.interruptible and self.should_preempt():raise PollPreempted()
   time.sleep(min(.05,max(0,self.interval-(time.monotonic()-self.last))))
  if self.interruptible and self.should_preempt():raise PollPreempted()
  stale=self.port.read(self.port.in_waiting)
  if stale:self.audit("stale_serial_bytes",raw_hex=stale.hex())
  start=time.monotonic();raw=b""
  self.audit("backend_request",command=cmd,raw_hex=request.hex())
  try:
   self.port.write(request);self.port.flush()
   while time.monotonic()-start<3 and len(raw)<4096:
    raw+=self.port.read(1)
    if raw.endswith(b"\r"):break
   return raw
  finally:
   self.last=time.monotonic()
   self.audit("backend_response",command=cmd,raw_hex=raw.hex(),elapsed_ms=round((self.last-start)*1000,2))
 def close(self):
  if self.port:self.port.close()
  if getattr(self,"lock",None):self.lock.close()
class ReplayBackend:
 def __init__(self,fixtures,audit):
  self.raw={k:bytes.fromhex(v) for k,v in fixtures.items()};self.audit=audit
 def query(self,cmd):
  self.audit("replay_request",command=cmd)
  if cmd in READS:return self.raw[cmd]
  c,v=locate_backend(cmd)
  s={k:parse(self.raw[k],k) for k in ("HEEP1","HEEP2")}
  for k,values in expected(c,s,v).items():self.raw[k]=("("+ " ".join(values)+"\r").encode()
  return ACK
 def close(self):pass
class Ticket:
 def __init__(self,c,value,cached_preflight=False):
  self.control=c;self.value=value;self.cached_preflight=cached_preflight;self.accepted=threading.Event();self.done=threading.Event()
  self.result={"status":"queued","control":c.name,"value":value}
class Engine:
 def __init__(self,backend,audit):
  self.backend=backend;self.audit=audit;self.cache={};self.lock=threading.RLock()
  self.jobs=queue.Queue(maxsize=1);self.stop=threading.Event();self.ready=threading.Event()
  self.fault=None;self.write_lock=None;self.inflight=None;self.thread=None
  if isinstance(backend,SerialBackend):backend.should_preempt=lambda:not self.jobs.empty()
 def read(self,cmd):
  raw=self.backend.query(cmd)
  if cmd in COUNTS:parse(raw,cmd)
  with self.lock:self.cache[cmd]=(raw,time.monotonic())
  return raw
 def snapshot(self):
  with self.lock:return {k:parse(self.cache[k][0],k) for k in ("HEEP1","HEEP2")}
 def refresh_settings(self):
  for k in ("HEEP1","HEEP2"):self.read(k)
  s=self.snapshot();validate_snapshot(s);return s
 def start(self):
  self.thread=threading.Thread(target=self.run,name="serial-owner",daemon=True);self.thread.start()
 def run(self):
  try:
   if self.read("QPRTL")!=IDENTITY or self.read("HIMSG1")!=FIRMWARE:raise RuntimeError("Unvalidated identity/firmware")
   for k in POLL:self.read(k)
   validate_snapshot(self.snapshot());self.ready.set()
   while not self.stop.is_set():
    try:job=self.jobs.get_nowait()
    except queue.Empty:
     try:
      if isinstance(self.backend,SerialBackend):self.backend.interruptible=True
      self.read(self.next_poll())
     except PollPreempted:continue
     finally:
      if isinstance(self.backend,SerialBackend):self.backend.interruptible=False
     if isinstance(self.backend,ReplayBackend):self.stop.wait(.1)
     continue
    self.change(job)
  except Exception as e:
   self.fault=str(e);self.audit("backend_fault",error=str(e))
  finally:
   self.ready.set()
   with self.lock:
    if self.inflight and not self.inflight.done.is_set():
     self.inflight.result={"status":"failed","error":self.fault or "stopped"}
     self.inflight.accepted.set();self.inflight.done.set();self.inflight=None
 def next_poll(self):
  # Settings refreshed by writes already count as polls. Refresh oldest telemetry
  # first instead of revisiting those blocks while other data ages out.
  with self.lock:return min(POLL,key=lambda key:self.cache.get(key,(None,0))[1])
 def refresh_aging_telemetry(self):
  # Reserve room for the five serial exchanges in a fully verified write.
  # Repeated settings changes must not starve ordinary telemetry.
  keys=[key for key in POLL if key not in ('HEEP1','HEEP2')]
  while not self.stop.is_set():
   with self.lock:
    key=min(keys,key=lambda k:self.cache.get(k,(None,0))[1])
    age=time.monotonic()-self.cache.get(key,(None,0))[1]
   if age<25:return
   self.read(key)
  raise RuntimeError('Stopped before settings transaction')
 def submit(self,name,value,cached_preflight=False):
  c=BY_NAME[name];value=str(value);c.command(value)
  with self.lock:
   if self.fault or not self.ready.is_set() or self.stop.is_set():raise ValueError("Backend unavailable: "+str(self.fault))
   if self.write_lock:raise ValueError("Writes locked: "+str(self.write_lock))
   if self.inflight:raise ValueError("Another write is in progress")
   if cached_preflight:
    if any(time.monotonic()-self.cache[k][1]>35 for k in ("HEEP1","HEEP2")):raise ValueError("Settings cache too old; retry after refresh")
    validate_snapshot(self.snapshot())
   t=Ticket(c,value,cached_preflight);self.inflight=t;self.jobs.put_nowait(t);return t
 def change(self,t):
  c,v=t.control,t.value
  original_interval=getattr(self.backend,"interval",None)
  try:
   # Native writes use a recent validated baseline; promptly forward only the real ACK.
   # Dependent settings reads wait for complete readback. Local writes use fresh preflight.
   self.refresh_aging_telemetry()
   if t.cached_preflight:
    if isinstance(self.backend,SerialBackend):self.backend.interval=.05
    with self.lock:
     if any(time.monotonic()-self.cache[k][1]>35 for k in ("HEEP1","HEEP2")):raise ValueError("Configuration baseline expired")
     before=self.snapshot();validate_snapshot(before)
    if same(c,before,v):before=self.refresh_settings()
   else:before=self.refresh_settings()
   if same(c,before,v):
    t.result={"status":"verified_no_change","control":c.name,"value":v}
   else:
    target=expected(c,before,v);wire=command(c,v)
    self.audit("write_plan",control=c.name,value=v,command=wire,before=before,expected=target)
    reply=self.backend.query(wire)
    if reply==NAK:
     after=self.refresh_settings()
     if after!=before:raise RuntimeError('NAK accompanied by changed settings; investigate')
     t.result={'status':'rejected_unchanged','control':c.name,'value':v,'error':'Inverter rejected this value; full settings readback unchanged'}
     self.audit('write_result',**t.result)
     return
    if reply!=ACK:raise RuntimeError("Inverter did not ACK")
    t.result={"status":"acknowledged_pending_readback","control":c.name,"value":v}
    t.accepted.set()
    after=self.refresh_settings()
    if after!=target:
     self.fault="Unexpected configuration readback; writes locked pending investigation"
     raise RuntimeError(self.fault)
    t.result={"status":"verified","control":c.name,"value":v}
   self.audit("write_result",**t.result)
  except Exception as e:
   t.result={"status":"failed","control":c.name,"value":v,"error":str(e)}
   # Never silently rollback over a possible manual change or retry an ambiguous write.
   self.fault=str(e);self.audit("write_failed",**t.result)
  finally:
   if original_interval is not None:self.backend.interval=original_interval
   with self.lock:self.inflight=None
   t.accepted.set();t.done.set()
 def state(self):
  with self.lock:
   now=time.monotonic()
   return {"mode":"replay" if isinstance(self.backend,ReplayBackend) else "live","ready":self.ready.is_set(),"fault":self.fault,
     "write_lock":self.write_lock,"inflight":self.inflight.result if self.inflight else None,
     "readings":{k:{"raw_hex":raw.hex(),"ascii":raw.decode("ascii",errors="backslashreplace"),"age_seconds":round(now-ts,2)} for k,(raw,ts) in self.cache.items()},
     "controls":[{**dataclasses.asdict(c),"current":c.read(self.snapshot()) if "HEEP1" in self.cache and "HEEP2" in self.cache else None} for c in CONTROLS]}
 def close(self):
  self.stop.set()
  if self.thread:self.thread.join(timeout=30)
  if self.thread and self.thread.is_alive():raise RuntimeError("Worker has not stopped")
  self.backend.close()
