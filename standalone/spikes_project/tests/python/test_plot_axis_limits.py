import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.plot_interactions import axis_limits

class AxisLimits(unittest.TestCase):
    def test_ranges(self):
        self.assertEqual(axis_limits('-1e-3, 2e-3'),(-.001,.002))
        self.assertEqual(axis_limits('1, 100','log'),(1,100))
        for value in ('1,1','2,1','nan,2','0,inf','1','1,2,3'):
            with self.assertRaises(ValueError):axis_limits(value)
        with self.assertRaises(ValueError):axis_limits('0,1','log')
