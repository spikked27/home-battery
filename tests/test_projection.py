"""Pure what-if model checks; no HA, broker or inverter calls."""
import importlib
from pathlib import Path
import sys
import types
from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

package=types.ModuleType("projection_test_package")
package.__path__=[str(Path(__file__).parents[1]/"custom_components/home_battery")]
sys.modules[package.__name__]=package
project=importlib.import_module(package.__name__+".projection").project_savings
DEFAULTS=importlib.import_module(package.__name__+".const").DEFAULTS

class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,15,12,tzinfo=ZoneInfo("America/New_York"))
        self.settings=dict(DEFAULTS)
        self.rates={"Super off-peak":.1,"Off-peak":.2,"Peak":.5}
    def run_model(self,amps=30,profile=None):
        return project(self.now,profile or [330.]*24,self.settings,self.rates,amps,52.)
    def test_charge_limit_changes_sustainable_shift(self):
        slow=self.run_model(2);fast=self.run_model(30)
        self.assertLess(slow["shifted_kwh_day"],fast["shifted_kwh_day"])
        self.assertGreater(fast["day"],0)
    def test_no_charging_cannot_spend_free_starting_energy(self):
        result=self.run_model(0)
        self.assertEqual(result["shifted_kwh_day"],0)
        self.assertLessEqual(result["day"],0)
    def test_readback_limits_change_savings_and_missing_limits_disable_projection(self):
        self.settings.update(backup_hours=1)
        original=project(self.now,[330.]*24,self.settings,self.rates,30,52)
        limited=project(self.now,[330.]*24,self.settings,self.rates,30,52,
                        inverter_limits={'inverter_limits_ready':True,'inverter_grid_soc':20,'inverter_shutdown_soc':10})
        self.assertLess(limited['shifted_kwh_day'],original['shifted_kwh_day'])
        self.assertIsNone(project(self.now,[330.]*24,self.settings,self.rates,9,52,inverter_limits={'inverter_limits_ready':False}))
    def test_run_rates_are_labeled_and_consistent(self):
        result=self.run_model()
        self.assertAlmostEqual(result["year"],result["day"]*365.25)
        self.assertAlmostEqual(result["month"],result["year"]/12)
        self.assertIn("run rate",result["assumptions"][0])
    def test_missing_data_not_zero_savings(self):
        self.assertIsNone(project(self.now,[330.]*23,self.settings,self.rates,2,52))
        self.assertIsNone(project(self.now,[330.]*24,self.settings,None,2,52))
        self.assertIsNone(project(self.now,[330.]*24,self.settings,self.rates,None,52))
    def test_outage_preference_still_saves_with_extra_headroom(self):
        base=self.run_model()
        self.settings["planning_goal"]="More Outage Protection"
        result=self.run_model()
        self.assertGreater(result["shifted_kwh_day"],0)
        self.assertLessEqual(result["shifted_kwh_day"],base["shifted_kwh_day"])
    def test_reference_flag_does_not_disable_simulation(self):
        self.settings["commissioned"]=False
        self.assertIsNotNone(self.run_model())
    def test_larger_reserve_cannot_increase_shift(self):
        base=self.run_model();self.settings["backup_hours"]=12
        self.assertLess(self.run_model()["shifted_kwh_day"],base["shifted_kwh_day"])
    def test_cannot_shift_more_than_daily_cheap_battery_allocation(self):
        result=self.run_model()
        reserve_dc=self.settings['backup_hours']*(330/.9+self.settings['overhead_w'])/1000*(1+self.settings['reserve_margin']/100)
        usable_dc=self.settings['capacity_kwh']*self.settings['charge_target']/100-reserve_dc
        self.assertLessEqual(result['shifted_kwh_day'],usable_dc*.9+1e-6,'Expensive reserve charging must not create extra discretionary daily cycles')
    def test_legacy_percentage_does_not_change_savings_model(self):
        base=self.run_model()
        self.settings['minimum_reserve']=90
        self.assertEqual(self.run_model(),base)

if __name__=="__main__": unittest.main()
