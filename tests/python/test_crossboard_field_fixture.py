# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import unittest
from scripts.run_crossboard_openems import fixture
from python.spike_core.openems_assembly_geometry import compile_assembly_geometry


class CrossboardFieldFixtureTests(unittest.TestCase):
    def test_facing_strips_have_separate_references_and_vacuum(self):
        for gap in (1.,4.,20.):
            result=compile_assembly_geometry(fixture(gap))
            boxes={(b['board_id'],b['id']):b for b in result['boxes']}
            self.assertEqual(len(boxes),6)
            self.assertEqual(boxes['A','substrate']['stop_mm'][2],0.)
            self.assertEqual(boxes['B','substrate']['start_mm'][2],gap)
            self.assertLess(boxes['A','signal']['stop_mm'][2],gap/2)
            self.assertGreater(boxes['B','signal']['start_mm'][2],gap/2)
            self.assertEqual(boxes['A','return']['stop_mm'][2],-1.)
            self.assertEqual(boxes['B','return']['start_mm'][2],gap+1)
            self.assertFalse(result['production_qualified'])

    def test_material_interfaces_are_mandatory_grid_constraints(self):
        result=compile_assembly_geometry(fixture(4.))
        for box in result['boxes']:
            for axis in range(3):
                self.assertIn(box['start_mm'][axis],result['mandatory_mesh_lines_mm'][axis])
                self.assertIn(box['stop_mm'][axis],result['mandatory_mesh_lines_mm'][axis])


if __name__=='__main__':unittest.main()
