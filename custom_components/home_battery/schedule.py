"""Bounded, read-only schedule illustration using the actual decision policy.

This is a rolling estimate, never a command queue. All energy is DC-side.
"""
from datetime import datetime
import math
from .policy import make_plan, numeric, price_window, planning_profile


def preview_schedule(now,data,settings,rates,charge_amps,pack_voltage,*,weekly=None,error_w=0,storm=False,guard=None,blocked_reason=''):
    result={'status':'Waiting','segments':[],'points':[],
        'timezone':str(now.tzinfo),'start':now.timestamp(),'end':now.timestamp()+86400,
        'basis':'Checked load forecast' if weekly else 'Current-load estimate',
        'profile':settings['planning_goal'],
        'assumptions':'15-minute estimate; current prices, weather and charging limits held constant. SOC/capacity are estimates. Solar, future cell voltages, outages and transfer delays are not predicted. This is not a queued command schedule.'}
    if not data.get('fresh') or not data.get('healthy') or data.get('has_bms_alarm'):
        return result|{'message':'Waiting for fresh readings and clear battery protections.'}
    if numeric(data.get('soc')) is None or not 0<=data['soc']<=100 or (numeric(data.get('grid_voltage')) or 0)<=90:
        return result|{'message':'An outage or missing battery readings prevents a reliable price schedule.'}
    if not rates or numeric(charge_amps) is None or charge_amps<0 or numeric(pack_voltage) is None or not 20<=pack_voltage<=70:
        return result|{'message':'Waiting for electricity prices and verified charging limits.'}
    if weekly and (set(weekly)!={str(d) for d in range(7)} or any(len(p)!=24 or any(numeric(v) is None or not 0<=v<=10000 for v in p) for p in weekly.values())):
        return result|{'message':'The load forecast is incomplete.'}
    load=max(data['load_w'],data.get('average_load_w',0))
    if not 0<=load<=10000:
        return result|{'message':'The load reading is outside its accepted range.'}
    cap=settings['capacity_kwh']*1000
    energy=cap*data['soc']/100
    target=cap*settings['charge_target']/100
    target_latched=bool((guard or {}).get('target_latched'))
    # Unknown cell/alarm recovery cannot be predicted from SOC. Do not invent it.
    other_guard=bool((guard or {}).get('cell_latched') or (guard or {}).get('alarm_latched') or
                     (blocked_reason and not target_latched))
    priority=data.get('priority','SUB')
    idle_dc=max(0,data['discharge_w']-data['charge_w']) if data.get('mode')=='Line' else 0
    stamp=now.timestamp()
    while stamp<result['end']:
        when=datetime.fromtimestamp(stamp,now.tzinfo)
        stop=min(result['end'],(math.floor(stamp/900)+1)*900)
        hours=(stop-stamp)/3600
        watts=weekly[str(when.weekday())][when.hour] if weekly else load
        demand=watts/(settings['discharge_efficiency']/100)+settings['overhead_w']
        projected=dict(data,soc=energy/cap*100,load_w=watts,average_load_w=watts,
                       charge_w=0.,discharge_w=demand if priority=='SBU' else 0.,priority=priority)
        # Keep the first decision identical to the live policy; later steps are estimates.
        if stamp==result['start']: projected=dict(data)
        if weekly and stamp!=result['start']:
            start,end=(15,19) if settings['price_source']=='PSEG Rate 195' else (settings['peak_start'],settings['peak_end'])
            uncertainty=max(0,error_w)*planning_profile(settings)['forecast_error_multiplier']
            projected['peak_forecast_wh']=sum(((v+uncertainty)/(settings['discharge_efficiency']/100)+settings['overhead_w'])*max(0,min(h+1,end)-max(h,start)) for h,v in enumerate(weekly[str(when.weekday())]))
        else: projected['peak_forecast_wh']=None
        plan=make_plan(when,projected,settings,rates,storm)
        if plan.desired_priority is None:
            return result|{'segments':[],'points':[],'message':plan.reason}
        priority=plan.desired_priority
        if energy>=target-1e-9: target_latched=True
        if energy<=target-cap*.05: target_latched=False
        allow_charge=not (other_guard or target_latched) and plan.decision in {'Recharge','Recover reserve','Charge','Keep ready'}
        before=energy/cap*100
        action='battery' if priority=='SBU' else 'utility'
        if priority=='SBU':
            energy=max(cap*(plan.reserve_soc or 0)/100,energy-demand*hours)
            energy=min(energy,before/100*cap)
        else:
            headroom=max(0,settings['ac_budget_a']*data['grid_voltage']-watts-settings['overhead_w'])
            charge_w=min(charge_amps,settings['charge_cap_a'],30)*pack_voltage
            charged=min(max(0,target-energy),min(charge_w,headroom*settings['charge_efficiency']/100)*hours) if allow_charge else 0
            if charged>0: action='charge'
            energy=max(0,min(cap,energy+charged-idle_dc*hours))
        after=energy/cap*100
        tariff=price_window(when,settings)
        detail=plan.reason if not (priority=='SUB' and other_guard) else 'Utility charging remains paused; cell/alarm recovery needs live readings.'
        step={'start':stamp,'end':stop,'action':action,'reason':detail,'tariff':tariff,
              'price':rates[tariff],'soc_start':round(before,1),'soc_end':round(after,1),'reserve':round(plan.reserve_soc or 0,1)}
        if result['segments'] and all(result['segments'][-1][k]==step[k] for k in ('action','reason','tariff')):
            result['segments'][-1].update(end=stop,soc_end=step['soc_end'])
        else: result['segments'].append(step)
        result['points'].append({'t':stamp,'soc':round(before,2),'reserve':round(plan.reserve_soc or 0,2)})
        stamp=stop
    result['points'].append({'t':stamp,'soc':round(energy/cap*100,2),'reserve':result['points'][-1]['reserve']})
    return result|{'status':'Estimated' if settings['automatic_enabled'] else 'Preview only',
        'message':'Updates as load, prices, battery and weather change.' if settings['automatic_enabled'] else 'Automatic scheduling is off; these actions will not run.'}
