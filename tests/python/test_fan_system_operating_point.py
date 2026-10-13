# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Independent algebraic oracles; synthetic data are not vendor evidence."""
import copy
import math
import unittest

from python.spike_core.fan_system_operating_point import (
    REQUEST_CONTRACT, FanSystemOperatingPointError, curve_digest,
    solve_fan_system_operating_point,
)


def source():
    return {'reference': 'Original synthetic analytical fixture, not vendor data',
            'sha256': 'a' * 64, 'review_status': 'assumed'}


def request():
    curve = [{'flow_m3_s': 0, 'pressure_pa': 100},
             {'flow_m3_s': 2, 'pressure_pa': 100}]
    return {'contract': REQUEST_CONTRACT,
            'fan': {'model_id': 'synthetic-constant-pressure', 'configuration': 'series',
                    'installed_count': 1, 'active_count': 1, 'curve': curve,
                    'curve_sha256': curve_digest(curve), 'source': source()},
            'system': {'common_resistance_pa_s2_m6': 0, 'source': source(),
                       'passages': [{'id': 'channel-A', 'resistance_pa_s2_m6': 100,
                                     'min_flow_m3_s': 0, 'source': source(), 'heat_loads': [
                                         {'occurrence_id': 'Blade-1', 'site_id': 'Q129',
                                          'heat_w': 120, 'source': source()},
                                         {'occurrence_id': 'Blade-1', 'site_id': 'Q10',
                                          'heat_w': 240, 'source': source()}]}]},
            'air': {'density_kg_m3': 1.2, 'specific_heat_j_kg_k': 1000,
                    'inlet_temperature_k': 300},
            'air_limits': {'min_total_flow_m3_s': 0, 'max_outlet_temperature_k': 350}}


def update_curve(raw, points):
    raw['fan']['curve'] = [{'flow_m3_s': q, 'pressure_pa': p} for q, p in points]
    raw['fan']['curve_sha256'] = curve_digest(raw['fan']['curve'])


class FanSystemOperatingPointTests(unittest.TestCase):
    def assert_error(self, raw, code):
        with self.assertRaises(FanSystemOperatingPointError) as context:
            solve_fan_system_operating_point(raw)
        self.assertEqual(context.exception.code, code)

    def test_constant_pressure_closed_form_and_downstream_energy(self):
        raw = request()
        before = copy.deepcopy(raw)
        result = solve_fan_system_operating_point(raw)
        self.assertEqual(raw, before)
        point = result['operating_point']
        self.assertAlmostEqual(point['total_flow_m3_s'], math.sqrt(100 / 100), places=11)
        self.assertLessEqual(abs(point['pressure_residual_pa']), point['residual_tolerance_pa'])
        stages = result['passages'][0]['stages']
        self.assertAlmostEqual(stages[0]['outlet_temperature_k'], 300.1)
        self.assertAlmostEqual(stages[1]['inlet_temperature_k'], 300.1)
        self.assertAlmostEqual(stages[1]['outlet_temperature_k'], 300.3)
        self.assertAlmostEqual(result['air_summary']['energy_residual_w'], 0, places=8)
        self.assertTrue(result['not_resolved_CFD'])
        self.assertFalse(result['board_convection_inferred'])
        self.assertEqual(result['model_status'], 'approximate')
        self.assertEqual(result['source_review_status'], 'assumed')
        self.assertEqual(result['request_sha256'], curve_digest(raw))
        result['input_snapshot']['fan']['source']['reference'] = 'changed snapshot'
        self.assertEqual(raw, before)

    def test_linear_closed_form(self):
        raw = request()
        update_curve(raw, [(0, 100), (2, 0)])
        # 100 - 50Q = 100Q^2, positive quadratic root.
        expected = (-50 + math.sqrt(50**2 + 4 * 100 * 100)) / 200
        point = solve_fan_system_operating_point(raw)['operating_point']
        self.assertAlmostEqual(point['total_flow_m3_s'], expected, places=11)
        self.assertLessEqual(abs(point['pressure_residual_pa']), point['residual_tolerance_pa'])
        self.assertLessEqual(point['iterations'], 160)

    def test_piecewise_curve_selects_correct_segment(self):
        raw = request()
        update_curve(raw, [(0, 180), (.5, 160), (2, 10)])
        # Second segment P=210-100Q, so 100Q^2+100Q-210=0.
        expected = (-100 + math.sqrt(10000 + 84000)) / 200
        actual = solve_fan_system_operating_point(raw)['operating_point']['total_flow_m3_s']
        self.assertAlmostEqual(actual, expected, places=11)

    def test_series_and_parallel_count_and_loss(self):
        raw = request()
        update_curve(raw, [(0, 100), (2, 0)])
        raw['fan'].update(installed_count=2, active_count=2)
        series = solve_fan_system_operating_point(raw)['operating_point']['total_flow_m3_s']
        self.assertAlmostEqual(series, 1)
        raw['fan']['configuration'] = 'parallel'
        parallel = solve_fan_system_operating_point(raw)['operating_point']['total_flow_m3_s']
        self.assertAlmostEqual(parallel, (-25 + math.sqrt(625 + 40000)) / 200, places=11)
        raw['fan']['active_count'] = 1
        reduced = solve_fan_system_operating_point(raw)
        self.assertLess(reduced['operating_point']['total_flow_m3_s'], parallel)
        self.assertLess(reduced['operating_point']['total_flow_m3_s'], series)
        self.assertGreater(reduced['passages'][0]['outlet_temperature_k'], 300.3)

    def test_resistance_derived_branch_imbalance_and_no_cross_blade_warming(self):
        raw = request()
        second = copy.deepcopy(raw['system']['passages'][0])
        second.update(id='channel-B', resistance_pa_s2_m6=400)
        for load in second['heat_loads']:
            load['occurrence_id'] = 'Blade-2'
        raw['system']['passages'].append(second)
        result = solve_fan_system_operating_point(raw)
        a, b = result['passages']
        self.assertAlmostEqual(a['flow_m3_s'], 1)
        self.assertAlmostEqual(b['flow_m3_s'], .5)
        self.assertAlmostEqual(result['operating_point']['total_flow_m3_s'], 1.5)
        self.assertAlmostEqual(result['operating_point']['effective_parallel_resistance_pa_s2_m6'], 400 / 9)
        self.assertEqual(b['stages'][0]['inlet_temperature_k'], 300)
        self.assertAlmostEqual(b['outlet_temperature_k'], 300.6)
        self.assertAlmostEqual(result['air_summary']['mixed_outlet_temperature_k'], 300.4)
        self.assertAlmostEqual(result['air_summary']['energy_residual_w'], 0, places=8)

    def test_common_loss_adds_to_parallel_passage_loss(self):
        raw = request()
        raw['system']['common_resistance_pa_s2_m6'] = 300
        result = solve_fan_system_operating_point(raw)
        point = result['operating_point']
        self.assertAlmostEqual(point['total_flow_m3_s'], .5)
        self.assertAlmostEqual(point['passage_pressure_pa'], 25)
        self.assertAlmostEqual(point['common_pressure_pa'], 75)

    def test_all_fans_lost_with_heat_is_not_finite_temperature_success(self):
        raw = request()
        raw['fan']['active_count'] = 0
        result = solve_fan_system_operating_point(raw)
        self.assertEqual(result['status'], 'zero_flow_heat_failure')
        self.assertEqual(result['operating_point']['total_flow_m3_s'], 0)
        self.assertIsNone(result['air_summary']['mixed_outlet_temperature_k'])
        self.assertIsNone(result['passages'][0]['outlet_temperature_k'])
        self.assertFalse(result['limits']['passed'])
        for load in raw['system']['passages'][0]['heat_loads']:
            load['heat_w'] = 0
        self.assertEqual(solve_fan_system_operating_point(raw)['air_summary']['mixed_outlet_temperature_k'], 300)

    def test_zero_pressure_curve_endpoint_is_exact_zero_flow(self):
        raw = request()
        update_curve(raw, [(0, 0), (1, 0)])
        result = solve_fan_system_operating_point(raw)
        self.assertEqual(result['operating_point']['total_flow_m3_s'], 0)
        self.assertEqual(result['status'], 'zero_flow_heat_failure')

    def test_no_extrapolation_or_missing_curve_fallback(self):
        for points in ([(0, 100), (.2, 90)], [(2, 100), (3, 90)]):
            raw = request()
            update_curve(raw, points)
            self.assert_error(raw, 'intersection_not_covered')
        raw = request()
        update_curve(raw, [])
        self.assert_error(raw, 'curve_budget')

    def test_unknown_heat_and_duplicate_sites_rejected(self):
        for unknown in (None, 'unknown', True, float('nan'), float('inf'), -1):
            raw = request()
            raw['system']['passages'][0]['heat_loads'][0]['heat_w'] = unknown
            with self.assertRaises(FanSystemOperatingPointError):
                solve_fan_system_operating_point(raw)
        raw = request()
        raw['system']['passages'][0]['heat_loads'][1]['site_id'] = 'Q129'
        self.assert_error(raw, 'duplicate_heat_site')

    def test_declared_limits_are_checked_not_silently_clamped(self):
        raw = request()
        raw['air_limits'].update(min_total_flow_m3_s=1.1, max_outlet_temperature_k=300.2)
        raw['system']['passages'][0]['min_flow_m3_s'] = 1.1
        result = solve_fan_system_operating_point(raw)
        self.assertFalse(result['limits']['passed'])
        self.assertFalse(result['limits']['minimum_total_flow_passed'])
        self.assertFalse(result['limits']['maximum_outlet_temperature_passed'])
        self.assertFalse(result['passages'][0]['minimum_flow_passed'])
        self.assertAlmostEqual(result['operating_point']['total_flow_m3_s'], 1)

    def test_malformed_fields_order_counts_and_digests(self):
        cases = []
        for path, value, code in [
            (('contract',), 'future', 'contract'),
            (('fan', 'curve_sha256'), '0' * 64, 'curve_digest'),
            (('fan', 'source', 'sha256'), 'not-a-hash', 'source_digest'),
            (('fan', 'source', 'review_status'), 'verified', 'source_review'),
            (('fan', 'active_count'), True, 'fan_count'),
            (('fan', 'active_count'), 2, 'fan_count'),
            (('fan', 'installed_count'), 1025, 'fan_count'),
            (('air', 'density_kg_m3'), 0, 'numeric_range'),
            (('system', 'passages', 0, 'resistance_pa_s2_m6'), 0, 'numeric_range'),
        ]:
            raw = request()
            obj = raw
            for key in path[:-1]:
                obj = obj[key]
            obj[path[-1]] = value
            cases.append((raw, code))
        for raw, code in cases:
            self.assert_error(raw, code)
        for points in ([(0, 1), (0, 0)], [(0, 1), (1, 2)]):
            raw = request()
            update_curve(raw, points)
            self.assert_error(raw, 'curve_order')
        raw = request()
        raw['inferred_heat_w'] = 0
        self.assert_error(raw, 'invalid_fields')

    def test_resource_budgets(self):
        raw = request()
        raw['fan']['curve'] *= 2049
        self.assert_error(raw, 'curve_budget')
        raw = request()
        raw['system']['passages'] *= 129
        self.assert_error(raw, 'passage_budget')
        raw = request()
        raw['system']['passages'][0]['heat_loads'] *= 513
        self.assert_error(raw, 'heat_budget')

    def test_maximum_admitted_resource_sizes(self):
        raw = request()
        update_curve(raw, [(q, 100) for q in range(4096)])
        raw['fan'].update(configuration='parallel', installed_count=1024, active_count=1024)
        passage = raw['system']['passages'][0]
        raw['system']['passages'] = []
        for j in range(128):
            branch = copy.deepcopy(passage)
            branch.update(id=f'channel-{j}', resistance_pa_s2_m6=1e4)
            branch['heat_loads'] = [{'occurrence_id': f'board-{j}', 'site_id': f'site-{i}',
                                     'heat_w': 0, 'source': source()} for i in range(8)]
            raw['system']['passages'].append(branch)
        result = solve_fan_system_operating_point(raw)
        self.assertAlmostEqual(result['operating_point']['total_flow_m3_s'], 12.8, places=9)
        self.assertEqual(len(result['passages']), 128)

    def test_large_pressure_scale_bracket_retains_small_flow_root(self):
        raw = request()
        raw['system']['passages'][0].update(resistance_pa_s2_m6=1e24, heat_loads=[])
        update_curve(raw, [(0, 1e12), (1e6, 1e12)])
        result = solve_fan_system_operating_point(raw)
        self.assertAlmostEqual(result['operating_point']['total_flow_m3_s'], 1e-6, delta=1e-17)

    def test_upper_covered_endpoint_is_not_rejected_by_reduction_roundoff(self):
        raw = request()
        update_curve(raw, [(0, 100), (1, 100)])
        result = solve_fan_system_operating_point(raw)
        self.assertEqual(result['operating_point']['total_flow_m3_s'], 1)
        second = copy.deepcopy(raw['system']['passages'][0])
        second.update(id='other', heat_loads=[])
        raw['system']['passages'].append(second)
        update_curve(raw, [(0, 100), (2, 100)])
        result = solve_fan_system_operating_point(raw)
        self.assertEqual(result['operating_point']['total_flow_m3_s'], 2)

    def test_nonrepresentable_sensible_heat_is_rejected(self):
        raw = request()
        raw['air'].update(density_kg_m3=1e6, specific_heat_j_kg_k=1e9)
        self.assert_error(raw, 'energy_resolution')

    def test_reviewed_is_only_caller_declaration_not_vendor_authentication(self):
        raw = request()
        raw['fan']['source']['review_status'] = 'reviewed'
        raw['system']['source']['review_status'] = 'reviewed'
        for passage in raw['system']['passages']:
            passage['source']['review_status'] = 'reviewed'
            for load in passage['heat_loads']:
                load['source']['review_status'] = 'reviewed'
        result = solve_fan_system_operating_point(raw)
        self.assertEqual(result['source_review_status'], 'reviewed')
        self.assertEqual(result['source_digest_authentication'], 'caller_declared_not_authenticated')


if __name__ == '__main__':
    unittest.main()
