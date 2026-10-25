"""Cold-aware timing, learning and budget boundaries; no device commands."""
import importlib
import sys
import types
import unittest
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo

pkg=types.ModuleType('thermal_test_package');pkg.__path__=[str(Path(__file__).parents[1]/'custom_components/home_battery')];sys.modules[pkg.__name__]=pkg
t=importlib.import_module(pkg.__name__+'.thermal')
policy=importlib.import_module(pkg.__name__+'.policy')
guard=importlib.import_module(pkg.__name__+'.charge_guard')
preview=importlib.import_module(pkg.__name__+'.schedule').preview_schedule
defaults=importlib.import_module(pkg.__name__+'.const').DEFAULTS

class ThermalTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,26,22,tzinfo=ZoneInfo('America/New_York'))
        self.s=dict(defaults,thermal_enabled=True,thermal_availability=True,automatic_enabled=True)
        self.d=dict(soc=50,load_w=300,charge_w=0,discharge_w=0,voltage=54,fresh=True,healthy=True,
                    cold_temperature=16,grid_voltage=120,cells=[3.8]*14,priority='SUB',mode='Line')
        self.rates={'Super off-peak':.1,'Off-peak':.2,'Peak':.5}
        self.c={'charge_amps':9,'cost':0,'price':.2,'model':{'ready':True,'cooling_c_per_hour':[-.2]*24,'recent_cooling_c_per_hour':0,'validation_error_c_per_hour':.1}}
        self.d['thermal_context']=self.c
    def advice(self,now=None):return t.thermal_advice(now or self.now,self.d,self.s,self.c)
    def test_delay_needed_charging_and_finish_in_window(self):
        a=self.advice();self.assertGreater(a['delay_until'],self.now.timestamp())
        self.assertLessEqual(a['delay_until']+a['estimated_charge_hours']*3600,a['window_end']+1)
        self.assertEqual(policy.make_plan(self.now,self.d,self.s,self.rates).decision,'Wait to charge')
    def test_started_charge_does_not_slide_later_as_soc_rises(self):
        self.c['started_window_end']=t.next_window(self.now,self.s)[1]
        for soc in [50,70,88]:
            self.d['soc']=soc
            self.assertEqual(policy.make_plan(self.now,self.d,self.s,self.rates).decision,'Charge')
    def test_reserve_and_storm_override_delay(self):
        self.d['soc']=2
        self.assertEqual(policy.make_plan(self.now,self.d,self.s,self.rates).decision,'Charge')
        self.assertEqual(policy.make_plan(self.now,self.d,self.s,self.rates,True).decision,'Keep ready')
    def test_learning_and_no_forecast_do_not_disable_normal_charging(self):
        self.c['model']['ready']=False
        self.assertEqual(self.advice()['status'],'Learning cooling pattern')
        self.assertEqual(policy.make_plan(self.now,self.d,self.s,self.rates).decision,'Charge')
    def test_falling_temperature_advances_start(self):
        self.d['cold_temperature']=10;self.c['model']['cooling_c_per_hour']=[-1]*24
        self.assertLessEqual(self.advice()['delay_until'],self.now.timestamp()+1800)
    def test_paid_advance_requires_price_budget_and_not_full(self):
        day=self.now.replace(hour=20);self.d['cold_temperature']=9;self.c['model']['cooling_c_per_hour']=[-1]*24
        self.assertTrue(self.advice(day)['early_charge'])
        self.c['cost']=.25;self.assertFalse(self.advice(day)['early_charge'])
        self.c['cost']=0;self.c['price']=None;self.assertFalse(self.advice(day)['early_charge'])
        self.c['price']=.2;self.d['soc']=92;self.assertFalse(self.advice(day)['early_charge'])
    def test_cold_or_missing_temperature_cannot_enable_utility_charging(self):
        for temp in [7,None]:
            self.d['cold_temperature']=temp
            self.assertTrue(guard.ChargeGuard().evaluate(self.d,self.s,0))
            self.assertEqual(policy.make_plan(self.now,self.d,self.s,self.rates).decision,'Cold hold')
    def test_charge_floor_does_not_block_daytime_discharge(self):
        self.d.update(soc=90,cold_temperature=7)
        self.assertEqual(policy.make_plan(self.now.replace(hour=16),self.d,self.s,self.rates).decision,'Use battery')
    def test_no_heat_credit_and_no_mutation(self):
        self.c['model']['charging_net_change_c_per_hour']=3
        before=repr((self.c,self.d,self.s));self.advice()
        self.assertEqual(before,repr((self.c,self.d,self.s)))
        self.assertLess(t.temperature_at(0,3600,10,self.c['model'],self.now.tzinfo),10)
    def test_dst_windows_are_elapsed_nine_or_seven_hours(self):
        for date,hours in [(datetime(2026,10,31,22,tzinfo=self.now.tzinfo),9),(datetime(2026,3,7,22,tzinfo=self.now.tzinfo),7)]:
            start,end=t.next_window(date,self.s);self.assertEqual((end-start)/3600,hours)
    def test_gap_and_charging_data_cannot_be_passive_learning(self):
        h=t.ThermalHistory();h.samples=[[i*3600,20-i*.1,200] for i in range(30)]
        self.assertFalse(h.model(self.now.tzinfo)['ready'])
        h.samples=[[i*7200,20-i*.1,0] for i in range(30)]
        self.assertFalse(h.model(self.now.tzinfo)['ready'])
    def test_history_learns_passive_cooling_with_holdout(self):
        h=t.ThermalHistory();h.samples=[[i*3600,20-i*.1,0] for i in range(30)]
        m=h.model(self.now.tzinfo);self.assertTrue(m['ready']);self.assertAlmostEqual(m['cooling_c_per_hour'][0],-.1)
    def test_budget_persists_and_long_gap_fails_closed(self):
        h=t.ThermalHistory();h.observe(self.now,self.d,self.s,.2,True)
        self.d['charge_w']=500;h.observe(self.now+timedelta(seconds=30),self.d,self.s,.2,True)
        restored=t.ThermalHistory(h.saved());restored.observe(self.now+timedelta(seconds=60),self.d,self.s,.2,True)
        self.assertGreater(restored.cost,0)
        restored=t.ThermalHistory(restored.saved());restored.observe(self.now+timedelta(minutes=5),self.d,self.s,.2,False)
        self.assertTrue(restored.budget_uncertain)
        restored.observe(self.now+timedelta(days=1),self.d,self.s,.2,False);self.assertEqual(restored.cost,0);self.assertFalse(restored.budget_uncertain)
    def test_timing_stop_does_not_wait_for_source_switch(self):
        self.d['scheduled_charge_block']=True
        self.assertIn('deferred',guard.ChargeGuard().evaluate(self.d,self.s,0))
    def test_preview_does_not_pulse_charge_after_it_has_started(self):
        r=preview(self.now,self.d,self.s,self.rates,9,54)
        phases=[row['action'] for row in r['segments'] if row['start']<t.next_window(self.now,self.s)[1]]
        self.assertEqual(phases.count('charge'),1)

if __name__=='__main__':unittest.main()
