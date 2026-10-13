# SPDX-License-Identifier: Apache-2.0
"""Original transient thermal fixtures and real optional CalculiX regressions."""
import copy
import math
import unittest

import numpy as np

from python.spike_core.calculix_runtime import probe_calculix_runtime
from python.spike_core.calculix_transient import (
    compile_calculix_transient_deck, parse_calculix_temperature_history, run_calculix_transient,
    run_calculix_field_transient, verify_calculix_field_transient_result,
    compare_thermal_transient_results, compare_transient_fields,
)
from python.spike_core.assembly_tetra_transient import run_assembly_tetra_transient
from python.spike_core.assembly_field_transient import run_assembly_field_transient
from python.spike_core.multiboard_identity import canonical_json_digest
from tests.python.test_assembly_tetra_thermal import cube, request, boundary, faces_at, contact_request
from tests.python.test_assembly_field_handoff import fixture


def settings(dt=.1, duration=1., initial=300., material='k'):
    return {'contract': 'spike/assembly-tetra-transient-settings/v1', 'duration_s': duration,
            'time_step_s': dt, 'output_interval_s': duration/4, 'initial_temperature_k': initial,
            'material_heat_capacity': [{'material_id': material, 'density_kg_m3': 2.,
                                        'specific_heat_j_kgk': 3.}]}


def sine_case(n, dt=.02):
    raw = request(cube(n))
    raw['boundaries'] = boundary(faces_at(raw['mesh'], 0), 'temperature', temperature_k=300.)
    raw['boundaries'] += boundary(faces_at(raw['mesh'], 1), 'temperature', temperature_k=300.)
    initial = [300. + 10*math.sin(math.pi*p[0]) for p in raw['mesh']['vertices']]
    return raw, settings(dt, .2, initial)


class CalculixTransientAdmissionTests(unittest.TestCase):
    def test_pwm_increment_card_respects_external_field_width(self):
        raw = request()
        raw['boundaries'] = []
        transient = settings(5e-5, 2e-4)
        compiled = compile_calculix_transient_deck(raw, transient)
        lines = compiled['deck'].splitlines()
        for i, line in enumerate(lines):
            if line.startswith('*HEAT TRANSFER'):
                values = lines[i+1].split(',')
                self.assertTrue(all(len(value) <= 20 for value in values))
                for value in values:
                    self.assertAlmostEqual(float(value)/5e-5, 1., places=10)

    def test_capacity_initial_source_and_event_deck(self):
        raw = request()
        raw['boundaries'] = []
        raw['heat_sources_w_m3'] = {c['id']: 12 for c in raw['mesh']['cells']}
        transient = settings(.3)
        transient['power_schedule'] = [{'time_s': 0., 'scale': 0.}, {'time_s': 1., 'scale': 1.}]
        before = copy.deepcopy((raw, transient))
        compiled = compile_calculix_transient_deck(raw, transient)
        self.assertEqual((raw, transient), before)
        self.assertIn('*DENSITY\n2\n*SPECIFIC HEAT\n3', compiled['deck'])
        self.assertNotIn('STEADY STATE', compiled['deck'])
        self.assertEqual(compiled['deck'].count('*STEP,'), len(compiled['time_grid'])-1)
        self.assertIn('1,BF,3', compiled['deck'])
        self.assertIn('1,BF,12', compiled['deck'])
        self.assertEqual(compiled['output_times'], [0., .25, .5, .75, 1.])

    def test_history_admission_requires_all_times_and_nodes(self):
        text = ' temperatures for set NALL and time .5\n1 300\n2 310\n'
        text += ' temperatures for set NALL and time 1\n1 301\n2 311\n'
        self.assertEqual(len(parse_calculix_temperature_history(text, 2, [.5, 1.])), 2)
        for changed in (text.replace('2 310\n', ''), text.replace('2 310', '1 310'),
                        text.replace('311', 'NaN'), text.replace('time 1', 'time .9'),
                        text + text, text.replace('2 311', '2 -1')):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                parse_calculix_temperature_history(changed, 2, [.5, 1.])

    def test_comparison_uses_rise_not_absolute_kelvin(self):
        left = {'frames': [{'time_s': 0, 'node_temperatures_k': [300]},
                           {'time_s': 1, 'node_temperatures_k': [301.2]}]}
        right = {'frames': [{'time_s': 0, 'node_temperatures_k': [300]},
                            {'time_s': 1, 'node_temperatures_k': [301]}]}
        comparison = compare_transient_fields(left, right, absolute_tolerance_k=.01, relative_tolerance=.01)
        self.assertFalse(comparison['passed'])
        right['frames'][1]['time_s'] = .9
        with self.assertRaisesRegex(ValueError, 'times'):
            compare_transient_fields(left, right, absolute_tolerance_k=.01, relative_tolerance=.01)

    def test_external_full_increment_history_is_bounded_before_deck_expansion(self):
        raw, transient = sine_case(4, .00002)
        transient['output_interval_s'] = .2
        with self.assertRaisesRegex(ValueError, 'CALCULIX_TRANSIENT_LIMIT'):
            compile_calculix_transient_deck(raw, transient)


@unittest.skipUnless(probe_calculix_runtime()['available'], 'Separately installed CalculiX unavailable')
class CalculixTransientExecutableTests(unittest.TestCase):
    def test_uniform_insulated_heat_and_nonuniform_event_grid(self):
        raw = request()
        raw['boundaries'] = []
        raw['heat_sources_w_m3'] = {c['id']: 12. for c in raw['mesh']['cells']}
        transient = settings(.3)
        result = run_calculix_transient(raw, transient)
        for frame in result['frames']:
            np.testing.assert_allclose(frame['node_temperatures_k'], 300+2*frame['time_s'], atol=6e-5)
        self.assertRegex(result['execution']['solver_version'], r'^\d+\.\d+(\.\d+)?$')
        transient['power_schedule'] = [{'time_s': 0., 'scale': 0.}, {'time_s': .4, 'scale': 1.},
                                       {'time_s': 1., 'scale': .2}]
        external = run_calculix_transient(raw, transient)
        internal = run_assembly_tetra_transient(raw, transient)
        self.assertTrue(compare_transient_fields(internal, external,
            absolute_tolerance_k=6e-5, relative_tolerance=0)['passed'])

    def test_one_point_capacity_explains_dc3d4_difference(self):
        # Independent original integration oracle: N_i=1/4 at the centroid.
        from python.spike_core.assembly_tetra_thermal_validation import validate_request
        raw, transient = sine_case(2, .2)
        transient['output_interval_s'] = .2
        data = validate_request(raw)
        n = len(data['xyz'])
        k, m = np.zeros((n,n)), np.zeros((n,n))
        for cell, (volume, gradients) in zip(data['cells'], data['geometry']):
            ix = np.ix_(cell['vertices'], cell['vertices'])
            k[ix] += volume*gradients @ data['tensors'][cell['material_id']] @ gradients.T
            m[ix] += 6*volume*np.ones((4,4))/16
        free = list(set(range(n))-set(data['fixed']))
        initial = np.asarray(transient['initial_temperature_k'])-300
        expected = np.linalg.solve((k+m/.2)[np.ix_(free,free)], (m@initial/.2)[free])+300
        external = run_calculix_transient(raw, transient)
        np.testing.assert_allclose(np.array(external['node_temperatures_k'])[free], expected, atol=6e-5, rtol=0)

    def test_convection_radiation_contact_and_saved_identity(self):
        raw = request(cube(2))
        raw['boundaries'] = boundary(faces_at(raw['mesh'], 0), 'temperature', temperature_k=300.)
        raw['boundaries'] += boundary(faces_at(raw['mesh'], 1), 'convection_radiation',
            heat_transfer_coefficient_w_m2k=10., ambient_temperature_k=300., emissivity=.7,
            radiation_temperature_k=300.)
        raw['heat_sources_w_m3'] = {c['id']: 12 for c in raw['mesh']['cells']}
        transient = settings()
        comparison = compare_transient_fields(run_assembly_tetra_transient(raw, transient),
            run_calculix_transient(raw, transient), absolute_tolerance_k=.05, relative_tolerance=.03)
        self.assertTrue(comparison['passed'], comparison)
        req, problem = fixture()
        transient = settings(initial=[300.]*8 + [400.]*8, material='slab')
        internal = run_assembly_field_transient(req, problem, transient)
        external = run_calculix_field_transient(req, problem, transient)
        self.assertEqual(verify_calculix_field_transient_result(req, problem, external), external)
        comparison = compare_thermal_transient_results(req, problem, internal, external,
            absolute_tolerance_k=1., relative_tolerance=.1)
        self.assertTrue(comparison['passed'], comparison)
        changed = copy.deepcopy(external)
        changed['field_result']['frames'][1]['time_s'] += .1
        changed['result_digest'] = canonical_json_digest({k:v for k,v in changed.items() if k!='result_digest'})
        with self.assertRaisesRegex(ValueError, 'times'):
            verify_calculix_field_transient_result(req, problem, changed)
        changed = copy.deepcopy(problem)
        changed['contacts'][0]['thermal_contact_conductance_w_m2k'] *= 2
        with self.assertRaisesRegex(ValueError, 'execution|STALE'):
            verify_calculix_field_transient_result(req, changed, external)
