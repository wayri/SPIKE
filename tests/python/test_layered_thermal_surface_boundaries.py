# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Independent resistance and transient checks for prescribed cell boundaries."""

import copy
import unittest

import numpy as np
from scipy.linalg import expm

from python.spike_core.board_thermal import run_board_thermal
from python.spike_core.contracts import SpiDeR


def design():
    return SpiDeR(design_id="surface-boundary-oracle", units="mm",
        components=[{"reference": "U1", "at": [5, 5]}],
        stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.1},
                 {"name": "core", "type": "dielectric", "thickness": 0.8},
                 {"name": "B.Cu", "type": "copper", "thickness": 0.1}],
        metadata={"board_bounds_mm": [0, 0, 10, 10]})


def request():
    return {"ambient_temperature_c": 25,
        "board": {"model": "layered", "thickness_mm": 1, "grid_step_mm": 10,
            "x_edges_mm": [0, 3, 10], "y_edges_mm": [0, 10],
            "convection_top_w_m2k": 0, "convection_bottom_w_m2k": 10,
            "dielectric_conductivity_w_mk": 1, "copper_conductivity_w_mk": 100,
            "include_copper": False, "include_vias": False},
        "components": [{"component_ref": "U1", "power_w": 0,
            "r_junction_case_k_w": 2, "r_case_board_k_w": 3,
            "contact_mode": "square", "contact_size_mm": 10}]}


def prescribed_request():
    req = request()
    req["board"].update(convection_top_grid_w_m2k=[20, 40],
        convection_bottom_grid_w_m2k=[10, 30], ambient_top_grid_c=[10, 20],
        ambient_bottom_grid_c=[30, 50])
    return req


def oracle():
    """Six-node network derived from SI face areas and center spacings."""
    area = np.array([30e-6, 70e-6])
    matrix = np.zeros((6, 6))
    def link(a, b, g):
        matrix[a, a] += g
        matrix[b, b] += g
        matrix[a, b] -= g
        matrix[b, a] -= g
    for layer, thickness in enumerate([0.0001, 0.0008, 0.0001]):
        link(2 * layer, 2 * layer + 1, thickness * 0.01 / 0.005)
    for a in range(4):
        link(a, a + 2, area[a % 2] / 0.00045)
    sink = np.array([area[0] / (0.00005 + 1 / 20), area[1] / (0.00005 + 1 / 40),
                     0, 0, area[0] / (0.00005 + 1 / 10), area[1] / (0.00005 + 1 / 30)])
    bath = np.array([10, 20, 25, 25, 30, 50])
    matrix += np.diag(sink)
    capacity = np.outer([0.0001, 0.0008, 0.0001], area).ravel() * 1e6
    return matrix, sink * bath, sink, bath, capacity


class LayeredThermalSurfaceBoundaryTests(unittest.TestCase):
    def solved(self, req):
        result = run_board_thermal(design(), req)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["model_status"], "approximate")
        self.assertLess(abs(result["summary"]["energy_balance_error_w"]), 1e-10)
        return result

    def test_scalar_defaults_equal_constant_grid_overrides(self):
        req = request()
        req["components"][0]["power_w"] = 0.1
        baseline = self.solved(req)
        req["board"].update(convection_top_grid_w_m2k=[0, 0], convection_bottom_grid_w_m2k=[10, 10],
                             ambient_top_grid_c=[25, 25], ambient_bottom_grid_c=[25, 25])
        actual = self.solved(req)
        for a, b in zip(actual["layer_grids"], baseline["layer_grids"]):
            np.testing.assert_allclose(a["temperatures_c"], b["temperatures_c"], atol=1e-12, rtol=0)

    def test_different_local_air_and_h_match_independent_network(self):
        result = self.solved(prescribed_request())
        matrix, rhs, sink, bath, _ = oracle()
        temperatures = np.concatenate([row["temperatures_c"] for row in result["layer_grids"]])
        np.testing.assert_allclose(temperatures, np.linalg.solve(matrix, rhs), atol=1e-10, rtol=0)
        self.assertLess(abs(float(np.dot(sink, temperatures - bath))), 1e-10)
        self.assertFalse(result["provenance"]["board_convection_inferred"])
        self.assertEqual(len(result["provenance"]["prescribed_surface_boundary_grids"]), 4)
        self.assertIn("THERMAL_PRESCRIBED_SURFACE_BOUNDARY", [issue["code"] for issue in result["issues"]])

    def test_local_air_only_override_and_single_positive_sink(self):
        req = request()
        req["board"].update(ambient_bottom_grid_c=[40, 40])
        result = self.solved(req)
        np.testing.assert_allclose(result["grid"]["temperatures_c"], 40, atol=1e-10, rtol=0)
        req["board"].update(convection_top_w_m2k=0, convection_bottom_w_m2k=0,
                            convection_bottom_grid_w_m2k=[0, 10])
        result = self.solved(req)
        np.testing.assert_allclose(result["grid"]["temperatures_c"], 40, atol=1e-10, rtol=0)
        # Positive scalar defaults cannot conceal an override with no sink.
        req["board"].update(convection_bottom_w_m2k=10, convection_bottom_grid_w_m2k=[0, 0])
        self.assertEqual(run_board_thermal(design(), req)["status"], "blocked")

    def test_transient_local_baths_refine_to_independent_exponential(self):
        matrix, rhs, _, _, capacity = oracle()
        steady = np.linalg.solve(matrix, rhs)
        exact = steady + expm(-matrix / capacity[:, None] * 2) @ (np.full(6, 25) - steady)
        errors = []
        for dt, stride in ((0.1, 2), (0.05, 4)):
            req = prescribed_request()
            req["transient"] = {"end_time_s": 2, "time_step_s": dt, "output_stride": stride,
                "copper_volumetric_heat_capacity_j_m3k": 1e6,
                "dielectric_volumetric_heat_capacity_j_m3k": 1e6}
            result = self.solved(req)
            final = np.concatenate(result["transient"][-1]["layer_temperatures_c"])
            errors.append(float(np.max(np.abs(final - exact))))
            np.testing.assert_equal(result["transient"][0]["layer_temperatures_c"], [[25, 25]] * 3)
            self.assertLess(result["summary"]["max_transient_energy_balance_error_w"], 1e-10)
            self.assertAlmostEqual(result["summary"]["transient_final_stored_energy_j"],
                                   float(np.dot(capacity, final - 25)), places=10)
        self.assertGreater(errors[0] / errors[1], 1.8)

    def test_invalid_boundary_shapes_and_values_fail_closed(self):
        for key in ("convection_top_grid_w_m2k", "convection_bottom_grid_w_m2k",
                    "ambient_top_grid_c", "ambient_bottom_grid_c"):
            invalid = [[], [1], [1, 2, 3], [[1, 2]], [True, 1], ["1", 2], [float("nan"), 1],
                       [float("inf"), 1], None, [(-1 if key.startswith("convection") else -274), 1]]
            for value in invalid:
                with self.subTest(key=key, value=value):
                    req = copy.deepcopy(request())
                    req["board"][key] = value
                    self.assertEqual(run_board_thermal(design(), req)["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
