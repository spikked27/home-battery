"""Deterministic planning and cash accounting; no I/O or device commands."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import math


def numeric(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def federal_holidays(year):
    """Observed federal holidays used by PSEG Rate 195."""
    def observed(day):
        return day + timedelta(days=-1 if day.weekday() == 5 else 1 if day.weekday() == 6 else 0)
    def nth(month, weekday, number):
        day = date(year, month, 1)
        return day + timedelta(days=(weekday-day.weekday()) % 7 + 7*(number-1))
    result = {observed(date(year, m, d)) for m, d in [(1,1),(6,19),(7,4),(11,11),(12,25)]}
    result |= {nth(1,0,3),nth(2,0,3),nth(9,0,1),nth(10,0,2),nth(11,3,4)}
    result.add(date(year,6,1)-timedelta(days=1+(date(year,6,1).weekday()-0-1)%7))
    result.add(observed(date(year+1,1,1)))
    return result


def tariff_window(now, charge_start=22, charge_end=6, peak_start=15, peak_end=19):
    hour = now.hour + now.minute/60
    overnight = (charge_start <= hour < charge_end if charge_start < charge_end
                 else hour >= charge_start or hour < charge_end)
    if overnight:
        return "Super off-peak"
    if now.weekday() < 5 and now.date() not in federal_holidays(now.year) and peak_start <= hour < peak_end:
        return "Peak"
    return "Off-peak"


def price_window(now,settings):
    """Changing desired charging hours must not change the utility's prices."""
    if settings["price_source"]=="PSEG Rate 195": return tariff_window(now)
    return tariff_window(now,settings["charge_start"],settings["charge_end"],settings["peak_start"],settings["peak_end"])


def pseg_rates(now, supply):
    """Published 2026 delivery + monthly supply; not account-specific bill prices."""
    if now.year != 2026 or numeric(supply) is None or not 0 < supply < 1:
        return None
    summer = 6 <= now.month <= 9
    delivery = (.0452,.1388,.2979) if summer else (.0450,.0929,.2440)
    multipliers = (.6,1,1.7419 if summer else 1.9688)
    return dict(zip(("Super off-peak","Off-peak","Peak"), (round(d+supply*m,6) for d,m in zip(delivery,multipliers))))


@dataclass(frozen=True)
class Plan:
    decision: str
    reason: str
    desired_priority: str | None
    reserve_soc: float | None = None
    runtime_hours: float | None = None
    economic_margin: float | None = None


def make_plan(now, data, settings, rates, storm=False):
    required = ("soc","load_w","discharge_w","charge_w","grid_voltage")
    if any(numeric(data.get(key)) is None for key in required) or not data.get("fresh"):
        return Plan("Paused","Waiting for fresh battery, inverter and load readings",None)
    if not data.get("healthy"):
        return Plan("Paused","Battery alarms or bridge fault require attention",None)
    soc, load = data["soc"], max(data["load_w"],data.get("average_load_w",0))
    if not 0 <= soc <= 100 or not 0 <= load <= 10000:
        return Plan("Paused","A measurement is outside its accepted range",None)
    capacity = settings["capacity_kwh"]
    demand = max(load/(settings["discharge_efficiency"]/100)+settings["overhead_w"],data["discharge_w"])
    reserve = max(settings["minimum_reserve"],settings["backup_hours"]*demand/1000/capacity*100*(1+settings["reserve_margin"]/100))
    if storm:
        reserve = max(reserve,settings["storm_reserve"])
    reserve = min(100,reserve)
    runtime = capacity*soc/100*1000/demand if demand > 0 else None
    grid = data["grid_voltage"] > 90
    if not grid:
        return Plan("Outage","Utility unavailable; hardware determines backup operation",None,reserve,runtime)
    if reserve >= settings["charge_target"]:
        return Plan("Keep ready","Reserve needs approach the charge target; use grid", "SUB",reserve,runtime)
    if storm or settings["planning_goal"] == "Backup first":
        return Plan("Keep ready","Storm reserve or backup-first preference", "SUB",reserve,runtime)
    if soc <= reserve:
        return Plan("Recharge","Battery is at or below the outage reserve", "SUB",reserve,runtime)
    if data.get("priority")=="SUB" and soc<min(settings["charge_target"],reserve+5):
        return Plan("Recover reserve","Recover five SOC points above reserve before returning to battery", "SUB",reserve,runtime)
    window = price_window(now,settings)
    hour=now.hour+now.minute/60
    start,end=settings["charge_start"],settings["charge_end"]
    charging_hours=(start<=hour<end if start<end else hour>=start or hour<end)
    if charging_hours:
        return Plan("Charge" if soc < settings["charge_target"] else "Target reached",
                    "Low-price charge window" if soc < settings["charge_target"] else "Charging target reached; neutral grid mode is not established",
                    "SUB",reserve,runtime)
    if not rates:
        return Plan("Hold reserve","Electricity prices unavailable; economics cannot be assessed", "SUB",reserve,runtime)
    margin = rates[window] - rates["Super off-peak"]*demand/max(load,1)/(settings["charge_efficiency"]/100) - settings["wear_cost"]*demand/max(load,1)
    if margin <= settings["minimum_margin"]:
        return Plan("Hold reserve","Charging losses and idle consumption outweigh the price difference","SUB",reserve,runtime,margin)
    # Preserve enough energy to reach today's next peak before discretionary off-peak discharge.
    peak_start,peak_end=(15,19) if settings["price_source"]=="PSEG Rate 195" else (settings["peak_start"],settings["peak_end"])
    if window == "Off-peak" and now.weekday() < 5 and now.date() not in federal_holidays(now.year) and now.hour < peak_start:
        peak_hours = peak_end-peak_start
        needed = reserve + peak_hours*demand/1000/capacity*100
        if soc <= needed:
            return Plan("Save for peak","Keep remaining energy for the upcoming peak window","SUB",reserve,runtime,margin)
    return Plan("Use battery","Reserve protected and estimated battery operation is economical","SBU",reserve,runtime,margin)


def money_rates(data, settings, price):
    """Cash-flow estimate. DC idle drain never becomes avoided AC consumption."""
    if price is None or not data.get("fresh") or not data.get("healthy"):
        return None
    if any(numeric(data.get(k)) is None for k in ("load_w","charge_w","discharge_w","grid_voltage")):
        return None
    grid = data["grid_voltage"] > 90
    ac = min(data["load_w"],data["discharge_w"]*settings["discharge_efficiency"]/100) if data.get("mode") == "Battery" and grid else 0
    charging = data["charge_w"]/(settings["charge_efficiency"]/100) if grid else 0
    idle = settings["overhead_w"] if data.get("mode") == "Line" and grid else 0
    return {"avoided":ac/1000*price,"charging":(charging+idle)/1000*price,
            "wear":data["discharge_w"]/1000*settings["wear_cost"]}


def cell_extremes(cells):
    if not cells or any(numeric(v) is None or not 0 < float(v) < 5 for v in cells):
        return None
    low, high = min(cells),max(cells)
    return {"lowest_cell":low,"highest_cell":high,"cell_spread":high-low,
            "lowest_positions":[i+1 for i,v in enumerate(cells) if v==low],
            "highest_positions":[i+1 for i,v in enumerate(cells) if v==high]}
