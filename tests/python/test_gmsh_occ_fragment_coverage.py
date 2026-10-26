# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""An unmeshed positive CAD fragment must never count as retained geometry.

The injected API is an original test double: two disjoint triangular prisms,
each with volume 1/2 mm^3. Every represented prism has an exact three-tetrahedron
partition. No native runtime, external implementation, or example output is used.
"""
import importlib.util
import itertools
import unittest
from unittest.mock import Mock, patch

from python.spike_core.solvers.geometry_meshing.preparation.gmsh_occ_mesher import OccMeshingError, build_occ_mesh


def _request():
    solids = []
    for source, x in (('kept', 0), ('lost', 2)):
        solids.append({'id': source, 'material_id': 'fr4', 'priority': 0,
                       'shape': {'kind': 'polygon_prism',
                                 'outer_mm': [[x,0], [x+1,0], [x,1]], 'holes_mm': [],
                                 'z_min_mm': 0, 'z_max_mm': 1}})
    return {'contract': 'spike/gmsh-occ-mesh/v2', 'solids': solids,
            'object_metadata': {name: {'kind': 'board_layer'} for name in ('kept', 'lost')},
            'mesh': {'min_size_mm': .2, 'max_size_mm': 1., 'max_cells': 100, 'max_vertices': 100},
            'focus': {'contract': 'spike/pcb-focus-sizing/v1', 'net_names': [],
                      'source_ids': ['kept'], 'fine_size_mm': .2, 'coarse_size_mm': 1.,
                      'halo_mm': .1, 'growth_rate': .5, 'regions': []}}


def _api(missing_second, empty_type_record=False):
    gmsh = Mock()
    gmsh.model.occ.fragment.return_value = ([(3,1), (3,2)], [[(3,1)], [(3,2)]])
    gmsh.model.occ.getMass.return_value = .5
    prism = [[0,0,0], [1,0,0], [0,1,0], [0,0,1], [1,0,1], [0,1,1]]
    local_cells = [[0,1,2,3], [1,4,2,3], [2,4,5,3]]
    points, elements, boundary = [], {}, []
    for fragment in (1, 2):
        if missing_second and fragment == 2:
            elements[fragment] = ([4], [[]], [[]]) if empty_type_record else ([], [], [])
            continue
        offset = len(points)
        points.extend([[x+2*(fragment-1), y, z] for x, y, z in prism])
        cells = [[index+offset+1 for index in cell] for cell in local_cells]
        elements[fragment] = ([4], [[100*fragment+i for i in range(3)]],
                              [[index for cell in cells for index in cell]])
        faces = {}
        for cell in cells:
            for face in itertools.combinations(cell, 3):
                key = tuple(sorted(face))
                faces[key] = faces.get(key, 0)+1
        boundary.extend(list(face) for face, owners in sorted(faces.items()) if owners == 1)
    gmsh.model.mesh.getNodes.return_value = (list(range(1, len(points)+1)),
                                            [value for point in points for value in point], [])
    # Include the absent fragment's CAD surfaces, but deliberately return no
    # surface elements for them. Orphan-triangle checks alone cannot detect it.
    gmsh.model.getEntities.return_value = [(2, tag) for tag in range(1, 17)]

    def get_elements(dimension, tag):
        if dimension == 3:
            return elements[tag]
        if tag <= len(boundary):
            return [2], [[tag]], [boundary[tag-1]]
        return [], [], []

    gmsh.model.mesh.getElements.side_effect = get_elements
    return gmsh


@unittest.skipUnless(importlib.util.find_spec('shapely'), 'Optional Shapely runtime unavailable')
class OccFragmentCoverageTests(unittest.TestCase):
    def test_complete_fixture_has_mesh_cells_for_both_cad_fragments(self):
        with patch('python.spike_core.solvers.geometry_meshing.preparation.gmsh_occ_mesher._solid', side_effect=[1, 2]):
            result = build_occ_mesh(_api(missing_second=False), _request())
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(result['whole_model_retained'])
        self.assertEqual(result['mesh']['counts'], {'vertices': 12, 'cells': 6})
        self.assertEqual(result['metrics']['fragment_mesh_volumes_mm3'], {'1': .5, '2': .5})
        self.assertEqual({source for cell in result['mesh']['cells'] for source in cell['source_object_ids']},
                         {'kept', 'lost'})

    def test_positive_cad_fragment_without_tetrahedra_is_rejected(self):
        for empty_type_record in (False, True):
            with self.subTest(empty_type_record=empty_type_record):
                with patch('python.spike_core.solvers.geometry_meshing.preparation.gmsh_occ_mesher._solid', side_effect=[1, 2]):
                    with self.assertRaisesRegex(OccMeshingError, '(?i)fragment|coverage|source'):
                        build_occ_mesh(_api(missing_second=True, empty_type_record=empty_type_record),
                                       _request())


if __name__ == '__main__':
    unittest.main()
