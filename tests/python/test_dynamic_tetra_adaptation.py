# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import copy
import itertools
import math
import unittest

from python.spike_core.solvers.geometry_meshing.preparation.dynamic_tetra_adaptation import adapt_tetra_mesh, _dorfler_marks
from python.spike_core.solvers.geometry_meshing.preparation.tetra_mesh_refinement import TetraRefinementError, _det


def mesh_pair():
    mesh = {
        'contract': 'spike/solver-mesh/v1', 'units': 'm',
        'coordinate_system': 'right_handed_xyz',
        'vertices': [[0, 0, 0], [2, 0, 0], [.3, 1, 0], [.2, .2, 1], [.4, .3, -2]],
        'cells': [
            {'id': 'a', 'kind': 'tetrahedron', 'vertices': [0, 1, 2, 3],
             'material_id': 'copper', 'source_object_ids': ['board']},
            {'id': 'b', 'kind': 'tetrahedron', 'vertices': [0, 2, 1, 4],
             'material_id': 'air', 'source_object_ids': ['board']},
        ],
        'object_map': {'board': {'kind': 'board'}},
        'counts': {'vertices': 5, 'cells': 2},
    }
    faces = {}
    for cell in mesh['cells']:
        for face in itertools.combinations(cell['vertices'], 3):
            faces.setdefault(tuple(sorted(face)), []).append(cell['material_id'])
    boundary = [{'vertices': list(face), 'label': owners[0]}
                for face, owners in faces.items() if len(owners) == 1]
    return mesh, boundary


def interior_mesh():
    points = [[0, 0, 0], [2, 0, 0], [.3, 1, 0], [.2, .2, 1], [.12, .06, .03]]
    cells = []
    boundary = []
    for index, face in enumerate(itertools.combinations(range(4), 3)):
        vertices = list(face) + [4]
        if _det(points, vertices) < 0:
            vertices[0], vertices[1] = vertices[1], vertices[0]
        cells.append({'id': str(index), 'kind': 'tetrahedron', 'material_id': 'solid',
                      'vertices': vertices, 'source_object_ids': ['board']})
        boundary.append({'label': 'wall', 'vertices': list(face)})
    mesh = {'contract': 'spike/solver-mesh/v1', 'units': 'm',
            'coordinate_system': 'right_handed_xyz', 'vertices': points, 'cells': cells,
            'counts': {'vertices': 5, 'cells': 4},
            'object_map': {'board': {'kind': 'board'}}}
    return mesh, boundary


class DynamicTetraAdaptationTests(unittest.TestCase):
    def test_repeated_feedback_reduces_analytical_quadratic_interpolation_error(self):
        from python.spike_core.solvers.geometry_meshing.preparation.internal_tetra_generation import generate_tetra_mesh
        source = generate_tetra_mesh([list(p) for p in itertools.product((0., 1.), repeat=3)])
        mesh, boundary = source['mesh'], source['boundary_triangles']
        errors = []
        for level in range(5):
            indicators = {}
            for cell in mesh['cells']:
                vertices = cell['vertices']
                volume = _det(mesh['vertices'], vertices)/6
                edges = list(itertools.combinations(vertices, 2))
                squared_lengths = [math.dist(mesh['vertices'][a], mesh['vertices'][b])**2
                                   for a, b in edges]
                # For u=|x|^2, P1 interpolation error equals
                # sum_{i<j} lambda_i lambda_j |v_i-v_j|^2. Uniform tetra
                # barycentric moments give 1/210, 1/420 and 1/840 for
                # squared, shared-vertex and disjoint edge products.
                average = math.fsum(value*value/210 for value in squared_lengths)
                average += math.fsum(2*squared_lengths[i]*squared_lengths[j] /
                    (420 if set(edges[i]) & set(edges[j]) else 840)
                    for i, j in itertools.combinations(range(6), 2))
                indicators[cell['id']] = math.sqrt(volume*average)
            errors.append(math.sqrt(math.fsum(value*value for value in indicators.values())))
            if level < 4:
                result = adapt_tetra_mesh(mesh, boundary, cell_indicators=indicators,
                                          marking_fraction=1., optimize=False)
                mesh, boundary = result['mesh'], result['boundary_triangles']
        self.assertTrue(all(new < .7*old for old, new in zip(errors, errors[1:])), errors)
        self.assertLess(errors[-1], .17*errors[0])
        self.assertEqual(mesh['counts']['cells'], 96)

    def test_subnormal_constant_nodal_field_is_preserved(self):
        mesh, boundary = mesh_pair()
        tiny = math.ulp(0.)
        result = adapt_tetra_mesh(mesh, boundary, manual_edges=[[0, 1]], optimize=False,
                                  nodal_fields={'constant': [tiny]*5})
        self.assertEqual(result['nodal_fields']['constant'], [tiny]*6)

    def test_unrepresentable_cell_integral_is_rejected(self):
        mesh, boundary = mesh_pair()
        with self.assertRaisesRegex(TetraRefinementError, 'integral is not representable'):
            adapt_tetra_mesh(mesh, boundary, manual_edges=[[0, 1]], optimize=False,
                             cell_fields={'density': [4*math.ulp(0.), 0.]})

    def test_full_bulk_marking_retains_tiny_positive_indicators(self):
        marks, evidence = _dorfler_marks({'a': 1., 'b': 1e-200, 'c': 0.}, 1.)
        self.assertEqual(marks, ['a', 'b'])
        self.assertEqual(evidence['squared_weight_underflow_count'], 1)

    def test_roundoff_in_signed_material_integral_is_admitted(self):
        import random
        from python.spike_core.solvers.geometry_meshing.preparation.internal_tetra_generation import generate_tetra_mesh
        rng = random.Random(44)
        source = generate_tetra_mesh([[rng.random() for _ in range(3)] for _ in range(10)])
        mesh = source['mesh']
        values = [0.] * len(mesh['cells'])
        values[0] = 1.
        values[-1] = -_det(mesh['vertices'], mesh['cells'][0]['vertices']) / _det(
            mesh['vertices'], mesh['cells'][-1]['vertices'])
        result = adapt_tetra_mesh(mesh, source['boundary_triangles'], manual_edges=[[3, 4]],
                                  optimize=False, cell_fields={'signed': values})
        metrics = result['transfer_metrics']['cell']['signed']
        self.assertTrue(metrics['conserved'])
        self.assertLess(metrics['absolute_error'], 1e-16)

    def test_affine_nodal_transfer_is_exact_and_input_is_unchanged(self):
        mesh, boundary = mesh_pair()
        snapshot = copy.deepcopy((mesh, boundary))
        affine = lambda point: 2 * point[0] - 3 * point[1] + 4 * point[2] + 1
        values = [affine(point) for point in mesh['vertices']]
        result = adapt_tetra_mesh(mesh, boundary, cell_indicators={'a': 2, 'b': 0},
                                  optimize=False, nodal_fields={'potential': values})
        self.assertEqual((mesh, boundary), snapshot)
        self.assertEqual(result['adaptation_evidence']['selected_edges'], [[1, 3]])
        for point, value in zip(result['mesh']['vertices'], result['nodal_fields']['potential']):
            self.assertAlmostEqual(value, affine(point), places=14)
        self.assertEqual(result['transfer_metrics']['nodal']['potential']['method'],
                         'original_P1_midpoint_interpolation')
        self.assertFalse(result['adaptation_evidence']['convergence_assessed'])

    def test_piecewise_constant_cell_transfer_conserves_each_material_integral(self):
        mesh, boundary = mesh_pair()
        result = adapt_tetra_mesh(mesh, boundary, manual_edges=[[0, 1]], optimize=False,
                                  cell_fields={'energy_density': [2.5, -3.0]})
        output = result['mesh']
        totals = {}
        for cell, value in zip(output['cells'], result['cell_fields']['energy_density']):
            volume = _det(output['vertices'], cell['vertices']) / 6
            totals[cell['material_id']] = totals.get(cell['material_id'], 0) + volume * value
        original = {}
        for cell, value in zip(mesh['cells'], [2.5, -3.0]):
            volume = _det(mesh['vertices'], cell['vertices']) / 6
            original[cell['material_id']] = original.get(cell['material_id'], 0) + volume * value
        self.assertEqual(set(totals), set(original))
        for material in totals:
            self.assertAlmostEqual(totals[material], original[material], places=14)
        metric = result['transfer_metrics']['cell']['energy_density']
        self.assertTrue(metric['conserved'])
        self.assertTrue(all(item['conserved'] for item in metric['by_material'].values()))

    def test_deterministic_bulk_manual_union_and_boundary_interface_ownership(self):
        mesh, boundary = mesh_pair()
        result = adapt_tetra_mesh(mesh, boundary, cell_indicators={'a': 1, 'b': 1},
                                  marking_fraction=.5, manual_edges=[[0, 3]], optimize=False)
        # Equal indicators break ties by cell ID, so only cell a is bulk-marked.
        self.assertEqual(result['adaptation_evidence']['indicator_marking']['marked_cell_ids'], ['a'])
        self.assertEqual(result['adaptation_evidence']['selected_edges'], [[0, 3], [1, 3]])
        self.assertEqual({face['label'] for face in result['boundary_triangles']}, {'air', 'copper'})
        self.assertEqual({cell['material_id'] for cell in result['mesh']['cells']}, {'air', 'copper'})
        self.assertEqual(result['mesh']['object_map'], mesh['object_map'])
        self.assertEqual(set(result['parent_cell_ids'].values()), {'a', 'b'})

    def test_one_pass_reports_unmet_size_criterion(self):
        mesh, boundary = mesh_pair()
        result = adapt_tetra_mesh(mesh, boundary, target_edge_length=1.0, optimize=False)
        sizing = result['adaptation_evidence']['sizing']
        self.assertTrue(sizing['initial_violations'])
        self.assertTrue(sizing['remaining_violations'])
        self.assertFalse(sizing['criterion_met'])
        self.assertTrue(result['adaptation_evidence']['convergence_assessed'])
        self.assertFalse(result['adaptation_evidence']['converged'])

    def test_protected_interior_vertex_and_noop(self):
        mesh, boundary = interior_mesh()
        result = adapt_tetra_mesh(mesh, boundary, protected_vertices=[4])
        self.assertEqual(result['mesh'], mesh)
        self.assertEqual(result['refinement_log'], [])
        self.assertEqual(result['optimization_log']['moves'], [])
        self.assertIn(4, result['optimization_log']['fixed_vertices'])
        self.assertFalse(result['production_qualified'])

    def test_optimization_without_fields_moves_only_admitted_interior_vertices(self):
        mesh, boundary = interior_mesh()
        result = adapt_tetra_mesh(mesh, boundary)
        self.assertTrue(result['optimization_log']['moves'])
        self.assertEqual(result['mesh']['vertices'][:4], mesh['vertices'][:4])
        self.assertNotEqual(result['mesh']['vertices'][4], mesh['vertices'][4])
        self.assertGreater(result['quality']['after']['minimum_mean_ratio'],
                           result['quality']['before']['minimum_mean_ratio'])

    def test_rejects_field_relocation_malformed_controls_and_budgets(self):
        mesh, boundary = mesh_pair()
        cases = [
            {'nodal_fields': {'x': [0] * 5}},
            {'cell_fields': {'x': [1, 2]}},
            {'cell_indicators': {'a': 1}},
            {'cell_indicators': [1, 1]},
            {'cell_indicators': {'a': 1, 'b': -1}, 'optimize': False},
            {'marking_fraction': True},
            {'marking_fraction': 0},
            {'target_edge_length': math.nan},
            {'manual_edges': [[3, 4]]},
            {'protected_vertices': [5]},
            {'protected_vertices': [True]},
            {'optimize': 1},
            {'iterations': True},
            {'max_cells': True},
            {'max_vertices': 3},
        ]
        # The first two are valid field shapes but must fail because optimization defaults true.
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(TetraRefinementError):
                adapt_tetra_mesh(mesh, boundary, **kwargs)
        with self.assertRaisesRegex(TetraRefinementError, 'resource budget'):
            adapt_tetra_mesh(mesh, boundary, manual_edges=[[0, 1]], optimize=False,
                             max_cells=2)
        with self.assertRaisesRegex(TetraRefinementError, 'unsupported'):
            adapt_tetra_mesh(mesh, boundary, nodal_fields={'x': [0, 1, 2, 3, 4]})
        deduplicated = adapt_tetra_mesh(mesh, boundary,
                                        manual_edges=[[0, 1], [1, 0]], optimize=False)
        self.assertEqual(deduplicated['adaptation_evidence']['selected_edges'], [[0, 1]])

    def test_noop_copies_empty_fields_and_reports_no_false_convergence(self):
        mesh, boundary = mesh_pair()
        result = adapt_tetra_mesh(mesh, boundary, optimize=False)
        self.assertEqual(result['mesh'], mesh)
        self.assertEqual(result['boundary_triangles'], boundary)
        self.assertEqual(result['nodal_fields'], {})
        self.assertEqual(result['cell_fields'], {})
        self.assertFalse(result['adaptation_evidence']['convergence_assessed'])
        self.assertFalse(result['adaptation_evidence']['converged'])


if __name__ == '__main__':
    unittest.main()
