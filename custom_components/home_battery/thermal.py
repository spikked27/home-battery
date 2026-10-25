"""Temperature-aware timing of needed charging. No hardware access or heat credit.

Cooling is learned from passive intervals, never from missing data. Outdoor
forecasts select a useful time; they are not substituted for cell temperature.
"""
from datetime import datetime, timedelta
from statistics import median
from .policy import numeric


class ThermalHistory:
    def __init__(self, saved=None):
        saved=saved or {}
        self.samples=[r for r in saved.get('samples',[]) if isinstance(r,list) and len(r)==3
                      and all(numeric(v) is not None for v in r) and -30<=r[1]<=65 and 0<=r[2]<=10000][-2200:]
        self.day=saved.get('day','');self.cost=max(0,numeric(saved.get('cost')) or 0)
        self.energy=max(0,numeric(saved.get('energy')) or 0);self.previous=saved.get('previous')
        if not isinstance(self.previous,(list,tuple)) or len(self.previous)!=4 or not all(numeric(v) is not None for v in self.previous[:3]):self.previous=None
        self.budget_uncertain=bool(saved.get('budget_uncertain',False))
        self.started_window_end=numeric(saved.get('started_window_end'))

    def saved(self):
        return {'samples':self.samples,'day':self.day,'cost':self.cost,'energy':self.energy,
                'previous':self.previous,'budget_uncertain':self.budget_uncertain,'started_window_end':self.started_window_end}

    def seed(self, temperatures, powers):
        power={r['start']:numeric(r.get('mean')) for r in powers}
        merged={r[0]:r for r in self.samples}
        for row in temperatures:
            t=numeric(row.get('start'));v=numeric(row.get('mean'));w=power.get(row.get('start'))
            if t is not None and v is not None and w is not None and -30<=v<=65 and 0<=w<=10000:
                merged.setdefault(t+1800,[t+1800,v,w])
        self.samples=sorted(merged.values())[-2200:]

    def observe(self, now, data, settings, price, early_charge=False):
        stamp=now.timestamp();day=now.date().isoformat()
        if self.day!=day:self.day=day;self.cost=self.energy=0.;self.previous=None;self.budget_uncertain=False
        if self.previous:
            t,w,p,active=self.previous;seconds=stamp-t
            if active and seconds>90:self.budget_uncertain=True
            if data.get('fresh') and 0<seconds<=90 and active and price is not None:
                energy=w/1000*seconds/3600
                self.energy+=energy;self.cost+=energy*p
        w=numeric(data.get('charge_w'));temp=numeric(data.get('cold_temperature'))
        self.previous=(stamp,(w or 0)/(settings['charge_efficiency']/100),price or 0,early_charge) if data.get('fresh') else None
        if data.get('fresh') and temp is not None and w is not None and -30<=temp<=65 and w>=0:
            if not self.samples or stamp-self.samples[-1][0]>=600:self.samples.append([stamp,temp,w])
        self.samples=[r for r in self.samples if stamp-8*86400<=r[0]<=stamp][-2200:]

    def model(self, zone):
        bins={h:[] for h in range(24)};passive=[];charging=[]
        for a,b in zip(self.samples,self.samples[1:]):
            hours=(b[0]-a[0])/3600
            if not .15<=hours<=1.25:continue
            slope=(b[1]-a[1])/hours
            if abs(slope)>3:continue
            if max(a[2],b[2])<50:
                passive.append((a[0],slope));bins[datetime.fromtimestamp(a[0],zone).hour].append(slope)
            elif min(a[2],b[2])>=100:charging.append(slope)
        # Held-out observations assess the rate model; warming is reported as
        # an association only and never subtracted from projected cooling.
        cut=max(1,int(len(passive)*.8));train=passive[:cut];test=passive[cut:]
        base=median(v for _,v in train) if train else 0.
        train_bins={h:[] for h in range(24)}
        for stamp,value in train:train_bins[datetime.fromtimestamp(stamp,zone).hour].append(value)
        def prediction(stamp):
            values=train_bins[datetime.fromtimestamp(stamp,zone).hour]
            return min(0,max(-2,median(values) if len(values)>=2 else base))
        error=median(abs(v-prediction(stamp)) for stamp,v in test) if test else None
        covered=sum(min(1,(b[0]-a[0])/3600) for a,b in zip(self.samples,self.samples[1:]) if .15<=(b[0]-a[0])/3600<=1.25 and max(a[2],b[2])<50)
        ready=covered>=12 and len(test)>=3 and error is not None and error<=.75
        cooling=[min(0,max(-2,median(bins[h]) if len(bins[h])>=2 else base)) for h in range(24)]
        recent=[(b[1]-a[1])/((b[0]-a[0])/3600) for a,b in zip(self.samples,self.samples[1:])
                if self.samples and a[0]>=self.samples[-1][0]-3600 and .15<=(b[0]-a[0])/3600<=.5 and max(a[2],b[2])<50]
        return {'ready':ready,'passive_hours':round(covered,1),'cooling_c_per_hour':cooling,
                'recent_cooling_c_per_hour':min(0,max(-2,median(recent))) if len(recent)>=2 else 0.,
                'validation_error_c_per_hour':round(error,3) if error is not None else None,
                'charging_net_change_c_per_hour':round(median(charging),3) if len(charging)>=6 else None,
                'charge_observations':len(charging),'heat_credit_used':False}


def next_window(now, settings):
    """Use local wall-clock boundaries across midnight and DST."""
    start_hour,end_hour=settings['charge_start'],settings['charge_end']
    starts=[(now+timedelta(days=d)).replace(hour=int(start_hour),minute=0,second=0,microsecond=0) for d in (-1,0,1)]
    for start in starts:
        end=(start+timedelta(days=1 if end_hour<=start_hour else 0)).replace(hour=int(end_hour))
        if end.timestamp()>now.timestamp():return start.timestamp(),end.timestamp()
    raise ValueError('Charging window unavailable')


def temperature_at(start, stop, temperature, model, zone):
    if numeric(temperature) is None:return None
    value=temperature;stamp=start
    while stamp<stop:
        step=min(900,stop-stamp);hour=datetime.fromtimestamp(stamp,zone).hour
        rate=min(model.get('cooling_c_per_hour',[0]*24)[hour],model.get('recent_cooling_c_per_hour',0))
        value+=rate*step/3600;stamp+=step
    return value


def thermal_advice(now, data, settings, context=None):
    result={'enabled':bool(settings.get('thermal_enabled')),'status':'Off','delay_until':None,'early_charge':False}
    if not result['enabled']:return result
    context=context or {};model=context.get('model',{});temp=numeric(data.get('cold_temperature'))
    floor=settings.get('thermal_charge_floor',8)
    result.update(temperature_c=temp,charge_floor_c=floor,model=model,
                  cost_today=context.get('cost',0),energy_today_kwh=context.get('energy',0),
                  source=data.get('cold_temperature_source'),heat_credit_used=False)
    if not data.get('fresh') or temp is None or numeric(data.get('soc')) is None or not 0<=data['soc']<=100:
        return result|{'status':'Temperature unavailable','message':'No charge deferral; fresh battery temperature is required for utility charging.'}
    if temp<floor:
        return result|{'status':'Too cold to charge','message':'Use utility; warm the enclosure. No cycling or protection override is available.'}
    start,end=next_window(now,settings);stamp=now.timestamp()
    amps=numeric(context.get('charge_amps'));voltage=numeric(data.get('voltage'))
    if amps is None or amps<=0 or voltage is None or voltage<=0:
        return result|{'status':'Waiting for charge limits','message':'Normal scheduling remains active; charging duration cannot be verified.'}
    watts=min(amps,settings['charge_cap_a'],30)*voltage
    # Extra time covers taper and transfer delays; cap the estimate to the
    # available window. Completion remains an estimate, never a guarantee.
    need=max(0,(settings['charge_target']-data['soc'])/100*settings['capacity_kwh']*1000)
    hours=need/max(1,watts)*1.25+.5
    available=max(stamp,start);latest=max(available,end-hours*3600)
    result.update(window_start=start,window_end=end,estimated_charge_hours=round(hours,2),latest_start=latest)
    if start<=stamp<end and hours>(end-stamp)/3600:
        return result|{'status':'Charge window tight','delay_until':stamp,
            'message':'Start needed charging now; the remaining cheap window may be too short to reach target.'}
    if data['soc']>=settings['charge_target']-5:
        return result|{'status':'No extra cycling','message':'Battery is at or near its target; do not discharge it to make room for heating.'}
    if not model.get('ready'):
        return result|{'status':'Learning cooling pattern','message':'Normal charging continues while passive temperature history and prediction checks accumulate.'}
    if start<=stamp<end and context.get('started_window_end')==end:
        return result|{'status':'Charging through cold hours','delay_until':stamp,
            'message':'Keep the started overnight charge stable; normal target and protections stop charging.'}
    # Weather chooses timing only. Battery limits use the learned battery
    # cooling curve, not the outdoor forecast as a cell-temperature reading.
    candidates=[available+i*900 for i in range(int(max(0,latest-available)/900)+1)]
    weather=context.get('weather',[])
    def score(t):
        middle=t+hours*1800
        nearby=min(weather,key=lambda r:abs(r[0]-middle)) if weather else None
        return nearby[1] if nearby and abs(nearby[0]-middle)<=7200 else temperature_at(stamp,middle,temp,model,now.tzinfo)
    chosen=min(candidates,key=lambda t:(score(t),-t)) if candidates else available
    coldest_candidate=chosen
    uncertainty=max(.5,(model.get('validation_error_c_per_hour') or 0)*max(0,chosen-stamp)/3600)
    # Start before any predicted cold-boundary crossing, with an additional
    # half hour of lead time. No speculative heating is credited.
    for t in candidates:
        if temperature_at(stamp,t,temp,model,now.tzinfo)-uncertainty<=floor+1:
            chosen=min(chosen,max(available,t-1800));break
    result.update(delay_until=chosen,predicted_start_temperature_c=round(temperature_at(stamp,chosen,temp,model,now.tzinfo),1))
    cold_soon=temperature_at(stamp,stamp+3600,temp,model,now.tzinfo)-max(.5,model.get('validation_error_c_per_hour') or 0)<=floor+1
    if stamp<start and cold_soon and settings.get('thermal_availability'):
        price=numeric(context.get('price'));spent=context.get('cost',0)
        # Reserve 90 seconds of worst-case charging cost for the next command
        # interval/transfer. This is a supervisory budget, not a hardware cap.
        exposure=(watts/(settings['charge_efficiency']/100))/1000*90/3600*(price or 0)
        allowed=not context.get('budget_uncertain') and price is not None and price>0 and spent+exposure<=settings.get('thermal_extra_budget',0)
        return result|{'status':'Charge before cold limit' if allowed else 'Early-charge budget unavailable',
            'early_charge':allowed,'message':'Advance needed charging before the predicted cold boundary; target and protections still apply.' if allowed else 'Early charging needs a valid price and remaining daily budget. A heater may be needed.'}
    waiting=start<=stamp<chosen
    advanced=chosen<coldest_candidate
    return result|{'status':'Waiting for colder hours' if waiting else 'Earlier charge for cold margin' if advanced else 'Cold-aware charging planned',
        'cold_boundary_advanced':advanced,
        'message':'Start earlier than the coldest period because the predicted temperature and its uncertainty approach the charging floor. No warming benefit is assumed.' if advanced else 'Needed charging is timed for colder hours with completion and temperature margins; no heating benefit is assumed.'}
