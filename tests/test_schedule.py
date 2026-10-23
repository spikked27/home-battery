"""Forecast illustration boundaries, without device/network access."""
import importlib
from pathlib import Path
import sys
import types
from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

package=types.ModuleType('schedule_test_package')
package.__path__=[str(Path(__file__).parents[1]/'custom_components/home_battery')]
sys.modules[package.__name__]=package
preview=importlib.import_module(package.__name__+'.schedule').preview_schedule
const=importlib.import_module(package.__name__+'.const')

class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,14,14,7,tzinfo=ZoneInfo('America/New_York'))
        self.settings=dict(const.DEFAULTS,automatic_enabled=True)
        self.data=dict(soc=80,load_w=500,average_load_w=500,discharge_w=600,charge_w=0,
                       grid_voltage=120,fresh=True,healthy=True,mode='Battery',priority='SBU')
        self.rates={'Super off-peak':.1,'Off-peak':.2,'Peak':.5}
    def run_preview(self,**kwargs):
        return preview(self.now,self.data,self.settings,self.rates,9,52,**kwargs)
    def test_learning_fallback_is_a_real_24_hour_plan(self):
        result=self.run_preview()
        self.assertEqual(result['basis'],'Current-load estimate')
        segments=result['segments']
        self.assertEqual(segments[0]['start'],self.now.timestamp())
        self.assertEqual(segments[-1]['end']-segments[0]['start'],86400)
        self.assertEqual({s['action'] for s in segments},{'battery','utility','charge'})
        self.assertTrue(all(a['end']==b['start'] for a,b in zip(segments,segments[1:])))
        for point in result['points']: self.assertTrue(0<=point['soc']<=100)
    def test_preview_never_mutates_live_state_or_settings(self):
        before=dict(self.data);settings=dict(self.settings);guard={'target_latched':True}
        self.run_preview(guard=guard)
        self.assertEqual(self.data,before);self.assertEqual(self.settings,settings)
        self.assertEqual(guard,{'target_latched':True})
    def test_off_is_explicitly_a_preview(self):
        self.settings['automatic_enabled']=False
        result=self.run_preview()
        self.assertEqual(result['status'],'Preview only')
        self.assertIn('will not run',result['message'])
    def test_stale_alarms_and_outage_never_show_a_promised_schedule(self):
        for change in ({'fresh':False},{'healthy':False},{'has_bms_alarm':True},{'grid_voltage':0}):
            with self.subTest(change=change):
                data=self.data|change
                self.assertEqual(preview(self.now,data,self.settings,self.rates,9,52)['segments'],[])
    def test_unknown_cell_recovery_never_invents_charge_permission(self):
        result=self.run_preview(guard={'cell_latched':True})
        self.assertNotIn('charge',{s['action'] for s in result['segments']})
    def test_target_latch_prevents_early_top_up(self):
        self.now=self.now.replace(hour=23)
        self.data.update(soc=92,mode='Line',priority='SUB',discharge_w=0)
        result=self.run_preview(guard={'target_latched':True})
        self.assertEqual(result['segments'][0]['action'],'utility')
        self.assertEqual(result['segments'][0]['soc_end'],92)
    def test_cleared_alarm_latch_can_recover_with_target_without_mutating_live_guard(self):
        self.data.update(soc=92,mode='Line',priority='SUB',discharge_w=16,load_w=10,average_load_w=10)
        guard={'target_latched':True,'alarm_latched':True,'cell_latched':False}
        result=self.run_preview(guard=guard)
        charge=[s for s in result['segments'] if s['action']=='charge']
        self.assertTrue(charge,'A cleared alarm latch must not block the entire next day')
        self.assertLessEqual(charge[0]['soc_start'],90)
        self.assertGreaterEqual(max(p['soc'] for p in result['points']),95)
        self.assertLess(sum(s['end']-s['start'] for s in charge)/3600,2,'Idle draw must not keep predicted charging stuck just below target all night')
        self.assertEqual(guard,{'target_latched':True,'alarm_latched':True,'cell_latched':False})
    def test_checked_weekday_forecast_used_but_incomplete_never_zero_filled(self):
        weekly={str(d):[500]*24 for d in range(7)}
        self.assertEqual(self.run_preview(weekly=weekly)['basis'],'Checked load forecast')
        weekly['3'][12]=None
        self.assertEqual(self.run_preview(weekly=weekly)['segments'],[])
    def test_dst_is_24_elapsed_hours_with_offsets_preserved(self):
        self.now=self.now.replace(month=11,day=1,hour=0)
        result=self.run_preview()
        self.assertEqual(result['end']-result['start'],86400)
        local_end=datetime.fromtimestamp(result['end'],self.now.tzinfo)
        self.assertEqual(local_end.hour,23)
    def test_missing_charge_limit_does_not_invent_a_completion_time(self):
        self.assertEqual(preview(self.now,self.data,self.settings,self.rates,None,52)['segments'],[])
    def test_recovered_reserve_is_held_until_next_cheap_window(self):
        self.data.update(soc=25,reserve_hold=True,priority='SUB',mode='Line',discharge_w=0,load_w=300,average_load_w=300)
        result=self.run_preview()
        before_night=[s for s in result['segments'] if s['start']<self.now.replace(hour=22,minute=0).timestamp()]
        self.assertTrue(before_night)
        self.assertTrue(all(s['action']=='utility' for s in before_night))
        self.assertTrue(any(s['action']=='charge' for s in result['segments']))

if __name__=='__main__': unittest.main()
