# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Retained STEP placement preserves analytic OCC entities and admission."""
import math
import unittest
from unittest.mock import Mock

import numpy as np

from python.spike_core.assembly_thermal_cad import import_step_solid


class RetainedStepPlacementTests(unittest.TestCase):
    def setup_case(self):
        occ, model = Mock(), Mock()
        occ.importShapes.return_value = [(3, 7), (2, 101), (2, 102), (2, 103)]
        occ.getMass.return_value = math.pi/2.
        model.getBoundary.return_value = [(2, 101), (2, 102), (2, 103)]
        occ.affineTransform.side_effect = AssertionError("General affine transform must not be used")
        shape = {"path": "fixture.step", "transform": np.eye(4).ravel().tolist()}
        return occ, model, shape

    def test_identity_does_not_transform_analytic_shape(self):
        occ, model, shape = self.setup_case()
        self.assertEqual(import_step_solid(occ, shape, model), 7)
        occ.affineTransform.assert_not_called()
        occ.rotate.assert_not_called()
        occ.translate.assert_not_called()

    def test_translation_uses_native_rigid_operation(self):
        occ, model, shape = self.setup_case()
        matrix = np.eye(4)
        matrix[:3, 3] = [.3, -.2, .1]
        shape["transform"] = matrix.ravel().tolist()
        import_step_solid(occ, shape, model)
        occ.rotate.assert_not_called()
        occ.translate.assert_called_once_with([(3, 7)], .3, -.2, .1)
        occ.affineTransform.assert_not_called()

    def test_rotation_and_translation_are_applied_in_source_frame_order(self):
        occ, model, shape = self.setup_case()
        matrix = np.eye(4)
        c, s = math.cos(.7), math.sin(.7)
        matrix[:3, :3] = [[c, -s, 0.], [s, c, 0.], [0., 0., 1.]]
        matrix[:3, 3] = [.3, -.2, .1]
        shape["transform"] = matrix.ravel().tolist()
        import_step_solid(occ, shape, model)
        arguments = occ.rotate.call_args.args
        self.assertEqual(arguments[0], [(3, 7)])
        np.testing.assert_allclose(arguments[1:], [0., 0., 0., 0., 0., 1., .7], atol=1e-14)
        calls = [call[0] for call in occ.method_calls]
        self.assertLess(calls.index("rotate"), calls.index("translate"))
        occ.affineTransform.assert_not_called()

    def test_deferred_placement_and_rejection_are_unchanged(self):
        occ, model, shape = self.setup_case()
        import_step_solid(occ, shape, model, apply_transform=False)
        occ.rotate.assert_not_called()
        occ.translate.assert_not_called()
        for entities, surfaces, mass in (
                ([(2, 101)], [(2, 101)], 1.),
                ([(3, 7), (3, 8)], [], 1.),
                ([(3, 7), (2, 999)], [(2, 101)], 1.),
                ([(3, 7)], [], 0.)):
            occ, model, shape = self.setup_case()
            occ.importShapes.return_value = entities
            model.getBoundary.return_value = surfaces
            occ.getMass.return_value = mass
            with self.assertRaises(ValueError):
                import_step_solid(occ, shape, model)
            occ.rotate.assert_not_called()
            occ.translate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
