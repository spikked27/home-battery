#!/usr/bin/env python3
"""Direct inverter owner: no SolarAssistant, PTY, bind mount or cloud dependency."""
import datetime,fcntl,gzip,json,logging,logging.handlers,os,pathlib,pwd,shutil,signal,socket,threading,time
from engine import Engine,SerialBackend
from mqtt_bridge import MqttBridge
from telemetry import VERSION
LAB=pathlib.Path(os.environ.get('INVERTER_LAB','/var/lib/home-battery'))
STATE=LAB/'standalone/state'
# Preserve the observer's API address so its ongoing log is uninterrupted.
SOCK=STATE/'control.sock'

def atomic(path,value):
 temp=path.with_suffix('.tmp')
 with temp.open('w') as f:
  json.dump(value,f,indent=2);f.flush();os.fsync(f.fileno())
 temp.replace(path)
 descriptor=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(descriptor)
 finally:os.close(descriptor)

class ArchiveHandler(logging.handlers.RotatingFileHandler):
 def doRollover(self):
  if self.stream:self.stream.close();self.stream=None
  src=pathlib.Path(self.baseFilename)
  archive=src.parent/'archives';archive.mkdir(exist_ok=True)
  dest=archive/(datetime.datetime.now(datetime.timezone.utc).strftime('traffic_%Y%m%dT%H%M%S%fZ')+'.jsonl.gz')
  with src.open('rb') as a,gzip.open(dest,'wb') as b:shutil.copyfileobj(a,b)
  src.unlink()
  self.stream=self._open()

class Audit:
 def __init__(self):
  self.lock=threading.RLock();self.latch=STATE/'write_fault.json'
  self.logger=logging.getLogger('standalone-inverter');self.logger.setLevel(logging.INFO);self.logger.propagate=False
  self.handler=ArchiveHandler(STATE/'traffic.jsonl',maxBytes=2_000_000,backupCount=1)
  self.handler.setFormatter(logging.Formatter('%(message)s'));self.logger.addHandler(self.handler)
 def __call__(self,event,**data):
  entry={"timestamp":datetime.datetime.now(datetime.timezone.utc).isoformat(),"event":event,**data}
  with self.lock:
   if event in ('write_plan','write_failed'):atomic(self.latch,entry)
   self.logger.info(json.dumps(entry))
   if event=='write_result' and data.get('status') in ('verified','verified_no_change','rejected_unchanged') and self.latch.exists():self.latch.unlink()
 def locked(self):return self.latch.exists()

class Manager:
 def __init__(self,audit,stop):
  self.audit=audit;self.stop=stop;self.engine=None;self.lock=threading.RLock()
  self.error='Starting';self.generation=0;self.reconnect=threading.Event()
 def run(self):
  while not self.stop.is_set():
   backend=engine=None
   try:
    if shutil.disk_usage(STATE).free<100_000_000:raise RuntimeError('Insufficient space for audit trail')
    backend=SerialBackend(self.audit)
    engine=Engine(backend,self.audit)
    if self.audit.locked():engine.write_lock='Unresolved prior transaction; inspect state/write_fault.json'
    with self.lock:self.engine=engine
    engine.start()
    while not engine.ready.wait(.5):
     if self.stop.is_set():break
    if engine.fault:raise RuntimeError(engine.fault)
    self.error=None;self.generation+=1
    self.audit('backend_connected',generation=self.generation,version=VERSION)
    while not self.stop.wait(.5):
     if engine.fault or not engine.thread.is_alive():raise RuntimeError(engine.fault or 'Serial worker stopped')
     if self.reconnect.is_set():
      self.reconnect.clear()
      if engine.inflight:raise RuntimeError('Reconnect during transaction')
      break
   except Exception as ex:
    self.error=str(ex);self.audit('connection_unavailable',error=self.error)
   finally:
    with self.lock:self.engine=None
    try:
     if engine:engine.close()
     elif backend:backend.close()
    except Exception as ex:
     self.audit('fatal_worker_shutdown',error=str(ex));os._exit(1)
   self.stop.wait(5)
 def current(self):
  with self.lock:
   if self.engine is None:raise ValueError(self.error or 'Reconnecting')
   return self.engine
 def state(self):
  try:result=self.current().state()
  except ValueError:result={'ready':False,'fault':self.error,'readings':{},'controls':[]}
  result.update(generation=self.generation,write_latch=self.audit.locked(),version=VERSION,standalone=True)
  return result
 def submit(self,name,value):return self.current().submit(name,value)

def notify(message):
 address=os.environ.get('NOTIFY_SOCKET')
 if address:
  with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as s:
   s.connect('\0'+address[1:] if address.startswith('@') else address);s.sendall(message.encode())

def main():
 STATE.mkdir(parents=True,exist_ok=True)
 instance=(STATE/'instance.lock').open('a');fcntl.flock(instance,fcntl.LOCK_EX|fcntl.LOCK_NB)
 stop=threading.Event()
 for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stop.set())
 audit=Audit();manager=Manager(audit,stop)
 thread=threading.Thread(target=manager.run,daemon=True,name='device-manager');thread.start()
 if SOCK.exists():SOCK.unlink()
 server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);server.bind(str(SOCK));server.listen(4);server.settimeout(.5)
 os.chmod(SOCK,0o600)
 slots=threading.BoundedSemaphore(4)
 def handle(conn):
  try:
   conn.settimeout(3);data=b''
   while b'\n' not in data:
    part=conn.recv(4096)
    if not part or len(data)>4096:raise ValueError('Invalid request')
    data+=part
   request=json.loads(data)
   if request.get('action')=='status':reply=manager.state()
   elif request.get('action')=='set':
    job=manager.submit(request['control'],str(request['value']))
    reply=job.result if job.done.wait(45) else {'status':'pending','message':'Inspect readback; do not retry'}
   elif request.get('action')=='reconnect':
    if manager.current().inflight:raise ValueError('Write in progress')
    manager.reconnect.set();reply={'status':'reconnecting'}
   else:raise ValueError('Unknown action')
  except Exception as ex:reply={'status':'error','error':str(ex)}
  try:conn.sendall((json.dumps(reply)+'\n').encode())
  except OSError:pass
  finally:conn.close();slots.release()
 mqtt=MqttBridge(manager,audit,stop);mqtt.start()
 atomic(STATE/'runtime.json',{'pid':os.getpid(),'version':VERSION,'socket':str(SOCK)})
 notify('READY=1\nSTATUS=Standalone bridge starting; reads only until ready')
 last_watchdog=0
 try:
  while not stop.is_set():
   if time.monotonic()-last_watchdog>10:
    if not mqtt.worker_thread.is_alive() or not mqtt.publisher_thread.is_alive():raise RuntimeError('MQTT worker stopped; restarting without replaying commands')
    notify('WATCHDOG=1');last_watchdog=time.monotonic()
    atomic(STATE/'health.json',dict(timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),**manager.state()))
   try:conn,_=server.accept()
   except socket.timeout:continue
   if slots.acquire(blocking=False):threading.Thread(target=handle,args=(conn,),daemon=True).start()
   else:conn.close()
 finally:
  stop.set();server.close();mqtt.close();thread.join(35)
  if thread.is_alive():audit('fatal_worker_shutdown',error='Manager shutdown timed out');os._exit(1)
  if SOCK.exists():SOCK.unlink()
  audit('service_stopped');notify('STOPPING=1')

if __name__=='__main__':main()
