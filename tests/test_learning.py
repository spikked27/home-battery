"""Recorded-load learning checks; synthetic history, no hardware or network."""
import importlib.util
from pathlib import Path
from datetime import datetime,timedelta,timezone
import unittest

spec=importlib.util.spec_from_file_location('load_learning',Path(__file__).parents[1]/'custom_components/home_battery/learning.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class LearningTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,23,12,tzinfo=timezone.utc)
        self.rows=[{'start':(self.now-timedelta(hours=h)).timestamp(),'mean':300 if (self.now-timedelta(hours=h)).weekday()<5 else 100} for h in range(1,337)]
    def test_selected_history_and_day_type(self):
        r=m.learn_load(self.rows,self.now,14)
        self.assertEqual(r['recorded_hours'],336);self.assertEqual(r['coverage_percent'],100)
        self.assertEqual(r['status'],'Ready')
        self.assertTrue(all(abs(v-100)<1e-9 for v in r['profile_w'])) # Saturday tomorrow
        self.assertTrue(all(abs(v-300)<1e-9 for v in r['today_profile_w']))
    def test_future_and_current_partial_hour_are_not_training_data(self):
        bad=self.rows+[{'start':self.now.timestamp(),'mean':9000},{'start':(self.now+timedelta(days=1)).timestamp(),'mean':9000}]
        self.assertEqual(m.learn_load(bad,self.now,14),m.learn_load(self.rows,self.now,14))
    def test_units_and_missing_are_not_zero_filled(self):
        r=m.learn_load([{'start':row['start'],'mean':row['mean']/1000} for row in self.rows],self.now,14,1000)
        self.assertAlmostEqual(r['expected_daily_kwh'],2.4)
        r=m.learn_load(self.rows[:23]+[{'start':self.rows[25]['start'],'mean':None}],self.now,14)
        self.assertEqual(r['recorded_hours'],23);self.assertEqual(r['profile_w'],[])
    def test_duplicate_hours_not_counted_twice(self):
        r=m.learn_load(self.rows+self.rows,self.now,7)
        self.assertEqual(r['recorded_hours'],168);self.assertEqual(r['coverage_percent'],100)
    def test_walk_forward_does_not_fit_the_held_out_spike(self):
        rows=[{'start':r['start'],'mean':100} for r in self.rows]
        rows[0]['mean']=1000
        result=m.learn_load(rows,self.now,14)
        self.assertGreater(result['typical_error_w'],0)
        self.assertGreater(result['validation_hours'],24)
    def test_real_zero_is_valid_and_invalid_ranges_rejected(self):
        rows=[{'start':r['start'],'mean':0} for r in self.rows]
        r=m.learn_load(rows,self.now,14)
        self.assertEqual(r['expected_daily_kwh'],0)
        self.assertIsNone(r['weighted_error_percent'])
        with self.assertRaises(ValueError):m.learn_load(rows,self.now,365)
    def test_no_history_explains_waiting(self):
        r=m.learn_load([],self.now,30)
        self.assertEqual(r['status'],'Waiting for history');self.assertEqual(r['available_days'],0)

if __name__=='__main__':unittest.main()
