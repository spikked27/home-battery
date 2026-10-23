"""Supervisory limits, hysteresis and restart recovery using the actual event."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest

# Load pure modules without requiring HA for these tests.
ROOT=Path(__file__).parents[1]/'custom_components/home_battery'
PACKAGE='guard_test_package'
package=types.ModuleType(PACKAGE);package.__path__=[str(ROOT)];sys.modules[PACKAGE]=package
spec=importlib.util.spec_from_file_location(PACKAGE+'.charge_guard',ROOT/'charge_guard.py')
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)

class GuardTests(unittest.TestCase):
    def setUp(self):
        self.guard=module.ChargeGuard()
        self.settings={'charge_target':95,'charge_cell_ceiling':4.12}
        self.d={'soc':62.2,'cells':[4.05]*14,'fresh':True,'healthy':True,'has_bms_alarm':False}
    def evaluate(self,t=0): return self.guard.evaluate(self.d,self.settings,t)
    def test_soc_jump_stops_before_bms_cutoff(self):
        self.assertFalse(self.evaluate())
        self.d['soc']=100
        self.assertIn('target reached',self.evaluate())
        self.assertTrue(self.guard.target_latched)
    def test_cell_limit_independent_of_soc(self):
        self.d['cells'][13]=4.141
        self.assertIn('50 mV',self.evaluate())
        self.assertTrue(self.guard.cell_latched)
    def test_no_chatter_and_stable_recovery(self):
        self.d['soc']=95;self.evaluate()
        self.d['soc']=94.9;self.assertTrue(self.evaluate(100))
        self.d['soc']=90;self.assertIn('3 minutes',self.evaluate(101))
        self.assertTrue(self.evaluate(280))
        self.assertFalse(self.evaluate(281))
    def test_alarm_resets_recovery_timer(self):
        self.d['soc']=100;self.evaluate();self.d['soc']=80;self.evaluate(1)
        self.d['has_bms_alarm']=True;self.assertIn('alarm',self.evaluate(170))
        self.d['has_bms_alarm']=False;self.assertTrue(self.evaluate(180))
        self.assertFalse(self.evaluate(360))
    def test_recovery_timer_not_replayed_after_restart(self):
        self.d['soc']=100;self.evaluate()
        self.guard=module.ChargeGuard(self.guard.saved());self.d['soc']=80
        self.assertIn('3 minutes',self.evaluate(1000))
        self.assertFalse(self.evaluate(1180))
    def test_missing_cells_or_stale_data_block(self):
        self.d['cells'][3]=None;self.assertTrue(self.evaluate())
        self.d['cells']=[4.0]*14;self.d['fresh']=False;self.assertTrue(self.evaluate())
    def test_alarm_alone_requires_stable_recovery(self):
        self.d['has_bms_alarm']=True;self.evaluate()
        self.d['has_bms_alarm']=False;self.assertTrue(self.evaluate(1))
        self.assertFalse(self.evaluate(181))
    def test_disabling_limit_does_not_clear_latched_cell_event(self):
        self.d['cells'][0]=4.15;self.evaluate();self.settings['charge_cell_ceiling']=0
        self.assertTrue(self.evaluate())
    def test_cell_recovery_requires_full_gap(self):
        self.d['cells'][0]=4.15;self.evaluate()
        self.d['cells']=[4.08]*14;self.assertTrue(self.evaluate(100))
        self.d['cells']=[4.06]*14;self.assertTrue(self.evaluate(101))
        self.assertFalse(self.evaluate(281))

if __name__=='__main__': unittest.main()
