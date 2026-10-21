"""Pure protocol checks for the bounded, captured SOC recovery settings."""
import importlib.util,sys,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("bridge_recovery_core",Path(__file__).parents[1]/"bridge/core.py")
core=importlib.util.module_from_spec(spec);sys.modules[spec.name]=core;spec.loader.exec_module(core)
class RecoveryTests(unittest.TestCase):
 def test_scoped_recovery_values(self):
  c=core.BY_NAME["bms_return_battery_soc"]
  for v in ("025","060","090","095"):
   self.assertEqual(core.command(c,v),"BMSU2BC"+v)
  for v in ("000","020","026","100","025\rPOP00"):
   with self.assertRaises(ValueError):core.command(c,v)
