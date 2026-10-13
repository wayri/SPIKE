"""Independent ODE, conservation and real external-solver PWM-volume checks.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Yawar B (wayri) and SPIKE contributors.
"""
import os
from pathlib import Path
import unittest

import numpy as np

from examples.converter.run_pwm_volume_validation import (
    uniform_case, switched_reference, assert_uniform_conservation,
    correlate_uniform_calculix, nonuniform_capacity_distinction, retained_board_package_replay,
)
from python.spike_core.calculix_runtime import probe_calculix_runtime
from python.spike_core.pwm_volume_electrothermal import run_pwm_volume_electrothermal


def endpoint(result):
    electrical = result['windows'][-1]['electrical_cycles'][-1]
    return np.array([electrical['inductor_current_a'], electrical['output_voltage_v'],
                     result['frames'][-1]['node_temperatures_k'][0]])


class SwitchedReferenceTests(unittest.TestCase):
    def test_reference_is_step_converged(self):
        coarse = switched_reference({'cycles': 8}, step=2e-7)[-1]
        fine = switched_reference({'cycles': 8}, step=1e-7)[-1]
        for key in ('inductor_current_a', 'output_voltage_v', 'temperature_k'):
            self.assertAlmostEqual(coarse[key], fine[key], delta=1e-8)
        self.assertGreater(fine['temperature_k'], 300.)


class NativeVolumeCorrelationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get('SPIKE_PWM_TEST_LIBRARY')
        if not path:
            raise unittest.SkipTest('SPIKE_PWM_TEST_LIBRARY required for actual native correlation')
        from python.spikes.native_abi import load_native_library
        cls.library = load_native_library(Path(path))
        cls.cases = [uniform_case(step=step) for step in (2e-6, 1e-6, .5e-6)]
        cls.results = [run_pwm_volume_electrothermal(raw, library=cls.library) for raw in cls.cases]

    def test_all_device_heat_equals_stored_energy_at_every_frame(self):
        for result in self.results:
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(len(result['frames']), len(result['windows'])+1)
            self.assertEqual(result['completed_cycles'], 80)
            self.assertLess(assert_uniform_conservation(result), 2e-8)
            for name in ('Rw', 'SH', 'SL', 'Load'):
                self.assertGreater(result['energy'][name], 0)
            self.assertLess(abs(result['energy']['electrical_balance_j']), 1e-10)
            physical = sum(result['energy'][name] for name in ('Rw', 'SH', 'SL', 'Load'))
            stored = .01*(result['frames'][-1]['node_temperatures_k'][0]-300)
            self.assertAlmostEqual(physical, stored, delta=2e-10)
            self.assertGreater(result['energy']['be_numerical_dissipation_j'], 1e-7)
            # Numerical dissipation is an electrical discretization ledger,
            # not an extra physical thermal source.
            self.assertGreater(abs(physical+result['energy']['be_numerical_dissipation_j']-stored), 1e-7)

    def test_actual_native_switching_converges_toward_independent_ode(self):
        reference = switched_reference({'cycles': 80}, step=5e-8)[-1]
        target = np.array([reference['inductor_current_a'], reference['output_voltage_v'],
                           reference['temperature_k']])
        errors = [float(np.linalg.norm(endpoint(result)-target)) for result in self.results]
        self.assertGreater(errors[0], 1.5*errors[1], errors)
        self.assertGreater(errors[1], 1.5*errors[2], errors)
        self.assertLess(errors[-1], .05, errors)
        absolute_errors = [np.abs(endpoint(result)-target) for result in self.results]
        for index, gate in enumerate((.005, .002, .005)):
            self.assertGreater(absolute_errors[0][index], 1.5*absolute_errors[1][index])
            self.assertGreater(absolute_errors[1][index], 1.5*absolute_errors[2][index])
            self.assertLess(absolute_errors[-1][index], gate)

    def test_window_refinement_at_fixed_electrical_step(self):
        results = [run_pwm_volume_electrothermal(uniform_case(step=2.5e-7, window=w),
                                                library=self.library) for w in (8, 4, 2, 1)]
        target = endpoint(results[-1])
        errors = [float(np.linalg.norm(endpoint(result)-target)) for result in results[:-1]]
        self.assertGreater(errors[0], 2*errors[1], errors)
        self.assertGreater(errors[1], 2*errors[2], errors)
        self.assertLess(errors[0], .01, errors)

    @unittest.skipUnless(probe_calculix_runtime()['available'], 'Separately installed CalculiX unavailable')
    def test_calculix_actual_uniform_full_history(self):
        check = correlate_uniform_calculix(self.cases[-1], self.results[-1])
        self.assertLessEqual(check['maximum_temperature_difference_k'], 6e-5)
        self.assertEqual(len(check['external_history']['frames']), 81)
        self.assertRegex(check['external_history']['execution']['solver_version'], r'^\d+\.\d+')


@unittest.skipUnless(probe_calculix_runtime()['available'], 'Separately installed CalculiX unavailable')
class NonuniformCapacityCorrelationTests(unittest.TestCase):
    def test_known_nonuniform_cross_solver_difference_is_not_hidden(self):
        result = nonuniform_capacity_distinction()
        self.assertFalse(result['cross_solver_agreement'])
        self.assertGreater(result['cross_solver_difference_k'], .05)
        self.assertLess(result['calculix_centroid_oracle_error_k'], 6e-5)
        self.assertLess(result['spike_consistent_oracle_error_k'], 1e-8)


@unittest.skipUnless(probe_calculix_runtime()['available'], 'Separately installed CalculiX unavailable')
class RetainedBoardPackageCorrelationTests(unittest.TestCase):
    def test_actual_retained_board_package_history_replay(self):
        directory = Path(__file__).resolve().parents[2]/'.local/transient-thermal-validation'
        if not (directory/'calculix.json').is_file():
            self.skipTest('Original OCC-meshed retained board/package fixture not present locally')
        result = retained_board_package_replay(directory)
        self.assertTrue(result['fresh_calculix_execution'])
        self.assertEqual(len(result['occurrences']), 3)
        self.assertGreater(result['nodes'], 27)
        self.assertLess(result['saved_spike_maximum_difference_k'], 1e-8)
        self.assertGreater(len(result['frames']), 1)


if __name__ == '__main__':
    unittest.main()
