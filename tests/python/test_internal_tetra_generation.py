# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Independent synthetic hull/volume and external black-box Delaunay oracles."""
import copy
from fractions import Fraction
import itertools
import json
import math
import random
import unittest
from unittest.mock import patch

from python.spike_core.solvers.geometry_meshing.preparation.internal_tetra_generation import generate_tetra_mesh, TetraGenerationError, _Predicates


def determinant(matrix):
    """Independent permutation expansion, used only for small exact oracles."""
    result = 0
    for permutation in itertools.permutations(range(len(matrix))):
        inversions = sum(permutation[i] > permutation[j] for i in range(len(matrix))
                         for j in range(i+1, len(matrix)))
        product = (-1)**inversions
        for row, column in enumerate(permutation):
            product *= matrix[row][column]
        result += product
    return result


def oriented_volume(points, cell):
    rows = [[Fraction(x) for x in points[i]]+[1] for i in cell]
    return -determinant(rows)/6


def cube(levels=(0., 1.)):
    return [list(point) for point in itertools.product(levels, repeat=3)]


class InternalTetraGenerationTests(unittest.TestCase):
    def check_geometry(self, result, expected_volume):
        mesh = result['mesh']
        points = mesh['vertices']
        faces = {}
        volume = Fraction(0)
        used = set()
        for cell in mesh['cells']:
            indices = cell['vertices']
            used.update(indices)
            contribution = oriented_volume(points, indices)
            self.assertGreater(contribution, 0)
            volume += contribution
            for face in itertools.combinations(indices, 3):
                faces.setdefault(tuple(sorted(face)), []).append(indices)
        self.assertEqual(used, set(range(len(points))))
        self.assertTrue(all(len(owners) in (1, 2) for owners in faces.values()))
        exterior = {face for face, owners in faces.items() if len(owners) == 1}
        self.assertEqual(exterior, {tuple(sorted(f['vertices'])) for f in result['boundary_triangles']})
        self.assertAlmostEqual(float(volume), expected_volume, delta=max(abs(expected_volume)*1e-12, 1e-300))
        self.assertAlmostEqual(result['quality']['volume'], float(volume), delta=float(volume)*1e-12)
        # Divergence-theorem hull volume, with independently evaluated outward
        # faces. Every cloud point must lie on/in each supporting plane.
        hull_volume = Fraction(0)
        for item in result['boundary_triangles']:
            face = item['vertices']
            matrix = [[Fraction(x) for x in points[i]] for i in face]
            hull_volume += determinant(matrix)/6
            for point in range(len(points)):
                self.assertLessEqual(oriented_volume(points, face+[point]), 0)
        self.assertEqual(volume, hull_volume)
        self.assertFalse(result['production_qualified'])
        self.assertFalse(result['evidence']['production_qualified'])
        self.assertFalse(result['evidence']['coordinate_perturbation'])

    def test_tetrahedron_contract_and_units(self):
        points = [[0,0,0], [2,0,0], [0,3,0], [0,0,4]]
        result = generate_tetra_mesh(points, units='mm', material_id='copper',
                                     source_object_id='part', boundary_label='wall')
        self.check_geometry(result, 4.)
        self.assertEqual(result['mesh']['counts'], {'vertices': 4, 'cells': 1})
        self.assertEqual(result['quality']['volume_units'], 'mm^3')
        self.assertEqual(result['mesh']['object_map'], {'part': {'kind': 'convex_point_cloud'}})
        self.assertTrue(all(c['material_id'] == 'copper' and c['source_object_ids'] == ['part']
                            for c in result['mesh']['cells']))
        self.assertEqual({f['label'] for f in result['boundary_triangles']}, {'wall'})
        from pathlib import Path
        from jsonschema import Draft202012Validator
        schema = json.loads((Path(__file__).resolve().parents[2]/'schemas'/'solver-mesh-v1.schema.json').read_text())
        Draft202012Validator(schema).validate(json.loads(json.dumps(result['mesh'], allow_nan=False)))

    def test_cube_cospherical_and_lattice(self):
        for levels, count in (((0, 1), 6), ((0, .5, 1), 48)):
            with self.subTest(levels=levels):
                result = generate_tetra_mesh(cube(levels))
                self.check_geometry(result, 1.)
                self.assertEqual(len(result['mesh']['cells']), count)
                self.assertGreater(result['evidence']['symbolic_sphere_ties'], 0)

    def test_octahedron_cospherical(self):
        points = [[s if axis == k else 0 for k in range(3)] for axis in range(3) for s in (-1,1)]
        self.check_geometry(generate_tetra_mesh(points), 4/3)

    def test_points_on_edges_faces_and_interior(self):
        points = cube()+[[.5,0,0], [.5,.5,0], [.5,.5,.5], [0,.5,.5], [1,1,.5]]
        result = generate_tetra_mesh(points)
        self.check_geometry(result, 1.)
        self.assertEqual(result['mesh']['vertices'], points)
        # Every boundary coplanar input remains part of the hull triangulation.
        boundary_vertices = {i for f in result['boundary_triangles'] for i in f['vertices']}
        self.assertTrue({8,9,11,12} <= boundary_vertices)
        self.assertNotIn(10, boundary_vertices)

    def test_reproducible_nonmutating_and_permutation_independent_geometry(self):
        points = cube()+[[.25,.375,.5], [.625,.5,.125]]
        original = copy.deepcopy(points)
        result = generate_tetra_mesh(points)
        self.assertEqual(points, original)
        self.assertEqual(result, generate_tetra_mesh(points))
        permuted = list(reversed(points))
        other = generate_tetra_mesh(permuted)
        def cell_coordinates(mesh):
            return {tuple(sorted(tuple(mesh['vertices'][i]) for i in c['vertices'])) for c in mesh['cells']}
        self.assertEqual(cell_coordinates(result['mesh']), cell_coordinates(other['mesh']))

    def test_scale_and_translation(self):
        for scale, translation in ((2**-20, 0), (2**20, 0), (1, 2**24), (.125, -32)):
            with self.subTest(scale=scale, translation=translation):
                points = [[x*scale+translation for x in p] for p in cube()+[[.25,.5,.75]]]
                self.check_geometry(generate_tetra_mesh(points), scale**3)

    def test_filtered_predicates_against_exact_independent_expansion(self):
        rng = random.Random(813)
        cases = [[[rng.uniform(-1,1) for _ in range(3)] for _ in range(5)] for _ in range(20)]
        cases += [[[0,0,0], [1,0,0], [0,1,0], [0,0,1], [1,1,z]]
                  for z in (1, math.nextafter(1, 0), math.nextafter(1, 2))]
        for points in cases:
            predicate = _Predicates(points, dict(enumerate(range(5))))
            cell = [0,1,2,3]
            exact_orientation = -determinant([[Fraction(x) for x in points[i]]+[1] for i in cell])
            expected = (exact_orientation > 0)-(exact_orientation < 0)
            self.assertEqual(predicate.orientation(cell), expected)
            if expected < 0:
                cell[0], cell[1] = cell[1], cell[0]
            lifted = []
            for i in cell+[4]:
                p = list(map(Fraction, points[i]))
                lifted.append(p+[sum(x*x for x in p), 1])
            exact_sphere = determinant(lifted)
            self.assertEqual(predicate.sphere(cell, 4, symbolic=False),
                             (exact_sphere < 0)-(exact_sphere > 0))

    def test_random_cloud_independent_scipy_black_box(self):
        try:
            from scipy.spatial import Delaunay, ConvexHull
        except ImportError:
            self.skipTest('Optional independently installed SciPy oracle unavailable.')
        for seed in (7201, 89, 515):
            rng = random.Random(seed)
            points = [[rng.random() for _ in range(3)] for _ in range(40)]
            result = generate_tetra_mesh(points)
            self.check_geometry(result, float(ConvexHull(points).volume))
            self.assertEqual({tuple(sorted(c['vertices'])) for c in result['mesh']['cells']},
                             {tuple(sorted(map(int, c))) for c in Delaunay(points).simplices})

    def test_reject_malformed_and_degenerate(self):
        tetra = [[0,0,0], [1,0,0], [0,1,0], [0,0,1]]
        cases = [None, (), tetra[:3], [[0,0]]*4, tetra+[tetra[0]],
                 [[x,y,0] for x,y in itertools.product((0,1), repeat=2)],
                 [[i,0,0] for i in range(4)], cube()*17]
        for value in (True, float('inf'), float('nan'), '1', 10**1000, 2**54+1):
            points = copy.deepcopy(tetra)
            points[1][0] = value
            cases.append(points)
        for points in cases:
            with self.subTest(points=str(points)[:100]), self.assertRaises(TetraGenerationError):
                generate_tetra_mesh(points)
        for kwargs in ({'max_cells': True}, {'max_cells': 0}, {'max_cells': 5001}, {'units':'cm'},
                       {'material_id': ''}, {'source_object_id': False}, {'boundary_label': 'x'*129}):
            with self.subTest(kwargs=kwargs), self.assertRaises(TetraGenerationError):
                generate_tetra_mesh(tetra, **kwargs)

    def test_unrepresentable_geometry_fails_without_partial_result(self):
        for scale in (1e-110, 1e110):
            with self.subTest(scale=scale), self.assertRaises(TetraGenerationError):
                generate_tetra_mesh([[x*scale for x in p] for p in cube()])
        points = [[0,0,0], [1e300,0,0], [0,1e-300,0], [0,0,1]]
        with self.assertRaisesRegex(TetraGenerationError, 'dynamic range'):
            generate_tetra_mesh(points)

    def test_finite_enclosure_conditioning_limit_fails_closed(self):
        rng = random.Random(7201)
        points = [[rng.random(), rng.random(), rng.random()*1e-8] for _ in range(20)]
        # Finite super-tetrahedron vertices can prevent real hull cells from
        # appearing on nearly flat generic input. This is not accepted as a
        # partial domain or silently converted to a surface mesh.
        with self.assertRaisesRegex(TetraGenerationError, 'omitted points|supporting convex hull'):
            generate_tetra_mesh(points)

    def test_cell_and_predicate_budgets(self):
        with self.assertRaisesRegex(TetraGenerationError, 'cell resource budget'):
            generate_tetra_mesh(cube(), max_cells=5)
        for constant in ('MAX_PREDICATES', 'MAX_EXACT_PREDICATES'):
            with patch('python.spike_core.solvers.geometry_meshing.preparation.internal_tetra_generation.'+constant, 1):
                with self.assertRaisesRegex(TetraGenerationError, 'budget'):
                    generate_tetra_mesh(cube())

    def test_point_limit_is_inclusive(self):
        rng = random.Random(7201)
        points = [[rng.random() for _ in range(3)] for _ in range(128)]
        result = generate_tetra_mesh(points)
        self.assertEqual(result['mesh']['counts']['vertices'], 128)
        self.assertLessEqual(result['evidence']['predicate_calls'], result['evidence']['predicate_limit'])
        with self.assertRaisesRegex(TetraGenerationError, 'Point budget'):
            generate_tetra_mesh(points+[[2,2,2]])


if __name__ == '__main__':
    unittest.main()
