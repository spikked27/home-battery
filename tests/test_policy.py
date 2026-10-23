"""Real decisions and accounting boundaries, without energizing hardware."""
import importlib.util
from pathlib import Path
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

ROOT=Path(__file__).parents[1]/"custom_components/home_battery"
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/(name+".py"))
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module
p=load("policy");c=load("const")

class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.settings=dict(c.DEFAULTS)
        self.settings["commissioned"]=True
        self.d={"soc":80.,"load_w":500.,"charge_w":0.,"discharge_w":600.,"grid_voltage":120.,"fresh":True,"healthy":True,"mode":"Battery"}
        self.now=datetime(2026,10,14,16,tzinfo=ZoneInfo("America/New_York"))
        self.rates=p.pseg_rates(self.now,.1392)
    def plan(self):return p.make_plan(self.now,self.d,self.settings,self.rates)
    def test_prices(self):
        self.assertEqual(self.rates,{"Super off-peak":.12852,"Off-peak":.2321,"Peak":.518057})
        self.assertIsNone(p.pseg_rates(self.now.replace(year=2027),.1392))
    def test_peak_economic_discharge(self):self.assertEqual(self.plan().desired_priority,"SBU")
    def test_all_profiles_operate_while_learning(self):
        for goal in c.SELECTS['planning_goal']:
            with self.subTest(goal=goal):
                self.settings['planning_goal']=goal
                self.assertNotIn('peak_forecast_wh',self.d)
                self.assertEqual(self.plan().decision,'Use battery')
                self.now=self.now.replace(hour=23)
                self.assertEqual(self.plan().decision,'Charge')
                self.now=self.now.replace(hour=16)
    def test_outage_profile_keeps_extra_backup_but_still_shaves_peaks(self):
        base=self.plan()
        self.settings['planning_goal']='More Outage Protection'
        extra=self.plan()
        self.assertAlmostEqual(extra.reserve_soc,base.reserve_soc*1.5)
        self.assertEqual(extra.desired_priority,'SBU')
        self.d['soc']=(base.reserve_soc+extra.reserve_soc)/2
        self.assertEqual(self.plan().decision,'Recharge')
        self.settings['planning_goal']='More Savings'
        self.assertEqual(self.plan().decision,'Use battery')
    def test_profiles_never_reduce_user_floor_or_skip_protections(self):
        for goal in c.SELECTS['planning_goal']:
            with self.subTest(goal=goal):
                self.settings.update(planning_goal=goal,minimum_reserve=70)
                self.assertGreaterEqual(self.plan().reserve_soc,70)
                self.d['soc']=65
                self.assertEqual(self.plan().decision,'Recharge')
                self.d['healthy']=False
                self.assertIsNone(self.plan().desired_priority)
                self.d.update(healthy=True,soc=80)
                self.d['fresh']=False
                self.assertIsNone(self.plan().desired_priority)
                self.d['fresh']=True
    def test_legacy_preferences_normalize(self):
        self.assertEqual(p.normalize_planning_goal('Save money'),'More Savings')
        self.assertEqual(p.normalize_planning_goal('Backup first'),'More Outage Protection')
    def test_checked_forecast_can_release_energy_not_needed_for_peak(self):
        self.now=self.now.replace(hour=10);self.d['soc']=60
        self.assertEqual(self.plan().decision,'Save for peak')
        self.d['peak_forecast_wh']=500
        self.assertEqual(self.plan().decision,'Use battery')
        self.d['peak_forecast_wh']=-1
        self.assertEqual(self.plan().decision,'Save for peak')
    def test_low_soc_recharge(self):
        self.d["soc"]=10;self.assertEqual(self.plan().desired_priority,"SUB")
    def test_stale_never_switches(self):
        self.d["fresh"]=False;self.assertIsNone(self.plan().desired_priority)
    def test_alarm_never_switches(self):
        self.d["healthy"]=False;self.assertIsNone(self.plan().desired_priority)
    def test_outage_no_command(self):
        self.d["grid_voltage"]=0;self.assertEqual(self.plan().decision,"Outage");self.assertIsNone(self.plan().desired_priority)
    def test_tiny_load_losses(self):
        self.d.update(load_w=5.,discharge_w=73.);self.assertEqual(self.plan().desired_priority,"SUB")
    def test_measured_drain_floor(self):
        self.d["discharge_w"]=2000;self.assertGreater(self.plan().reserve_soc,70)
    def test_storm_prefers_grid(self):
        plan=p.make_plan(self.now,self.d,self.settings,self.rates,True)
        self.assertEqual(plan.desired_priority,"SUB");self.assertGreaterEqual(plan.reserve_soc,90)
    def test_high_charge_recovery_can_use_battery(self):
        self.d.update(high_charge_recovery=True,soc=100)
        self.assertEqual(self.plan().decision,'Battery recovery')
        self.assertEqual(self.plan().desired_priority,'SBU')
    def test_recovery_cannot_spend_outage_reserve(self):
        self.d.update(high_charge_recovery=True,soc=10)
        self.assertEqual(self.plan().desired_priority,'SUB')
    def test_reserve_recovery_avoids_chattering(self):
        self.d.update(priority="SUB",soc=30)
        self.assertEqual(self.plan().decision,"Recover reserve")
        self.d["soc"]=34
        self.assertEqual(self.plan().desired_priority,"SBU")
    def test_midnight_window(self):
        for hour in (22,23,0,5):self.assertEqual(p.tariff_window(self.now.replace(hour=hour)),"Super off-peak")
        self.assertEqual(p.tariff_window(self.now.replace(hour=6)),"Off-peak")
    def test_custom_charge_hours_do_not_reprice_pseg(self):
        self.settings.update(charge_start=12,charge_end=14)
        self.assertEqual(p.price_window(self.now.replace(hour=12),self.settings),"Off-peak")
    def test_federal_holiday_and_weekend(self):
        self.assertEqual(p.tariff_window(self.now.replace(month=11,day=26)),"Off-peak")
        self.assertEqual(p.tariff_window(self.now.replace(month=5,day=25)),"Off-peak")
        self.assertEqual(p.tariff_window(self.now.replace(day=17)),"Off-peak")
    def test_preserve_next_peak(self):
        self.now=self.now.replace(hour=12);self.d["soc"]=60
        self.assertEqual(self.plan().decision,"Save for peak")
    def test_dc_drain_not_credited_as_ac_delivery(self):
        self.d.update(load_w=5.,discharge_w=73.)
        money=p.money_rates(self.d,self.settings,.2)
        self.assertAlmostEqual(money["avoided"],.001)
    def test_outage_not_bill_savings(self):
        self.d["grid_voltage"]=0;self.assertEqual(p.money_rates(self.d,self.settings,.2)["avoided"],0)
    def test_missing_prices_pause_money(self):self.assertIsNone(p.money_rates(self.d,self.settings,None))
    def test_reference_meter_cannot_earn_savings(self):
        self.settings["commissioned"]=False
        self.assertIsNone(p.money_rates(self.d,self.settings,.2))
    def test_charging_conversion(self):
        self.d.update(mode="Line",charge_w=900.)
        self.assertAlmostEqual(p.money_rates(self.d,self.settings,.2)["charging"],.209)
    def test_cell_positions_and_ties(self):
        result=p.cell_extremes([3.7,3.6,3.7])
        self.assertEqual(result["highest_positions"],[1,3]);self.assertEqual(result["lowest_positions"],[2])
    def test_invalid_cells(self):
        for cells in ([None,3.7],[5,3.7],[]):self.assertIsNone(p.cell_extremes(cells))
    def test_nonfinite_rejected(self):
        self.d["soc"]=float('nan');self.assertIsNone(self.plan().desired_priority)

if __name__=="__main__":unittest.main()
