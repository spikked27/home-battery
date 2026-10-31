"""Pure protocol checks for the bounded, captured SOC recovery settings."""
import importlib.util,sys,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("bridge_recovery_core",Path(__file__).parents[1]/"bridge/core.py")
core=importlib.util.module_from_spec(spec);sys.modules[spec.name]=core;spec.loader.exec_module(core)
class RecoveryTests(unittest.TestCase):
 def test_verified_low_soc_values_remain_a_bounded_allowlist(self):
  self.assertEqual(core.command(core.BY_NAME['bms_shutdown_soc'],'005'),'BMSSDC005')
  self.assertEqual(core.command(core.BY_NAME['bms_return_utility_soc'],'010'),'BMSB2UC010')
  self.assertIn('44.0',core.VERIFIED_VALUES['back_to_grid_voltage'])
  for name,value in [('bms_shutdown_soc','000'),('bms_shutdown_soc','001'),('bms_return_utility_soc','005'),('bms_return_utility_soc','015')]:
   with self.assertRaises(ValueError):core.command(core.BY_NAME[name],value)
 def test_scoped_recovery_values(self):
  c=core.BY_NAME["bms_return_battery_soc"]
  for v in ("025","060","090","095"):
   self.assertEqual(core.command(c,v),"BMSU2BC"+v)
  for v in ("000","020","026","100","025\rPOP00"):
   with self.assertRaises(ValueError):core.command(c,v)
