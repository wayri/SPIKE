from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.thermal_report import report


class ThermalMargins(unittest.TestCase):
    def assess(self,setup,data=None):
        return report({'components':[{'id':'one','ref':'Q1','temperature_k':300,'parameters':{'thermal_assessment':setup}}]}, {'data':data or {}})['parts'][0]
    def test_recorded_kelvin_margin_and_threshold(self):
        row=self.assess({'max_junction_c':150},{'element_temperature_k':{'Q1':[400,413.15]}})
        self.assertEqual(row['status'],'warning');self.assertAlmostEqual(row['headroom_c'],10)
        self.assertEqual(self.assess({'max_junction_c':150,'supplied_temperature_c':150})['status'],'exceeded')
    def test_no_inference_from_declared_temperature_or_terminal_power(self):
        self.assertEqual(self.assess({'max_junction_c':150},{'element_power_w':{'Q1':[100]}})['status'],'unavailable')
    def test_explicit_estimate_requires_conditions(self):
        setup={'max_junction_c':150,'theta_ja_k_w':40,'steady_power_w':2,'ambient_c':25}
        self.assertEqual(self.assess(setup)['status'],'unavailable')
        row=self.assess(setup|{'conditions_evidence':'Measured effective resistance on actual board'})
        self.assertEqual(row['peak_junction_c'],105);self.assertEqual(row['headroom_c'],45)
    def test_invalid_trace_is_not_passed(self):
        self.assertEqual(self.assess({'max_junction_c':150},{'element_temperature_k':{'Q1':[float('nan')]}})['status'],'unavailable')
