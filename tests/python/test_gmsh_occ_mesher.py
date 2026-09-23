# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
import copy
import importlib.util
import unittest
from unittest.mock import patch

from python.spike_core.gmsh_occ_mesher import OccMeshingError, build_occ_mesh, validate_request


def request():
    return {'contract': 'spike/gmsh-occ-mesh/v1', 'solids': [
        {'id': 'board', 'material_id': 'fr4', 'priority': 0,
         'shape': {'kind': 'polygon_prism', 'outer_mm': [[0,0],[4,0],[4,3],[0,3]],
                   'holes_mm': [[[1,1],[2,1],[2,2],[1,2]]], 'z_min_mm': 0, 'z_max_mm': 1}}],
        'mesh': {'min_size_mm': 0.1, 'max_size_mm': 1, 'max_cells': 10000, 'max_vertices': 10000}}


class TestOccMissingDependency(unittest.TestCase):
    def test_missing_optional_dependency_is_explicit_and_fail_closed(self):
        with patch.dict("sys.modules", {"shapely": None, "shapely.geometry": None}):
            with self.assertRaisesRegex(OccMeshingError, "GMSH_DEPENDENCY"):
                validate_request(request())


@unittest.skipUnless(importlib.util.find_spec("shapely"), "Optional OCC runtime requires Shapely; run with its qualified Python environment")
class TestOccInput(unittest.TestCase):
    def test_valid_polygon_hole_and_tube(self):
        value = request()
        validate_request(value)
        value['solids'].append({'id': 'via', 'material_id': 'copper', 'priority': 1,
                                'shape': {'kind': 'tube', 'center_mm': [3,1], 'outer_radius_mm': .3,
                                          'inner_radius_mm': .2, 'z_min_mm': 0, 'z_max_mm': 1}})
        validate_request(value)

    def test_invalid_contracts(self):
        mutations = [lambda r: r.update(extra=True),
                     lambda r: r.update(contract='other'),
                     lambda r: r['mesh'].update(max_cells=True),
                     lambda r: r['mesh'].update(min_size_mm=float('nan')),
                     lambda r: r['mesh'].update(max_size_mm=10**1000),
                     lambda r: r['solids'][0].update(priority=1.5),
                     lambda r: r['solids'].append(copy.deepcopy(r['solids'][0])),
                     lambda r: r['solids'][0]['shape'].update(z_max_mm=0),
                     lambda r: r['solids'][0]['shape'].update(outer_mm=[[0,0],[4,3],[4,0],[0,3]]),
                     lambda r: r['solids'][0]['shape'].update(holes_mm=[[[10,10],[11,10],[11,11]]]),
                     lambda r: r['solids'][0]['shape'].update(outer_mm=[[0,0],[4,0],[0,0]]),
                     lambda r: r['solids'][0]['shape'].update(kind='step_file')]
        for mutation in mutations:
            value = request()
            mutation(value)
            with self.subTest(value=str(value)[:150]), self.assertRaises(OccMeshingError):
                validate_request(value)

    def test_invalid_before_native_allocation(self):
        value = request()
        value['solids'][0]['shape']['z_max_mm'] = -1
        with self.assertRaises(OccMeshingError):
            build_occ_mesh(None, value)


if __name__ == '__main__':
    unittest.main()
