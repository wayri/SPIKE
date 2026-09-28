# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import unittest
from scripts.run_crossboard_openems import fixture
from python.spike_core.openems_assembly_geometry import compile_assembly_geometry
from python.spike_core.crossboard_mesh import plan_crossboard_mesh


class ControlledMeshTests(unittest.TestCase):
    def plan(self, level):
        return plan_crossboard_mesh(compile_assembly_geometry(fixture(4.)),
            [([-15,-1,-1],[-15,1,0]),([15,-1,-1],[15,1,0]),
             ([-15,-1,4],[-15,1,5]),([15,-1,4],[15,1,5])], level=level)

    def test_nested_transverse_refinement_and_fixed_boundary(self):
        plans = [self.plan(i) for i in range(3)]
        for a, b in zip(plans, plans[1:]):
            self.assertEqual(a['inner_pml_bounds_mm'], b['inner_pml_bounds_mm'])
            for x, y in zip(a['lines_mm'], b['lines_mm']):
                self.assertTrue(all(any(abs(v-w)<1e-12 for w in y) for v in x))
                self.assertEqual(x[:9], y[:9]);self.assertEqual(x[-9:], y[-9:])
        for level, plan in enumerate(plans):
            for axis, lo, hi, base in ((1,-1,1,2),(2,-1,0,2),(2,0,.1,1)):
                cells = sum(lo <= v < hi for v in plan['lines_mm'][axis])
                self.assertEqual(cells, base*2**level)

    def test_controls_fail_closed(self):
        for value in (-1, 3, True, .5):
            with self.assertRaises(ValueError):self.plan(value)


if __name__ == '__main__':unittest.main()
