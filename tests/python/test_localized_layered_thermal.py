# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original rectilinear-grid resistance, conservation and refinement oracles."""

import copy
import math
import unittest
from unittest.mock import patch

import numpy as np
from scipy.sparse.linalg import spsolve
from scipy.sparse import csr_matrix

from python.spike_core.board_thermal import _pad_contacts, run_board_thermal
from python.spike_core.contracts import SpiDeR
from python.spike_core.thermal_grid import rectangle_weights, transfer_coverage


def design():
    return SpiDeR(design_id="local-grid-oracle", units="mm",
        components=[{"reference": "U1", "at": [5, 5]}],
        stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.1},
                 {"name": "core", "type": "dielectric", "thickness": 0.8},
                 {"name": "B.Cu", "type": "copper", "thickness": 0.1}],
        metadata={"board_bounds_mm": [0, 0, 10, 10]})


def request():
    return {"ambient_temperature_c": 25,
        "board": {"model": "layered", "thickness_mm": 1, "grid_step_mm": 2,
            "convection_top_w_m2k": 0, "convection_bottom_w_m2k": 10,
            "dielectric_conductivity_w_mk": 1, "copper_conductivity_w_mk": 100,
            "via_plating_thickness_mm": 0.02, "include_copper": False, "include_vias": False},
        "components": [{"component_ref": "U1", "power_w": 0.1,
            "r_junction_case_k_w": 2, "r_case_board_k_w": 3,
            "contact_mode": "square", "contact_size_mm": 10}]}


def explicit(req, x=(0, 1, 3, 5, 10), y=(0, 2, 3, 8, 10)):
    req["board"].update(x_edges_mm=list(x), y_edges_mm=list(y))
    return req


class LocalizedLayeredThermalTests(unittest.TestCase):
    def test_cross_axis_transfer_bounds_dense_intermediates(self):
        original = csr_matrix.__matmul__

        def bounded_multiply(matrix, operand):
            if isinstance(operand, np.ndarray) and operand.ndim == 2:
                self.assertLessEqual(matrix.shape[0] * operand.shape[1], 8192)
            return original(matrix, operand)

        long = np.linspace(0, 8192, 8193)
        short = np.linspace(0, .01, 8193)
        with patch.object(csr_matrix, '__matmul__', bounded_multiply):
            a = transfer_coverage({'F.Cu': np.ones((1, 8192))}, long, [0, .01], [0, 8192], short)['F.Cu']
            b = transfer_coverage({'F.Cu': np.ones((8192, 1))}, [0, .01], long, short, [0, 8192])['F.Cu']
        np.testing.assert_allclose(a, np.ones((8192, 1)), atol=1e-14)
        np.testing.assert_allclose(b, np.ones((1, 8192)), atol=1e-14)

    def solved(self, req, board=None):
        result = run_board_thermal(board or design(), req)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["model_status"], "approximate")
        self.assertLess(abs(result["summary"]["energy_balance_error_w"]), 1e-9)
        return result

    def test_uniform_flux_exact_series_resistance_on_arbitrary_cells(self):
        result = self.solved(explicit(request()))
        # q''=1000 W/m2; total top-center to air resistance per unit area
        # = 0.0009/1 + 0.00005/1 + 1/10 m2 K/W, hence rise 100.95 K.
        for layer, expected in zip(result["layer_grids"], (125.95, 125.5, 125.05)):
            np.testing.assert_allclose(layer["temperatures_c"], expected, atol=2e-10, rtol=0)
        self.assertNotIn("spacing_mm", result["grid"])
        self.assertEqual(result["grid"]["kind"], "rectilinear")
        self.assertEqual(result["grid"]["x_edges_mm"], [0, 1, 3, 5, 10])

    def test_constant_ambient_zero_source_and_transient_capacity(self):
        req = explicit(request())
        req["components"][0]["power_w"] = 0
        result = self.solved(req)
        np.testing.assert_allclose(result["grid"]["temperatures_c"], 25, atol=1e-10, rtol=0)
        req["components"][0]["power_w"] = 0.1
        req["transient"] = {"end_time_s": 2, "time_step_s": 0.1, "output_stride": 4,
            "copper_volumetric_heat_capacity_j_m3k": 1e6,
            "dielectric_volumetric_heat_capacity_j_m3k": 1e6}
        nonuniform = self.solved(req)
        uniform_req = copy.deepcopy(req)
        for key in ("x_edges_mm", "y_edges_mm"):
            uniform_req["board"].pop(key)
        uniform_req["board"]["grid_step_mm"] = 10
        uniform = self.solved(uniform_req)
        for current, oracle in zip(nonuniform["transient"], uniform["transient"]):
            for actual_layer, expected_layer in zip(current["layer_temperatures_c"], oracle["layer_temperatures_c"]):
                np.testing.assert_allclose(actual_layer, expected_layer[0], atol=1e-10, rtol=0)
        self.assertAlmostEqual(nonuniform["summary"]["transient_final_stored_energy_j"],
                               uniform["summary"]["transient_final_stored_energy_j"], places=10)

    def test_shared_face_half_width_conductances_and_rhs_power(self):
        req = explicit(request(), x=(0, 1, 4, 10), y=(0, 2, 10))
        captured = {}
        def capture(matrix, rhs):
            captured.update(matrix=matrix, rhs=rhs)
            return spsolve(matrix, rhs)
        with patch("python.spike_core.layered_board_thermal.spsolve", side_effect=capture):
            self.solved(req)
        matrix = captured["matrix"]
        # k=1, top dz=.1mm, y shared face=2mm, center distance=(1+3)/2mm.
        self.assertAlmostEqual(-matrix[0, 1], 0.0001 * 0.002 / 0.002, places=14)
        # y link: x face=1mm, center distance=(2+8)/2mm.
        self.assertAlmostEqual(-matrix[0, 3], 0.0001 * 0.001 / 0.005, places=14)
        self.assertAlmostEqual(sum(captured["rhs"][:6]), 0.1, places=13)

    def test_explicit_uniform_edges_reproduce_legacy_temperatures(self):
        req = request()
        req["components"][0]["contact_size_mm"] = 0.2
        legacy = self.solved(req)
        result = self.solved(explicit(copy.deepcopy(req), np.linspace(0, 10, 6), np.linspace(0, 10, 6)))
        for a, b in zip(legacy["layer_grids"], result["layer_grids"]):
            np.testing.assert_allclose(a["temperatures_c"], b["temperatures_c"], rtol=0, atol=1e-10)

    def test_nonuniform_via_column_retains_total_barrel_conductance(self):
        board = design()
        board.vias = [{"layers": ["F.Cu", "B.Cu"], "at": [5, 5], "size": 1, "drill": 0.5}]
        matrices = []
        def capture(matrix, rhs):
            matrices.append(matrix)
            return spsolve(matrix, rhs)
        for included in (False, True):
            req = explicit(request())
            req["board"]["include_vias"] = included
            with patch("python.spike_core.layered_board_thermal.spsolve", side_effect=capture):
                self.solved(req, board)
        difference = matrices[1] - matrices[0]
        expected = 100 * math.pi * (0.5 * 0.02 + 0.02**2) * 1e-6 / 0.00045
        # The via is exactly on an x edge: it is assigned once, never dropped
        # or duplicated. This verifies a lumped point column, not a resolved bore.
        self.assertAlmostEqual(-float(difference[:16, 16:32].sum()), expected, places=13)
        self.assertAlmostEqual(-float(difference[16:32, 32:48].sum()), expected, places=13)

    def test_square_and_imported_rectangular_pad_overlap_conserve_area(self):
        x = np.array([0, 3.7, 4.8, 5.1, 6.2, 10])
        y = np.array([0, 4.2, 4.9, 5.8, 10])
        weights = rectangle_weights(x, y, (4, 4.5, 6, 5.5))
        self.assertAlmostEqual(sum(w for _, w in weights), 1, places=14)
        board = design()
        board.pads = [{"component": "U1", "name": "EP", "type": "smd", "shape": "rect",
            "at": [5, 5], "size": [2, 1], "layers": ["F.Cu"]}]
        contacts = _pad_contacts(board, "U1", (0, 0, 10, 10), (5, 4), (2, 2.5),
                                 x_edges_mm=x, y_edges_mm=y)
        self.assertAlmostEqual(contacts[0]["area_mm2"], 2, places=12)
        np.testing.assert_allclose(contacts[0]["_weights"], weights, atol=3e-15, rtol=0)
        req = explicit(request(), x=x, y=y)
        req["components"][0]["contact_mode"] = "pads"
        result = self.solved(req, board)
        self.assertAlmostEqual(sum(p["heat_w"] for p in result["components"][0]["pad_contacts"]), 0.1, places=10)

    def test_fixed_copper_transfer_preserves_integrated_area(self):
        x, y = np.array([0, 2, 4, 6, 8, 10]), np.array([0, 5, 10])
        tx, ty = np.array([0, 1, 3.8, 4, 4.1, 6.2, 10]), np.array([0, 3, 7, 10])
        values = np.array([[0, 0.2, 1, 0.7, 0], [0, 0.4, 0.8, 0, 0.1]])
        result = transfer_coverage({"F.Cu": values}, x, y, tx, ty)["F.Cu"]
        self.assertAlmostEqual(float(np.sum(values * np.outer(np.diff(y), np.diff(x)))),
                               float(np.sum(result * np.outer(np.diff(ty), np.diff(tx)))), places=12)
        self.assertTrue(np.all((result >= 0) & (result <= 1)))
        board = design()
        board.tracks = [{"layer": "F.Cu", "start": [1, 5], "end": [9, 5], "width": 0.2}]
        req = explicit(request())
        req["board"].update(include_copper=True, copper_raster_step_mm=0.5)
        solved = self.solved(req, board)
        reference_req = copy.deepcopy(req)
        reference_req["board"].update(x_edges_mm=[0, 4.9, 5, 5.1, 10], y_edges_mm=[0, 4, 4.9, 5.1, 6, 10])
        other = self.solved(reference_req, board)
        def area(result):
            grid = result["grid"]
            a = np.outer(np.diff(grid["y_edges_mm"]), np.diff(grid["x_edges_mm"])).ravel()
            return float(np.dot(a, result["layer_grids"][0]["copper_coverage"]))
        self.assertAlmostEqual(area(solved), area(other), places=12)
        self.assertEqual(solved["provenance"]["copper_raster_spacing_mm"], [0.5, 0.5])

    def test_invalid_edge_and_raster_budgets_fail_closed(self):
        cases = [([0, 2, 1, 10], [0, 10]), ([0, 0, 10], [0, 10]),
                 ([0, 5, float("nan"), 10], [0, 10]), ([0, True, 10], [0, 10]),
                 ([0, 9], [0, 10]), (list(np.linspace(0, 10, 100)), list(np.linspace(0, 10, 100)))]
        for x, y in cases:
            with self.subTest(x=x[:4], y=y[:4]):
                self.assertEqual(run_board_thermal(design(), explicit(request(), x, y))["status"], "blocked")
        req = explicit(request())
        req["board"]["include_copper"] = True
        self.assertEqual(run_board_thermal(design(), req)["status"], "blocked")
        req["board"]["copper_raster_step_mm"] = 0.001
        self.assertEqual(run_board_thermal(design(), req)["status"], "blocked")
        req = request()
        req["board"]["x_edges_mm"] = [0, 10]
        self.assertEqual(run_board_thermal(design(), req)["status"], "blocked")

    def test_virtual_sink_full_contact_matches_independent_parallel_path(self):
        req = explicit(request())
        req["virtual_heatsinks"] = [{"id": "HS1", "face": "top", "x_mm": 5, "y_mm": 5,
            "width_mm": 10, "height_mm": 10, "interface_resistance_k_w": 2,
            "sink_to_ambient_k_w": 10}]
        result = self.solved(req)
        # Top half-cell .5 K/W + supplied interface 2 K/W + sink 10 K/W;
        # in parallel with the bottom path 1009.5 K/W.
        rise = 0.1 / (1 / 1009.5 + 1 / 12.5)
        np.testing.assert_allclose(result["grid"]["temperatures_c"], 25 + rise, atol=1e-10, rtol=0)
        self.assertAlmostEqual(result["virtual_heatsinks"][0]["heat_flow_w"], rise / 12.5, places=10)

    def test_pad_rank_one_fill_budget_blocks_before_dense_stamp(self):
        board = design()
        board.pads = [{"component": "U1", "name": "EP", "type": "smd", "shape": "rect",
            "at": [5, 5], "size": [10, 10], "layers": ["F.Cu"]}]
        req = explicit(request(), np.linspace(0, 10, 33), np.linspace(0, 10, 33))
        req["components"][0]["contact_mode"] = "pads"
        result = run_board_thermal(board, req)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("one million matrix terms", result["issues"][0]["message"])

    def test_narrow_source_local_refinement_against_independent_cosine_series(self):
        board = design()
        board.metadata["board_bounds_mm"] = [0, 0, 10, 0.2]
        board.components[0]["at"] = [5, 0.1]
        # Independent continuum-in-x solution of the same three fixed z cells.
        # Neumann end conditions give cosine modes. Each mode solves a 3x3
        # through-depth resistance matrix plus k*dz*(n*pi/L)^2 on its diagonal.
        # Integrating the source rectangle and observation rectangle contributes
        # one sinc each; no thermal-grid matrix or raster enters this oracle.
        thickness = np.array([0.0001, 0.0008, 0.0001])
        g, air = 1 / 0.00045, 1 / 0.10005
        vertical = np.array([[g, -g, 0], [-g, 2 * g, -g], [0, -g, g + air]])
        q_mean = 0.002 / (0.01 * 0.0002)
        expected = 0.0
        for mode in range(2001):
            wavenumber = mode * np.pi / 0.01
            average_cosine = np.cos(mode * np.pi / 2) * np.sinc(mode * 0.0002 / (2 * 0.01))
            heat = np.array([q_mean * (1 if mode == 0 else 2) * average_cosine, 0, 0])
            amplitude = np.linalg.solve(vertical + np.diag(thickness * wavenumber**2), heat)
            expected += amplitude[0] * average_cosine
        errors = []
        for intervals in (20, 40, 80, 160):
            # Only the central 2 mm strip is progressively refined; the full
            # board remains represented, with a fixed coarse exterior.
            x = np.concatenate((np.linspace(0, 4, 41)[:-1],
                np.linspace(4, 6, intervals + 1), np.linspace(6, 10, 41)[1:]))
            req = explicit(request(), x=x, y=(0, 0.2))
            req["components"][0].update(power_w=0.002, contact_size_mm=0.2)
            result = self.solved(req, board)
            errors.append(abs(result["components"][0]["board_temperature_c"] - 25 - expected))
            self.assertLessEqual(result["grid"]["shape"][0], 240)
        self.assertLess(errors[1], errors[0] * 0.45, errors)
        self.assertLess(errors[2], errors[1] * 0.6, errors)
        self.assertLess(errors[3], errors[2] * 0.6, errors)
        self.assertLess(errors[-1], 0.02, errors)


if __name__ == "__main__":
    unittest.main()
