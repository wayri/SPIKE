# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Independent broad-phase regression checks on generated conforming cubes."""
import unittest
from python.spike_core.assembly_field_geometry import assert_disjoint_occurrences
from tests.python.test_assembly_tetra_thermal import cube


def pair(n, offset):
    left, right = cube(n), cube(n)
    count=len(left['vertices'])
    left['vertices'] += [[p[i]+offset[i] for i in range(3)] for p in right['vertices']]
    left['cells'] += [{**c,'vertices':[v+count for v in c['vertices']]} for c in right['cells']]
    owners=['left']*len(right['cells'])+['right']*len(right['cells'])
    return left, owners


class OccurrenceBroadPhaseTests(unittest.TestCase):
    def test_dense_separated_occurrences_do_not_spend_cell_budget(self):
        # 6,144 total tets; formerly dense same-owner x slabs exhausted 250k.
        for axis in range(3):
            offset=[0,0,0];offset[axis]=2
            mesh, owners=pair(8,offset)
            out=assert_disjoint_occurrences(mesh,owners,max_comparisons=0)
            self.assertEqual(out['inter_occurrence_comparisons'],0)

    def test_touching_is_allowed_and_positive_overlap_rejected(self):
        mesh,owners=pair(2,[1,0,0])
        self.assertEqual(assert_disjoint_occurrences(mesh,owners)['inter_occurrence_comparisons'],0)
        mesh,owners=pair(2,[.75,.25,.25])
        with self.assertRaisesRegex(ValueError,'ASSEMBLY_FIELD_OVERLAP'):
            assert_disjoint_occurrences(mesh,owners)
        with self.assertRaisesRegex(ValueError,'ASSEMBLY_FIELD_WORK'):
            assert_disjoint_occurrences(mesh,owners,max_comparisons=0)

    def test_interleaved_bounding_boxes_still_use_sat(self):
        # Congruent positively oriented tetrahedra whose boxes overlap but
        # whose separating x+y+z planes do not; same-owner duplicates ignored.
        vertices=[[0,0,0],[1,0,0],[0,1,0],[0,0,1],
                  [.8,.8,.8],[1.8,.8,.8],[.8,1.8,.8],[.8,.8,1.8]]
        mesh={'vertices':vertices,'cells':[{'vertices':[0,1,2,3]},{'vertices':[4,5,6,7]}]}
        self.assertEqual(assert_disjoint_occurrences(mesh,['a','b'])['inter_occurrence_comparisons'],1)
