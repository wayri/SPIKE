# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original SI fixtures and independent analytical/reference invariants."""
import copy
import json
import math
from pathlib import Path
import unittest

import numpy as np
from jsonschema import Draft202012Validator

from python.spike_core.solvers.thermal_fluid.heat.assembly_view_factors import AssemblyViewFactorError, derive_assembly_view_factors


def square(z, side=1., upwards=True):
    points = [[0., 0., z], [side, 0., z], [side, side, z], [0., side, z]]
    triangles = [[points[i] for i in indexes] for indexes in ((0, 1, 2), (0, 2, 3))]
    return triangles if upwards else [list(reversed(t)) for t in triangles]


def request(level=3):
    return {'contract': 'spike/assembly-view-factor-request/v1', 'units': 'm',
            'surfaces': [{'id': 'lower', 'triangles': square(0.)},
                         {'id': 'upper', 'triangles': square(1., upwards=False)}],
            'quadrature': {'level': level, 'max_pair_evaluations': 10_000_000,
                           'max_visibility_tests': 50_000_000, 'max_geometry_pairs': 32768}}


def square_exact():
    # By difference coordinates, the unit-square double-area integral is
    # 4/pi integral_0^1 integral_0^1 (1-x)(1-y)/(1+x*x+y*y)^2 dx dy.
    # Evaluating its antiderivative gives the expression below. This oracle
    # does not reuse the triangle quadrature. Howell catalog C-11 identifies
    # the reference geometry: https://www.thermalradiation.net/sectionc/C-11.html
    return (math.log(4/3)+4*math.sqrt(2)*math.atan(1/math.sqrt(2))-math.pi)/math.pi


class AssemblyViewFactorTests(unittest.TestCase):
    def test_request_schema_golden_and_malformed(self):
        path = Path(__file__).resolve().parents[2]/'schemas/assembly-view-factor-request-v1.schema.json'
        schema = json.loads(path.read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        golden = request(5)
        validator.validate(golden)
        golden['occluders'] = square(.5)
        validator.validate(golden)
        malformed = []
        for field, value in (('units', 'mm'), ('contract', 'wrong'), ('extra', 1),
                             ('surfaces', []), ('occluders', [True])):
            case = request()
            case[field] = value
            malformed.append(case)
        for key, value in (('level', True), ('level', 6), ('max_pair_evaluations', 0),
                           ('max_visibility_tests', 50_000_001), ('max_geometry_pairs', 32769)):
            case = request()
            case['quadrature'][key] = value
            malformed.append(case)
        for value in (True, '0', float('inf'), 1e13):
            case = request()
            case['surfaces'][0]['triangles'][0][0][0] = value
            malformed.append(case)
        for value in ('', '   ', 'x'*129):
            case = request()
            case['surfaces'][0]['id'] = value
            malformed.append(case)
        for index, case in enumerate(malformed):
            with self.subTest(index=index):
                self.assertTrue(list(validator.iter_errors(case)))
                with self.assertRaises(AssemblyViewFactorError):
                    derive_assembly_view_factors(case)

    def test_parallel_square_six_refinement_levels(self):
        result = derive_assembly_view_factors(request(5))
        exact = square_exact()
        self.assertAlmostEqual(exact, .199824895698387, places=14)
        values = [row['view_factors'][0][1] for row in result['quadrature_history']]
        errors = [abs(value-exact) for value in values]
        self.assertEqual(len(values), 6)
        for previous, current in zip(errors, errors[1:]):
            self.assertLess(current, previous/3)
        self.assertLess(errors[-1], 8e-5)
        self.assertIsNone(result['quadrature_history'][0]['max_absolute_change'])
        self.assertIsNone(result['error_bound'])
        self.assertEqual(result['status'], 'experimental')
        self.assertFalse(result['production_qualified'])

    def test_independent_input_mesh_refinement(self):
        coarse = request(1)
        fine = request(0)
        for surface in fine['surfaces']:
            triangles = []
            for triangle in surface['triangles']:
                a, b, c = np.asarray(triangle)
                ab, bc, ca = (a+b)/2, (b+c)/2, (c+a)/2
                triangles.extend(np.asarray(t).tolist() for t in
                                 ((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)))
            surface['triangles'] = triangles
        np.testing.assert_allclose(derive_assembly_view_factors(coarse)['view_factors'],
                                   derive_assembly_view_factors(fine)['view_factors'], atol=1e-14)

    def test_rotation_translation_and_scale(self):
        baseline = derive_assembly_view_factors(request(2))
        angle = .723
        rotation = np.array([[math.cos(angle), 0, math.sin(angle)], [0, 1, 0],
                             [-math.sin(angle), 0, math.cos(angle)]])
        for scale in (.001, 1., 1000.):
            case = request(2)
            for surface in case['surfaces']:
                surface['triangles'] = (scale*np.asarray(surface['triangles'])@rotation.T
                                        +np.array([2., -3., .8])*scale).tolist()
            output = derive_assembly_view_factors(case)
            np.testing.assert_allclose(output['view_factors'], baseline['view_factors'], atol=1e-14)
            np.testing.assert_allclose(output['areas_m2'], np.array(baseline['areas_m2'])*scale**2)
            self.assertNotEqual(output['input_digest_sha256'], baseline['input_digest_sha256'])

    def test_unequal_area_reciprocity(self):
        case = request(3)
        case['surfaces'][1]['triangles'] = square(1., side=.5, upwards=False)
        result = derive_assembly_view_factors(case)
        areas, factors = result['areas_m2'], result['view_factors']
        self.assertAlmostEqual(areas[0]*factors[0][1], areas[1]*factors[1][0], places=15)
        self.assertEqual(result['exchange_areas_m2'][0][1], result['exchange_areas_m2'][1][0])

    def test_backfacing_and_opaque_central_plate(self):
        case = request(2)
        case['surfaces'][1]['triangles'] = square(1.)
        self.assertEqual(derive_assembly_view_factors(case)['view_factors'], [[0., 0.], [0., 0.]])
        case = request(2)
        case['occluders'] = square(.5)
        result = derive_assembly_view_factors(case)
        self.assertEqual(result['view_factors'], [[0., 0.], [0., 0.]])
        self.assertEqual(result['unresolved_view_fractions'], [1., 1.])
        self.assertEqual(result['unresolved_status'], 'UNRESOLVED')
        self.assertFalse(result['ambient_view_factors_inferred'])

    def test_third_emitting_surface_is_also_opaque(self):
        case = request(2)
        case['surfaces'].append({'id': 'blocker', 'triangles': square(.5)})
        result = derive_assembly_view_factors(case)
        self.assertEqual(result['view_factors'][0][1], 0.)
        self.assertGreater(result['view_factors'][1][2], 0.)

    def test_partial_shadow_is_reciprocal_and_rotation_invariant(self):
        case = request(3)
        bare = derive_assembly_view_factors(case)['view_factors'][0][1]
        case['occluders'] = (np.asarray(square(.5, side=.4))+[.3, .3, 0.]).tolist()
        result = derive_assembly_view_factors(case)
        value = result['view_factors'][0][1]
        self.assertGreater(value, 0.)
        self.assertLess(value, bare)
        self.assertEqual(value, result['view_factors'][1][0])
        # Exact axis rotation avoids a grazing-edge perturbation changing the
        # visibility classification: shadow-boundary convergence is separate.
        for surface in case['surfaces']:
            surface['triangles'] = np.asarray(surface['triangles'])[..., [2, 0, 1]].tolist()
        case['occluders'] = np.asarray(case['occluders'])[..., [2, 0, 1]].tolist()
        rotated = derive_assembly_view_factors(case)
        np.testing.assert_allclose(rotated['view_factors'], result['view_factors'], atol=1e-14)
        self.assertFalse(rotated['ambient_view_factors_inferred'])

    def test_malformed_numbers_geometry_and_contract(self):
        for value in (True, float('nan'), float('inf'), '0', 10**1000):
            case = request()
            case['surfaces'][0]['triangles'][0][0][0] = value
            with self.subTest(value=type(value).__name__), self.assertRaises(AssemblyViewFactorError):
                derive_assembly_view_factors(case)
        for kind in ('degenerate', 'duplicate', 'opposite', 'nonplanar', 'contact', 'intersect', 'near'):
            case = request(0)
            triangles = case['surfaces'][1]['triangles']
            if kind == 'degenerate':
                triangles[0][1] = triangles[0][0]
            elif kind == 'duplicate':
                triangles.append(copy.deepcopy(triangles[0]))
            elif kind == 'opposite':
                triangles[0].reverse()
            elif kind == 'nonplanar':
                triangles[0][0][2] += .1
            elif kind == 'contact':
                case['surfaces'][1]['triangles'] = square(0., upwards=False)
            elif kind == 'near':
                case['surfaces'][1]['triangles'] = square(.01, upwards=False)
            else:
                case['surfaces'][1]['triangles'] = [[[.2, .2, -.5], [.8, .2, .5], [.2, .8, .5]]]
            with self.subTest(kind=kind), self.assertRaises(AssemblyViewFactorError):
                derive_assembly_view_factors(case)
        for field, value in (('units', 'mm'), ('contract', 'other')):
            case = request()
            case[field] = value
            with self.assertRaises(AssemblyViewFactorError):
                derive_assembly_view_factors(case)

    def test_resource_limits(self):
        for key, value in (('level', True), ('level', 6), ('max_pair_evaluations', 1),
                           ('max_geometry_pairs', 1), ('max_visibility_tests', 1)):
            case = request()
            case['occluders'] = square(.5)
            case['quadrature'][key] = value
            with self.subTest(key=key), self.assertRaises(AssemblyViewFactorError):
                derive_assembly_view_factors(case)

    def test_over_one_rows_fail_without_renormalization(self):
        # Coarse centroid quadrature overestimates a close parallel pair enough
        # to exceed unity. Its diameter/clearance ratio is admitted, but the
        # physical row bound still must fail rather than silently renormalize.
        case = request(0)
        case['surfaces'][1]['triangles'] = square(.36, upwards=False)
        with self.assertRaisesRegex(AssemblyViewFactorError, 'row exceeds one'):
            derive_assembly_view_factors(case)


if __name__ == '__main__':
    unittest.main()
