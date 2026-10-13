# SPDX-License-Identifier: Apache-2.0
"""Analytical and physical checks for the independent electrostatic oracle."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from scripts.validate_retained_assembly_em import assess, laplace_solve, response, static_reference


class RetainedEmReferenceTests(unittest.TestCase):
    def test_manufactured_harmonic_solution(self):
        x, y, z = np.indices((13, 13, 13)) / 12.
        expected = 1. + x + 2*y - z + x*y + x*z + y*z
        fixed = (x == 0) | (x == 1) | (y == 0) | (y == 1) | (z == 0) | (z == 1)
        result, residual = laplace_solve(fixed, np.where(fixed, expected, 0.))
        self.assertLess(residual, 1e-9)
        np.testing.assert_allclose(result, expected, atol=2e-9, rtol=0)

    def test_reference_charge_balance_reciprocity_and_passivity(self):
        result = static_reference(1)
        matrix = np.array(result['maxwell_matrix_f'])
        self.assertGreater(np.linalg.eigvalsh(matrix).min(), 0.)
        self.assertLess(result['reciprocity_relative_error'], 1e-8)
        self.assertLess(abs(result['net_electrode_charge_c']), 1e-24)
        self.assertGreater(result['capacitance_f'], 0.)

    def test_s11_capacitance_conversion(self):
        frequency = np.array([2.5e8, 5e8])
        capacitance = 7.5e-13
        impedance = 1/(1j*2*np.pi*frequency*capacitance)
        s = (impedance-50)/(impedance+50)
        actual = response({'frequency_hz': frequency.tolist(), 's_parameter_column': [
            {'real': s.real.tolist(), 'imag': s.imag.tolist()}]})
        np.testing.assert_allclose(actual['effective_capacitance_f'], capacitance, rtol=1e-13)

    def test_duration_refinement_label_and_stopping_are_independent(self):
        stopped = {'execution_status': 'completed', 'did_reach_requested_decay': False,
                   'stopping_reason': 'timestep_cap_before_requested_decay'}
        item = {'s11_real': [0.], 's11_imag': [0.], 'effective_capacitance_f': [1.],
                'stopping': stopped}
        runs = {name: dict(item) for name in
                ('base', 'duration', 'pml-distance', 'spatial', 'spatial-duration')}
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory/'static-reference.json').write_text(json.dumps([
                {'capacitance_f': 1.}, {'capacitance_f': 1.}]), encoding='utf-8')
            (directory/'responses.json').write_text(json.dumps(runs), encoding='utf-8')
            report = assess(directory)
        self.assertIn('duration_refined_capacitance_relative_error', report['metrics'])
        self.assertNotIn('time_refined_capacitance_relative_error', report['metrics'])
        alias = report['metric_aliases']['time_refined_capacitance_relative_error']
        self.assertEqual(alias['canonical_metric'], 'duration_refined_capacitance_relative_error')
        self.assertIn('not a timestep-refinement claim', alias['historical_semantics'])
        self.assertEqual(report['observable_sensitivity']['duration']['status'], 'accepted')
        self.assertFalse(report['stopping']['duration']['did_reach_requested_decay'])


if __name__ == '__main__':
    unittest.main()
