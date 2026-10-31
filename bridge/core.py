"""HPVINV09 <-> PI30 mapping. Pure functions; no device access."""
import binascii, copy, dataclasses, re, time
from decimal import Decimal
IDENTITY=b"(HPVINV09\r"
FIRMWARE=b"(0010.03 20260202 12\r"
BATTERY_CHARGE_CAP_A=30
AC_SITE_BUDGET_A=32
COUNTS={"HEEP1":19,"HEEP2":17,"HGRID":10,"HOP":9,"HBAT":8,"HPV":9,"HTEMP":8,"HSTS":4,"HBMS1":10,"HBMS2":9,"HPVB":6,"HGEN":7}
def crc(data,backend=False):
    reserved=(0,10,13,40) if backend else (10,13,40)
    return bytes(x+1 if x in reserved else x for x in binascii.crc_hqx(data,0).to_bytes(2,"big"))
def frame(s,backend=False):
    b=s.encode("ascii");return b+crc(b,backend)+b"\r"
ACK=frame("(ACK");NAK=frame("(NAK")
def parse(raw,cmd):
    if not raw.startswith(b"(") or not raw.endswith(b"\r") or b"\r" in raw[:-1] or b"\n" in raw:raise ValueError("Bad framing: "+cmd)
    f=raw[1:-1].decode("ascii").split()
    if cmd in COUNTS and len(f)!=COUNTS[cmd]:raise ValueError("Changed field layout: "+cmd)
    if cmd in ("HEEP1","HEEP2") and any(not re.fullmatch(r"\d+(?:\.\d+)?",x) for x in f):raise ValueError("Invalid setting")
    if cmd=="HEEP1" and (len(f[3])!=11 or len(f[4])!=3):raise ValueError("Changed packed settings")
    if cmd=="HEEP2" and len(f[16])!=5:raise ValueError("Changed second-output settings")
    return f
@dataclasses.dataclass(frozen=True)
class Control:
    name:str
    prefix:str
    values:tuple
    block:str
    index:int
    start:int|None=None
    end:int|None=None
    unit:str|None=None
    native:str|None=None
    note:str="Verified configuration readback; physical behavior not commissioned."
    def read(self,s):
        v=s[self.block][self.index]
        return v if self.start is None else v[self.start:self.end]
    def command(self,value):
        value=str(value)
        if self.name in ('utility_charge_current','total_charge_current') and Decimal(value)>BATTERY_CHARGE_CAP_A:
            raise ValueError('Battery charging is capped at 30 A DC')
        if self.name=='grid_current_parameter' and Decimal(value)>AC_SITE_BUDGET_A:
            raise ValueError('Grid export current selection is capped at 32 A; this is not an AC input/output clamp')
        if value not in self.values:raise ValueError("Value outside supported options for "+self.name)
        if self.prefix.startswith("toggle:"):return "P"+("E" if value=="1" else "D")+self.prefix[-1]
        return self.prefix+value
    def expected(self,s,value):
        r=copy.deepcopy(s);old=r[self.block][self.index]
        if self.start is None:
            if "." in old:v=f"{Decimal(value):0{len(old)}.{len(old.split('.')[1])}f}"
            else:v=str(int(value)).zfill(len(old))
        else:v=old[:self.start]+str(value)+(old[self.end:] if self.end is not None else "")
        r[self.block][self.index]=v
        return r
def C(name,prefix,values,b,i,start=None,end=None,unit=None,native=None,note=None):
    kw={} if note is None else {"note":note}
    return Control(name,prefix,tuple(values.split()),b,i,start,end,unit,native,**kw)
CONTROLS=[
 C("output_priority","POP","00 01 02","HEEP1",0,native="POP01 -> POP00 (SUB); POP02 -> POP01 (SBU)",note="00=SUB and 01=SBU panel-confirmed; 02 label unconfirmed."),
 C("charger_priority","PCP","00 01 02 03","HEEP1",4,2,3,native="PCP02 -> PCP01 (solar + utility)",note="01=SNU confirmed; other code labels provisional."),
 C("utility_charge_current","MUCHGC","002 005 009 010","HEEP1",2,unit="A",native="MUCHGC"),
 C("total_charge_current","MNCHGC","009 010","HEEP1",1,unit="A",native="MNCHGC"),
 C("back_to_grid_voltage","PBCV","44.0 45.0 46.0","HEEP2",4,unit="V",native="PBCV"),
 C("back_to_battery_voltage","PBDV","53.0 54.0","HEEP2",5,unit="V",native="PBDV"),
 C("display_auto_return","toggle:k","0 1","HEEP1",4,1,2,native="PDk/PEk"),
 C("backlight","toggle:x","0 1","HEEP1",6,native="PDx/PEx"),
 C("buzzer","toggle:a","0 1","HEEP1",5,native="PDa/PEa"),
 C("equalization_voltage","PBEQV","58.30 58.40","HEEP2",7,unit="V"),
 C("equalization_duration","PBEQT","055 060","HEEP2",8,unit="min"),
 C("equalization_timeout","PBEQOT","115 120","HEEP2",9,unit="min"),
 C("equalization_interval","PBEQP","030 031","HEEP2",10,unit="days"),
 C("bms_shutdown_soc","BMSSDC","005 010 015","HEEP1",10,unit="%"),
 C("grid_current_parameter","PGFC","009 010","HEEP1",17,unit="A"),
 C("second_output_recovery_soc","PDSRS","90 95","HEEP2",16,0,2,unit="%"),
 C("second_output_recovery_delay","PDDLYT","005 010","HEEP2",13,unit="min"),
 C("source_notification","toggle:y","0 1","HEEP1",3,5,6,native="PDy/PEy"),
 C("overload_restart","toggle:u","0 1","HEEP1",3,4,5,native="PDu/PEu"),
 C("overtemperature_restart","toggle:v","0 1","HEEP1",3,6,7,native="PDv/PEv"),
 C("bms_return_battery_soc","BMSU2BC","025 060 090 095","HEEP1",12,unit="%"),
 C("bms_return_utility_soc","BMSB2UC","010 020 025","HEEP1",11,unit="%"),
 C("second_output_discharge_duration","PDDCGT","0000 0005","HEEP2",16,2,5,unit="min"),
 C("ac_input_range","PGR","00 01","HEEP1",3,0,1,native="PGR",note="Configuration verified; UPS/APL labels from related implementation."),
 C("bms_restart_soc","BMSSRC","050 055","HEEP1",13,unit="%"),
]
# Preserve the distinction between device-tested values and manual-supported ranges.
VERIFIED_VALUES={c.name:c.values for c in CONTROLS}
def numeric_range(lo,hi,step,width=3,decimals=0):
    return tuple(f'{Decimal(v)/(10**decimals):0{width}.{decimals}f}' if decimals else str(v).zfill(width)
                 for v in range(lo,hi+1,step))
EXPANDED_RANGES={
 'utility_charge_current':(('002','005','009','010','020','030'),'Manual program 11: 2 A, then 10 A steps; retains verified 5/9 A serial values. User cap 30 A DC.'),
 'total_charge_current':(('009','010','020','030'),'Manual program 02: 10 A steps; retains verified 9 A serial value. User cap 30 A DC across solar and utility.'),
 'back_to_grid_voltage':(numeric_range(440,510,10,4,1),'Manual program 12: 44-51 V, 1 V steps.'),
 'back_to_battery_voltage':(numeric_range(480,580,10,4,1),'Manual program 13: 48-58 V, 1 V steps. Fully-charged sentinel encoding unknown.'),
 'equalization_voltage':(tuple(f'{Decimal(v)/10:.2f}' for v in range(480,601)),'Manual program 31: 48-60 V, 0.1 V steps. Stored setting only; equalization stays disabled in lithium/BMS profile.'),
 'equalization_duration':(numeric_range(5,900,5),'Manual program 33: 5-900 minutes, 5-minute steps.'),
 'equalization_timeout':(numeric_range(5,900,5),'Manual program 34: 5-900 minutes, 5-minute steps.'),
 'equalization_interval':(numeric_range(0,90,1),'Manual program 35: 0-90 days, 1-day steps.'),
 'grid_current_parameter':(numeric_range(1,32,1),'Manual program 56: GRID-tie/export current, 1 A steps; user selection cap 32 A. Endpoints not device-tested. Not a verified combined AC input/output limit; physical effect uncommissioned.'),
 'second_output_discharge_duration':(numeric_range(0,990,5,4),'Manual program 65: 0-990 minutes, 5-minute steps; 0 disables timer.'),
 'second_output_recovery_delay':(numeric_range(0,60,5),'Manual program 66: 0-60 minutes; related protocol requires 5-minute steps. Not every value device-tested.'),
}
CONTROLS=[dataclasses.replace(c,values=EXPANDED_RANGES[c.name][0],note=EXPANDED_RANGES[c.name][1]+' Each write requires ACK and full readback.') if c.name in EXPANDED_RANGES else c for c in CONTROLS]
BY_NAME={c.name:c for c in CONTROLS}
# Wire encodings differ from packed-field widths.
def command(c,value):
    s=c.command(value)
    if c.name=="second_output_recovery_soc":s=c.prefix+str(int(value)).zfill(3)
    return s
def expected(c,s,value):
    v=value
    if c.start is not None:v=str(int(value)).zfill(c.end-c.start)
    return c.expected(s,v)
def same(c,s,value):return Decimal(c.read(s))==Decimal(value)
_BACKEND_COMMANDS={command(c,v):(c,v) for c in CONTROLS for v in c.values}
def locate_backend(cmd):
    try:c,v=_BACKEND_COMMANDS[cmd]
    except KeyError:raise ValueError("Command outside supported registry") from None
    c.command(v)
    return c,v
def native_write(cmd):
    # Only panel-confirmed equivalences; extra enums available as neutral local codes.
    if cmd=="POP01":return BY_NAME["output_priority"],"00"
    if cmd=="POP02":return BY_NAME["output_priority"],"01"
    if cmd=="PCP02":return BY_NAME["charger_priority"],"01"
    if cmd.startswith(("POP","PCP")):raise ValueError("Priority label not sufficiently verified")
    c,v=locate_backend(cmd)
    if c.native is None:raise ValueError("No equivalent in this SA driver; use local control")
    return c,v
def payload(raw):
    if not raw.endswith(b"\r") or len(raw)<4:raise ValueError("Incomplete PI30 request")
    data=raw[:-3]
    if crc(data)!=raw[-3:-1]:raise ValueError("Invalid PI30 CRC")
    return data.decode("ascii")
def validate_snapshot(s):
    for k in ("HEEP1","HEEP2"):parse(("("+" ".join(s[k])+"\r").encode(),k)
    if s["HEEP1"][9]!="1" or s["HEEP1"][3][2]!="4":raise ValueError("Battery/BMS profile changed")
    if s["HEEP2"][6]!="0":raise ValueError("Equalization unexpectedly enabled")
