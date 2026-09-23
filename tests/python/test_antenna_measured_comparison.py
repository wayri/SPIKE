# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
import math
import unittest
from python.spike_core.antenna_measured_comparison import compare_forward_gain, evaluate_temporal_admission


class MeasuredGainTests(unittest.TestCase):
    def test_truncated_excitation_is_not_a_physical_comparison(self):
        log='Cutting to max number of timesteps! Time for 1800 iterations with 300000 cells'
        result=evaluate_temporal_admission(log,.15)
        self.assertEqual(result['status'],'failed_numerical_admission')
        self.assertFalse(result['checks']['complete_excitation'])
        self.assertFalse(result['checks']['pec_power_balance'])

    def test_gain_is_not_directivity_or_realized_gain(self):
        result=compare_forward_gain(radiation_intensity_w_sr=1/math.pi,
            accepted_power_w=2,radiated_power_w=1,measured_gain_dbd=0,
            dbd_to_dbi_db=2.16,measurement_accuracy_db=.5)
        self.assertAlmostEqual(result['accepted_power_gain_dbi'],10*math.log10(2))
        self.assertAlmostEqual(result['forward_directivity_dbi'],10*math.log10(4))
        self.assertFalse(result['measured_qualification'])

    def test_exact_agreement_does_not_qualify_geometry(self):
        result=compare_forward_gain(radiation_intensity_w_sr=10**(.926)/(4*math.pi),
            accepted_power_w=1,radiated_power_w=1,measured_gain_dbd=7.1,
            dbd_to_dbi_db=2.16,measurement_accuracy_db=.5)
        self.assertTrue(result['inside_reported_measurement_accuracy'])
        self.assertFalse(result['measured_qualification'])

    def test_nonfinite_or_nonpositive_rejected(self):
        for value in [0,-1,float('nan'),float('inf'),True]:
            with self.assertRaises(ValueError):
                compare_forward_gain(radiation_intensity_w_sr=value,accepted_power_w=1,
                    radiated_power_w=1,measured_gain_dbd=7.1,dbd_to_dbi_db=2.16,measurement_accuracy_db=.5)
