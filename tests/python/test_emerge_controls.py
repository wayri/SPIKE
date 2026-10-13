# SPDX-License-Identifier: Apache-2.0
"""Bounded GUI controls and truthful sampled complex-field transport."""

import copy
import types
import unittest

from extensions.emerge_suite.board_adapter import compile_board
from extensions.emerge_suite.capture import nearfield_plane
from extensions.emerge_suite.normalize import nearfield
from tests.python.test_emerge_suite_extension import board, parameters


class EMergeControlsTests(unittest.TestCase):
    def test_conductor_and_roughness_loss_requests_fail_closed(self):
        unsupported = (
            {"include_conductor_loss": True},
            {"enable_skin_effect": True},
            {"include_proximity_loss": True},
            {"loss_model": {"conductor": "slab_skin"}},
            {"conductor_loss_model": "surface_impedance"},
            {"include_internal_reactance": True},
            {"copper_conductivity_s_per_m": 5.8e7},
            {"surface_impedance_ohm": .01},
            {"copper_thickness_um": 35},
            {"conductivity_s_m": 5.8e7},
            {"thickness_m": 35e-6},
            {"roughness_model": "rms"},
            {"surface_roughness_model": "rms"},
            {"surface_roughness_um": 1.5},
            {"rms_roughness_um": 1.5},
        )
        for request in unsupported:
            with self.subTest(request=request):
                with self.assertRaisesRegex(ValueError, "zero-thickness PEC copper"):
                    compile_board(board(), dict(parameters(), **request))

        case = compile_board(board(), dict(parameters(), include_conductor_loss=False,
                                            conductor_loss_model="pec",
                                            roughness_model="smooth"))
        self.assertIn("surface_pec", case["geometry_status"])

    def test_controls_preserve_material_loss_and_port_impedance(self):
        params = dict(parameters(), include_dielectric_loss=True, reference_impedance_ohm=75,
                      air_margin_mm=40, parallel=True, n_workers=3, sparse_solver="superlu")
        case = compile_board(board(), params)
        self.assertEqual(case["loss_tangent_omitted"], 0)
        self.assertEqual(case["dielectric_layers"][0]["loss_tangent"], 0.02)
        self.assertTrue(all(port["reference_impedance_ohm"] == 75 for port in case["ports"]))
        self.assertEqual(case["n_workers"], 3)

    def test_controls_reject_unsafe_sizes_and_values(self):
        for key, value in (("include_dielectric_loss", 1), ("parallel", "yes"),
                           ("n_workers", 9), ("nearfield_grid_points", 100),
                           ("radiation_theta_step_deg", 7), ("air_margin_mm", 0),
                           ("reference_impedance_ohm", float("nan")), ("sparse_solver", "unknown"),
                           ("field_excited_port", 3)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                compile_board(board(), dict(parameters(), **{key: value}))
        with self.assertRaisesRegex(ValueError, "inside"):
            compile_board(board(), dict(parameters(), nearfield_enabled=True, air_margin_mm=5, nearfield_z_mm=6))
        with self.assertRaisesRegex(ValueError, "100000"):
            compile_board(board(), dict(parameters(), frequency_points=64,
                                       radiation_theta_step_deg=5, radiation_phi_step_deg=5))
        with self.assertRaisesRegex(ValueError, "100000"):
            compile_board(board(), dict(parameters(), frequency_points=64,
                                       nearfield_enabled=True, nearfield_grid_points=41))

    def test_complex_field_capture_keeps_units_and_domain_gaps(self):
        import numpy as np

        observed = {}
        class Field:
            def interpolate(self, x, y, z, usenan):
                observed.update(x=x, y=y, z=z, usenan=usenan)
                v = np.full(len(x), 3+4j)
                v[-1] = complex(float("nan"), 0)
                return types.SimpleNamespace(**{axis: v.copy() for axis in ("Ex", "Ey", "Ez", "Hx", "Hy", "Hz")})

        plane = nearfield_plane(Field(), 1e9, [0, 0, 2, 4], 1, 3)
        self.assertEqual(observed["x"][-1], 0.002)
        self.assertEqual(observed["z"][0], 0.001)
        self.assertEqual(plane["e_v_m"][0], [[3, 4]] * 3)
        self.assertFalse(plane["valid"][-1])
        self.assertIsNone(plane["h_a_m"][-1])
        data, summary = nearfield({"frequencies_hz": [1e9], "planes": [plane]})
        self.assertEqual(summary["valid_sample_count"], 8)
        self.assertEqual(data["contract"], "spike/emerge-nearfield-plane/v1")
        raw = {"frequencies_hz": [1e9], "planes": [plane], "excitation_ports": ["P1", "P2"],
               "excitation_port": "P2", "excitation_coefficients": [[0, 0], [1, 0]]}
        self.assertEqual(nearfield(raw)[0]["excitation_port"], "P2")
        raw["excitation_coefficients"] = [[1, 0], [1, 0]]
        with self.assertRaisesRegex(ValueError, "one unit"):
            nearfield(raw)
        malformed = copy.deepcopy(plane)
        malformed["e_v_m"][-1] = [[0, 0]] * 3
        with self.assertRaisesRegex(ValueError, "null"):
            nearfield({"frequencies_hz": [1e9], "planes": [malformed]})


if __name__ == "__main__":
    unittest.main()
