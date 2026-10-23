"""Local load forecasting and chronological validation; no device commands."""
from datetime import datetime, timedelta
from math import isfinite

HISTORY_DAYS=(7,14,30,90)


def clean_hours(rows, now, days, factor=1):
    """Only completed, unique recorded UTC hours within the chosen window."""
    cutoff=now.timestamp()-days*86400
    complete=int(now.timestamp()//3600)*3600
    result={}
    for row in rows:
        try: stamp=float(row['start']);value=float(row['mean'])*factor
        except (KeyError,TypeError,ValueError): continue
        if isfinite(stamp) and isfinite(value) and cutoff<=stamp<complete and 0<=value<=10000:
            result[stamp]=value
    return sorted(result.items())


def predict(samples, target, tz):
    """Recent comparable day types, with same-hour fallback; no future samples."""
    candidates=[];same_type=[]
    for stamp,value in samples:
        if stamp>=target.timestamp(): continue
        local=datetime.fromtimestamp(stamp,tz)
        if local.hour!=target.hour: continue
        weight=2**(-(target.timestamp()-stamp)/86400/14)
        candidates.append((value,weight))
        if (local.weekday()<5)==(target.weekday()<5): same_type.append((value,weight))
    selected=same_type if len(same_type)>=2 else candidates
    return sum(v*w for v,w in selected)/sum(w for _,w in selected) if selected else None


def learn_load(rows,now,days,factor=1):
    if days not in HISTORY_DAYS: raise ValueError('Choose 7, 14, 30 or 90 days')
    samples=clean_hours(rows,now,days,factor)
    hours=len(samples)
    tomorrow=now.replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=1)
    profile=[predict(samples,tomorrow.replace(hour=h),now.tzinfo) for h in range(24)]
    today=now.replace(hour=0,minute=0,second=0,microsecond=0)
    today_profile=[predict(samples,today.replace(hour=h),now.tzinfo) for h in range(24)]
    weekly={str((tomorrow+timedelta(days=d)).weekday()):[predict(samples,(tomorrow+timedelta(days=d)).replace(hour=h),now.tzinfo) for h in range(24)] for d in range(7)}
    ready=hours>=48 and all(v is not None for v in profile)
    # Walk forward over recent held-out hours. Each prediction uses strictly
    # earlier measurements, not an in-sample fit or tomorrow's observations.
    errors=[];actual_total=0.
    recent=now.timestamp()-7*86400
    for i,(stamp,value) in enumerate(samples):
        if i<48 or stamp<recent: continue
        predicted=predict(samples[:i],datetime.fromtimestamp(stamp,now.tzinfo),now.tzinfo)
        if predicted is not None:
            errors.append(abs(predicted-value));actual_total+=value
    return {
        'status':'Ready' if ready else 'Learning' if hours else 'Waiting for history',
        'history_days':days,'recorded_hours':hours,'available_days':round(hours/24,1),
        'coverage_percent':round(min(100,hours/(days*24)*100),1),
        'profile_w':profile if ready else [],
        'today_profile_w':today_profile if ready else [],
        'profiles_by_weekday':weekly if ready else {},
        'expected_daily_kwh':sum(profile)/1000 if ready else None,
        'validation_hours':len(errors),
        'typical_error_w':sum(errors)/len(errors) if errors else None,
        'weighted_error_percent':sum(errors)/actual_total*100 if errors and actual_total>0 else None,
        'method':'Recent similar weekdays/weekends; local hourly history; no cloud',
        'validation_method':'Earlier readings only; walk-forward absolute error, not guaranteed future accuracy',
        'first_hour':samples[0][0] if samples else None,'last_hour':samples[-1][0] if samples else None,
        'updated_at':now.isoformat(),
        'forecast_date':now.date().isoformat(),
    }
