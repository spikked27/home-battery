"""Public contracts and validated local planning settings."""
DOMAIN = "home_battery"
VERSION = "1.3.1"
PLATFORMS = ["sensor","binary_sensor","select","number","switch","button"]
DEFAULTS = {
    "capacity_kwh":5.2,"backup_hours":2,"minimum_reserve":20,"storm_reserve":90,
    "charge_target":95,"reserve_margin":20,"discharge_efficiency":90,
    "charge_efficiency":90,"overhead_w":45,"wear_cost":0,"minimum_margin":0,
    "charge_start":22,"charge_end":6,"peak_start":15,"peak_end":19,
    "charge_cap_a":30,"ac_budget_a":32,"freshness_seconds":90,
    "planning_goal":"Save money","weather_policy":"Automatic advice",
    "price_source":"PSEG Rate 195","automatic_enabled":False,"storm_override":False,
    "commissioned":False,"switching_confirmed":False,"manual_override_minutes":120,
    "storm_wind_mph":30,"storm_gust_mph":40,
    "manual_super_rate":.12852,"manual_off_rate":.2321,"manual_peak_rate":.518057,
}
NUMBERS = {
    "capacity_kwh":("Usable battery capacity",.1,200,.1,"kWh"),
    "backup_hours":("Outage backup target",.25,72,.25,"h"),
    "minimum_reserve":("Minimum battery reserve",5,100,1,"%"),
    "storm_reserve":("Storm reserve",5,100,1,"%"),
    "charge_target":("Charge target",10,100,1,"%"),
    "reserve_margin":("Backup estimate margin",0,100,1,"%"),
    "discharge_efficiency":("DC to AC efficiency estimate",50,100,1,"%"),
    "charge_efficiency":("Charging efficiency estimate",50,100,1,"%"),
    "overhead_w":("Inverter idle consumption estimate",0,500,1,"W"),
    "wear_cost":("Battery wear allowance",0,1,.001,"USD/kWh"),
    "minimum_margin":("Minimum savings margin",0,1,.001,"USD/kWh"),
    "charge_start":("Low-price charging starts",0,23,1,"h"),
    "charge_end":("Low-price charging ends",0,23,1,"h"),
    "peak_start":("Peak window starts",0,22,1,"h"),
    "peak_end":("Peak window ends",1,23,1,"h"),
    "charge_cap_a":("Battery charging ceiling",2,30,1,"A"),
    "ac_budget_a":("AC supply planning budget",1,32,1,"A"),
    "manual_override_minutes":("Manual control hold",5,1440,5,"min"),
    "storm_wind_mph":("Storm wind threshold",10,100,1,"mph"),
    "storm_gust_mph":("Storm gust threshold",10,150,1,"mph"),
    "manual_super_rate":("Manual super off-peak price",0,2,.0001,"USD/kWh"),
    "manual_off_rate":("Manual off-peak price",0,2,.0001,"USD/kWh"),
    "manual_peak_rate":("Manual peak price",0,2,.0001,"USD/kWh"),
}
SELECTS = {"planning_goal":["Save money","Backup first"],
           "weather_policy":["Automatic advice","Manual reserve"],
           "price_source":["PSEG Rate 195","Manual prices"]}
SWITCHES = {"automatic_enabled":"Automatic scheduling","storm_override":"Manual storm reserve",
            "commissioned":"Critical-load meter commissioned","switching_confirmed":"SUB charging and SBU supply confirmed"}
PSEG_URL = "https://www.psegliny.com/aboutpseglongisland/ratesandtariffs/rateinformation"
PSEG_BOOK = "https://www.psegliny.com/aboutpseglongisland/ratesandtariffs/-/media/A0FDA80A6FE44A45973922422E86BD9E.ashx"
