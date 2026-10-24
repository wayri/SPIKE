# SPDX-License-Identifier: Apache-2.0
"""STEP scale, orientation, placement and source immutability checks."""
import hashlib
import importlib.util
from pathlib import Path
import unittest
import numpy as np
from extensions.optycal_suite.step_geometry import mesh_step, rigid_matrix

ROOT = Path(__file__).resolve().parents[2]
class OptycalStepTests(unittest.TestCase):
    def test_active_rotation_and_translation(self):
        matrix = rigid_matrix([1, 2, 3], [0, 0, 90])
        np.testing.assert_allclose(matrix @ [1, 0, 0, 1], [1, 3, 3, 1], atol=1e-12)
        with self.assertRaises(ValueError):
            rigid_matrix([float('nan'), 0, 0], [0, 0, 0])

    @unittest.skipUnless(importlib.util.find_spec('gmsh'), 'separately installed Gmsh required')
    def test_actual_step_units_closed_volume_and_rigid_placement(self):
        path = ROOT/'examples/optycal/reflector.step'
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        mesh = mesh_step(path, mesh_size_mm=50, translation_mm=[0, 0, 1000], rotation_deg=[0, 0, 90], expected_sha256=digest)
        self.assertAlmostEqual(mesh['cad_volume_mm3'], 500*500*5, places=4)
        self.assertAlmostEqual(mesh['surface_volume_mm3']/mesh['cad_volume_mm3'], 1, places=10)
        np.testing.assert_allclose(mesh['bounds_mm'], [-250, -250, 1000, 250, 250, 1005], atol=1e-7)
        with self.assertRaisesRegex(ValueError, 'changed'):
            mesh_step(path, mesh_size_mm=50, expected_sha256='0'*64)
