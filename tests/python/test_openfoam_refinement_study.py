# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import unittest

from python.spike_core.openfoam_refinement_study import RefinementStudyError, evaluate_refinement_study


def request(axis='mesh', steps=(.4,.2,.1), order=2):
    levels = []
    for i, step in enumerate(steps):
        levels.append({'case_sha256': f'{i+1:064x}', 'result_sha256': f'{i+10:064x}',
                       'geometry_sha256': 'a'*64, 'material_sha256': 'b'*64, 'source_sha256': 'c'*64,
                       'physical_time_s': 10, 'h_m': step if axis == 'mesh' else .01,
                       'time_step_s': step if axis == 'time' else .001,
                       'reference_temperature_k': 300, 'temperature_k': 305+2*step**order})
    return {'contract': 'spike/openfoam-refinement-study/v1', 'axis': axis, 'levels': levels}


class RefinementTests(unittest.TestCase):
    def test_second_order_mesh(self):
        result = evaluate_refinement_study(request())
        self.assertAlmostEqual(result['observed_order'], 2, places=9)
        self.assertAlmostEqual(result['richardson_temperature_rise_k'], 5, places=10)
        self.assertAlmostEqual(result['estimated_fine_error_k'], .02, places=10)
        self.assertAlmostEqual(result['fine_relative_change'], .06/5.02, places=10)
        self.assertFalse(result['production_qualified'])

    def test_nonuniform_time_ratios(self):
        result = evaluate_refinement_study(request('time', (.5,.2,.1), 1.5))
        self.assertAlmostEqual(result['observed_order'], 1.5, places=9)
        self.assertAlmostEqual(result['richardson_temperature_rise_k'], 5, places=10)

    def test_baseline_invariance(self):
        a = request()
        b = request()
        for level in b['levels']:
            level['reference_temperature_k'] += 700
            level['temperature_k'] += 700
        self.assertAlmostEqual(evaluate_refinement_study(a)['fine_relative_change'],
                               evaluate_refinement_study(b)['fine_relative_change'], places=12)

    def test_nonmonotonic_no_fabricated_order(self):
        value = request()
        value['levels'][1]['temperature_k'] = 304
        result = evaluate_refinement_study(value)
        self.assertEqual(result['status'], 'nonmonotonic')
        self.assertIsNone(result['observed_order'])

    def test_identical_and_zero_rise(self):
        value = request()
        for level in value['levels']:
            level['temperature_k'] = 300
        result = evaluate_refinement_study(value)
        self.assertIsNone(result['observed_order'])
        self.assertIsNone(result['fine_relative_change'])

    def test_monotonic_divergence_has_no_order(self):
        value = request()
        for level, temperature in zip(value['levels'], (301, 302, 304)):
            level['temperature_k'] = temperature
        result = evaluate_refinement_study(value)
        self.assertEqual(result['status'], 'no_supported_positive_order')
        self.assertIsNone(result['richardson_temperature_rise_k'])

    def test_four_six_eight_grid_ratio(self):
        result = evaluate_refinement_study(request(steps=(1/4, 1/6, 1/8), order=1))
        self.assertAlmostEqual(result['observed_order'], 1, places=9)

    def test_stale_inconsistent_and_nonfinite(self):
        for key, replacement in [('case_sha256', '1'.zfill(64)), ('result_sha256', 'a'.zfill(64)),
                                 ('geometry_sha256', 'e'*64), ('material_sha256', 'e'*64),
                                 ('source_sha256', 'e'*64), ('physical_time_s', 11),
                                 ('time_step_s', .002), ('temperature_k', float('nan')),
                                 ('temperature_k', True), ('temperature_k', 10**1000),
                                 ('h_m', .8), ('reference_temperature_k', 301)]:
            value = request()
            value['levels'][1][key] = replacement
            with self.subTest(key=key), self.assertRaises(RefinementStudyError):
                evaluate_refinement_study(value)


if __name__ == '__main__':
    unittest.main()
