# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1','Opt-in wx battery profile test')
class BatteryProfileTests(unittest.TestCase):
    def test_csv_step_profile_and_invalid_inputs(self):
        from spikes_studio.battery_panel import parse_current_profile
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'current.csv'
            path.write_text('time_s,current_a\n0,1\n10,-.5\n20,0\n')
            self.assertEqual(parse_current_profile(path),([0.,10.,20.],[1.,-.5]))
            for data in ('time,current\n0,1\n1,0\n','time_s,current_a\n0,1\n0,2\n','time_s,current_a\n0,nan\n1,2\n'):
                path.write_text(data)
                with self.assertRaises(ValueError):parse_current_profile(path)
