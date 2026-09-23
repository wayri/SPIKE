# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
import unittest
from python.spike_core.fdtd_completion import screen_fdtd_completion

GOOD='Create FDTD operator\nExcitation signal length is: 20 timesteps\nTimestep: 100 || Energy: ~1e-9 (-40.80dB)\nTime for 100 iterations with 100 cells\n'

class CompletionTests(unittest.TestCase):
    def screen(self,log):return screen_fdtd_completion(log,expected_runs=4,end_criteria=1e-4)['screen_passed']
    def test_complete_four_excitations(self):self.assertTrue(self.screen(GOOD*4))
    def test_missing_or_incomplete_runs(self):
        for log in ('',GOOD*3,GOOD*5,GOOD*3+GOOD.replace('Time for','Missing'),
                    GOOD*3+GOOD.replace('-40.80','-20.00'),
                    GOOD*3+GOOD.replace('20 timesteps','200 timesteps'),
                    GOOD*4+'Max. number of timesteps was reached before the end-criteria'):
            with self.subTest(log=log[-100:]):self.assertFalse(self.screen(log))
    def test_invalid_budget_and_criterion(self):
        for criterion in (0,1,True,float('nan')):
            with self.assertRaises(ValueError):screen_fdtd_completion(GOOD,expected_runs=1,end_criteria=criterion)
