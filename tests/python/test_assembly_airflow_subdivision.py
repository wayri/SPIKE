# SPDX-License-Identifier: Apache-2.0
"""Independent affine-volume, surface, interface and resource oracles."""
import copy
import threading
import unittest
from collections import Counter
from fractions import Fraction as F
from unittest.mock import MagicMock

import numpy as np
from scipy.spatial import ConvexHull

from python.spike_core.solvers.thermal_fluid.flow.assembly_airflow_subdivision import subdivide_airflow_mesh


def tetra(points=None):
    return {'vertices': points or [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
            'cells': [{'id': 'p', 'kind': 'tetrahedron', 'vertices': [0, 1, 2, 3],
                       'material_id': 'solid_0', 'source_object_ids': ['component']} ]}


LIMITS = {'max_cells': 100, 'max_vertices': 100}


class AirflowSubdivisionTests(unittest.TestCase):
    def test_affine_hex_volumes_and_centres_against_independent_hull(self):
        # Rational oracle det(A)/6=2 for this sheared tetra; each child is 1/2.
        matrix = np.array([[2, 1, 0], [0, 3, 1], [0, 0, 2]], dtype=float)
        points = (np.asarray(tetra()['vertices']) @ matrix.T + [13, -5, 7]).tolist()
        source = tetra(points); before = copy.deepcopy(source)
        result = subdivide_airflow_mesh(source, LIMITS)
        expected = float(F(2*3*2, 6*4))
        self.assertEqual(len(result['cells']), 4)
        self.assertEqual(len(result['vertices']), 15)
        self.assertEqual(result['vertices'][:4], points)
        for child in result['cells']:
            vertices = np.asarray([result['vertices'][i] for i in child['vertices']])
            self.assertAlmostEqual(ConvexHull(vertices).volume, expected, delta=1e-13)
            self.assertEqual(child['material_id'], 'solid_0')
            self.assertEqual(child['source_object_ids'], ['component'])
            # Independent barycentric inclusion: child i has largest lambda_i.
            bary = np.linalg.solve(matrix, (vertices-[13,-5,7]).T).T
            bary = np.column_stack((1-bary.sum(axis=1), bary))
            local = int(child['id'].rsplit('_', 1)[1])
            self.assertTrue(np.all(bary >= -1e-14))
            self.assertTrue(np.all(bary[:,local,None] >= bary-1e-14))
        self.assertEqual(source, before)

    def test_shared_region_surface_uses_identical_three_quads(self):
        source = tetra(); source['vertices'].append([0, 0, -1])
        source['cells'].append({'id': 'q', 'kind': 'tetrahedron', 'vertices': [0,2,1,4],
                                'material_id': 'air', 'source_object_ids': ['air']})
        result = subdivide_airflow_mesh(source, LIMITS)
        # Recover interface quads geometrically, independent of converter face templates.
        per_region = {'air': [], 'solid_0': []}
        for cell in result['cells']:
            plane_nodes = [v for v in cell['vertices'] if result['vertices'][v][2] == 0]
            if len(plane_nodes) == 4:
                per_region[cell['material_id']].append(tuple(sorted(plane_nodes)))
                coords = np.array([result['vertices'][v][:2] for v in plane_nodes])
                self.assertAlmostEqual(ConvexHull(coords).volume, 1/6, delta=1e-15)
        self.assertEqual(len(per_region['air']), 3)
        self.assertEqual(Counter(per_region['air']), Counter(per_region['solid_0']))
        self.assertEqual(len(result['vertices']), len(set(map(tuple,result['vertices']))))

    def test_final_budget_is_enforced_without_source_mutation(self):
        source = tetra(); before = copy.deepcopy(source)
        for limits in ({'max_cells': 3, 'max_vertices':100}, {'max_cells':4, 'max_vertices':14}):
            with self.subTest(limits=limits), self.assertRaisesRegex(ValueError,'AIRFLOW_RESOURCE'):
                subdivide_airflow_mesh(source, limits)
        self.assertEqual(source,before)
        self.assertEqual(len(subdivide_airflow_mesh(source, {'max_cells':4,'max_vertices':15})['cells']),4)

    def test_cancellation_prevents_subdivision_result(self):
        event=threading.Event(); event.set()
        with self.assertRaisesRegex(InterruptedError,'AIRFLOW_CANCELLED'):
            subdivide_airflow_mesh(tetra(), LIMITS, cancellation_event=event)

    def test_optimizer_cannot_move_or_rewire_source_surface(self):
        from python.spike_core.solvers.thermal_fluid.flow.assembly_airflow_mesh import build_air_mesh
        from tests.python.test_assembly_airflow import request
        for mutate in ('coordinate', 'connectivity'):
            with self.subTest(mutate=mutate):
                gmsh=MagicMock()
                gmsh.model.occ.addBox.side_effect=[1,2]
                gmsh.model.occ.getMass.return_value=1.0
                gmsh.model.occ.fragment.return_value=([(3,1),(3,2)], [[(3,1),(3,2)],[(3,2)]])
                gmsh.model.getEntities.return_value=[(2,1)]
                xyz=[0,0,0,1,0,0,0,1,0]
                changed=list(xyz)
                if mutate=='coordinate': changed[0]=.001
                gmsh.model.mesh.getNodes.side_effect=[([1,2,3],xyz,[]),([1,2,3],changed,[])]
                changed_face=[1,3,2] if mutate=='connectivity' else [1,2,3]
                gmsh.model.mesh.getElements.side_effect=[([2],[[1]],[[1,2,3]]),([2],[[1]],[changed_face])]
                with self.assertRaisesRegex(ValueError,'changed the source surface'):
                    build_air_mesh(gmsh,request()['geometry'])


if __name__ == '__main__':
    unittest.main()
