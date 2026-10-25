"""Reference-load what-if simulation. Never writes controls or the savings ledger."""
from datetime import datetime, timedelta
from .policy import plan_with_reserve_hold, numeric, price_window


def project_savings(now, hourly_w, settings, rates, charge_amps, pack_voltage, storm=False, weekly_profiles=None):
    """Repeat the observed 24h profile, settle 14 days, then model a week.

    Model the controller's charge permission separately from SUB source choice.
    SOC/capacity and constant monthly prices remain modelling assumptions; cell
    limits, protection trips, switching delays and HA outages are not simulated.
    """
    # Long-run reference figures cannot assume tonight's temperature/weather
    # repeats all year. Thermal advances are disclosed separately in the UI;
    # their actual charging cost remains in the recorded operation ledger.
    settings=dict(settings,thermal_enabled=False)
    if len(hourly_w)!=24 or any(numeric(v) is None or not 0<=v<=10000 for v in hourly_w):
        return None
    if not rates or numeric(charge_amps) is None or charge_amps<0 or numeric(pack_voltage) is None or not 20<=pack_voltage<=70:
        return None
    if weekly_profiles and (set(weekly_profiles)!={str(d) for d in range(7)} or any(len(p)!=24 or any(numeric(v) is None or not 0<=v<=10000 for v in p) for p in weekly_profiles.values())):
        return None
    cap=settings["capacity_kwh"]
    eta_d=settings["discharge_efficiency"]/100
    eta_c=settings["charge_efficiency"]/100
    target=cap*settings["charge_target"]/100
    energy=0.  # Settle from empty; the same hours-derived reserve governs the model.
    priority="SUB"
    charge_latched=False
    reserve_hold=False
    # Full weeks keep weekday/weekend weighting; no starting energy is free income.
    start=now.replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(days=now.weekday())
    baseline=operating=wear=shifted=0.
    starting_energy=None
    for step in range(21*96):
        when=start+timedelta(minutes=step*15)
        profile=weekly_profiles[str(when.weekday())] if weekly_profiles else hourly_w
        load=profile[when.hour]
        demand=load/eta_d+settings["overhead_w"]
        data={"soc":energy/cap*100,"load_w":load,"average_load_w":sum(profile)/24,
              "charge_w":0.,"discharge_w":demand if priority=="SBU" else 0.,
              "grid_voltage":120.,"fresh":True,"healthy":True,"mode":"Battery" if priority=="SBU" else "Line","priority":priority}
        plan,reserve_hold=plan_with_reserve_hold(when,data,settings,rates,storm,reserve_hold)
        if energy>=target-1e-9: charge_latched=True
        if energy<=target-cap*.05: charge_latched=False
        priority=plan.desired_priority or "SUB"
        if step==14*96: starting_energy=energy
        rate=rates[price_window(when,settings)]
        if priority=="SBU":
            reserve=cap*(plan.reserve_soc or 0)/100
            used=min(max(0,energy-reserve),demand/1000*.25)
            fraction=min(1,used/(demand/1000*.25)) if demand else 0
            energy-=used
            cost=load/1000*.25*(1-fraction)*rate
            delivered=load/1000*.25*fraction
            wear_cost=used*settings["wear_cost"]
        else:
            headroom=max(0,settings["ac_budget_a"]*120-load-settings["overhead_w"])
            watts=min(charge_amps,settings["charge_cap_a"])*pack_voltage
            allow_charge=not charge_latched and plan.decision in {"Recharge","Recover reserve","Charge","Keep ready"}
            charged=min(max(0,target-energy),min(watts,headroom*eta_c)/1000*.25) if allow_charge else 0
            energy+=charged
            cost=(load+settings["overhead_w"])/1000*.25*rate+charged/eta_c*rate
            delivered=wear_cost=0.
        if step>=14*96:
            baseline+=load/1000*.25*rate
            operating+=cost
            wear+=wear_cost
            shifted+=delivered
    # Charge any net drawdown back into the cost rather than crediting initial inventory.
    replenishment=max(0,(starting_energy or 0)-energy)/eta_c*rates["Super off-peak"]
    net=baseline-operating-wear-replenishment
    return {"day":net/7,"month":net/7*365.25/12,"year":net/7*365.25,
            "shifted_kwh_day":shifted/7,"baseline_cost_day":baseline/7,
            "operating_cost_day":(operating+wear+replenishment)/7,
            "charge_limit_a":charge_amps,"model":("Learned weekday/weekend hourly profiles" if weekly_profiles else "Observed 24-hour load repeated")+"; 14-day settling period and 7-day simulation",
            "assumptions":["Current monthly prices held constant; annual value is a run rate, not a tariff forecast",
                "Configured capacity, efficiencies, idle use and reserve margin",
                "Grid charging only when the planner requests recharge; grid hold does not top up",
                "Configured DC current, SOC target and five-point recharge hysteresis; SOC accuracy unverified",
                "Cell limits, protection trips, switching delays and HA outages not simulated",
                "No solar, outages, battery degradation or changing weather beyond the current reserve state"]}
