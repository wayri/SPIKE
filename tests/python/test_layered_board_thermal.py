# SPDX-License-Identifier: Apache-2.0
"""Independent resistance and heat-balance checks for layered board volumes."""

import math
import unittest

import numpy as np
from scipy.linalg import expm

from python.spike_core.board_thermal import run_board_thermal
from python.spike_core.contracts import DesignIR


def design(vias=None, pads=None):
    return DesignIR(design_id="layered-oracle", units="mm", components=[{"reference": "U1", "at": [5, 5]}],
        stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.1},
                 {"name": "core", "type": "dielectric", "thickness": 0.8},
                 {"name": "B.Cu", "type": "copper", "thickness": 0.1}],
        metadata={"board_bounds_mm": [0, 0, 10, 10]}, vias=vias or [], pads=pads or [])


def request(**board_edits):
    board = {"model": "layered", "thickness_mm": 1.0, "grid_step_mm": 10,
             "convection_top_w_m2k": 0, "convection_bottom_w_m2k": 10,
             "dielectric_conductivity_w_mk": 1, "copper_conductivity_w_mk": 100,
             "via_plating_thickness_mm": 0.02, "include_copper": False, "include_vias": False}
    board.update(board_edits)
    return {"ambient_temperature_c": 25, "board": board,
            "components": [{"component_ref": "U1", "power_w": 0.1,
                            "r_junction_case_k_w": 2, "r_case_board_k_w": 3,
                            "contact_mode": "square", "contact_size_mm": 2}]}


class LayeredBoardThermalTests(unittest.TestCase):
    def test_one_column_series_resistance_and_conservation(self):
        result = run_board_thermal(design(), request())
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(len(result["layer_grids"]), 3)
        # The top-to-bottom center resistance is 0.9 mm/(1 W/mK * 100 mm2).
        top = result["layer_grids"][0]["temperatures_c"][0]
        bottom = result["layer_grids"][-1]["temperatures_c"][0]
        self.assertAlmostEqual(top - bottom, 0.9, places=9)
        # Bottom half-cell conduction (0.05 mm) and 10 W/m2K convection are series.
        self.assertAlmostEqual(bottom - 25, 100.05, places=9)
        self.assertAlmostEqual(result["components"][0]["junction_temperature_c"], top + 0.5, places=9)
        self.assertAlmostEqual(result["summary"]["outward_heat_w"], 0.1, places=9)
        self.assertLess(abs(result["summary"]["energy_balance_error_w"]), 1e-10)

    def test_via_barrel_parallel_path_reference(self):
        via = {"layers": ["F.Cu", "B.Cu"], "at": [5, 5], "size": 1, "drill": 0.5}
        baseline = run_board_thermal(design(vias=[via]), request(include_vias=False))
        solved = run_board_thermal(design(vias=[via]), request(include_vias=True))
        self.assertEqual(solved["status"], "completed", solved)
        barrel_mm2 = math.pi * (0.5 * 0.02 + 0.02**2)
        # Two equal 0.45 mm center spacings; dielectric area = 100 mm2.
        each = (1 * 100 + 100 * barrel_mm2) * 1e-3 / 0.45
        expected_drop = 2 * 0.1 / each
        top = solved["layer_grids"][0]["temperatures_c"][0]
        bottom = solved["layer_grids"][-1]["temperatures_c"][0]
        self.assertAlmostEqual(top - bottom, expected_drop, places=9)
        self.assertLess(top, baseline["layer_grids"][0]["temperatures_c"][0])
        self.assertLess(abs(solved["summary"]["energy_balance_error_w"]), 1e-10)

    def test_virtual_heatsink_series_parallel_reference(self):
        req = request()
        req["virtual_heatsinks"] = [{"id": "HS1", "face": "top", "x_mm": 5, "y_mm": 5,
            "width_mm": 10, "height_mm": 10, "interface_resistance_k_w": 2,
            "sink_to_ambient_k_w": 10}]
        solved = run_board_thermal(design(), req)
        self.assertEqual(solved["status"], "completed", solved)
        # One column: top-to-bottom 9 K/W, bottom-to-ambient 1000.5 K/W.
        # Copper occupancy is disabled here, so the top half-cell uses 1 W/mK:
        # 0.5 K/W solid + 2 K/W interface + 10 K/W sink-to-ambient.
        top_rise = 0.1 / (1 / 1009.5 + 1 / 12.5)
        top = solved["layer_grids"][0]["temperatures_c"][0]
        sink = solved["virtual_heatsinks"][0]
        self.assertAlmostEqual(top, 25 + top_rise, places=9)
        self.assertAlmostEqual(sink["heat_flow_w"], top_rise / 12.5, places=9)
        self.assertAlmostEqual(sink["temperature_c"], 25 + sink["heat_flow_w"] * 10, places=9)
        self.assertAlmostEqual(solved["summary"]["convection_outward_heat_w"] + sink["heat_flow_w"], 0.1, places=9)
        self.assertLess(abs(solved["summary"]["energy_balance_error_w"]), 1e-10)

    def test_virtual_heatsink_invalid_and_plate_rejected(self):
        req = request()
        req["virtual_heatsinks"] = [{"id": "HS1", "face": "top", "x_mm": 5, "y_mm": 5,
            "width_mm": 10, "height_mm": 10, "interface_resistance_k_w": 0,
            "sink_to_ambient_k_w": 0}]
        self.assertEqual(run_board_thermal(design(), req)["status"], "blocked")
        req["virtual_heatsinks"][0]["sink_to_ambient_k_w"] = 10
        req["board"]["model"] = "plate"
        self.assertEqual(run_board_thermal(design(), req)["status"], "blocked")

    def test_bottom_virtual_heatsink_cools_through_stackup(self):
        req = request()
        baseline = run_board_thermal(design(), req)
        req["virtual_heatsinks"] = [{"id": "HS-B", "face": "bottom", "x_mm": 5, "y_mm": 5,
            "width_mm": 10, "height_mm": 10, "interface_resistance_k_w": 1,
            "sink_to_ambient_k_w": 8}]
        solved = run_board_thermal(design(), req)
        self.assertEqual(solved["status"], "completed", solved)
        self.assertGreater(solved["virtual_heatsinks"][0]["heat_flow_w"], 0)
        self.assertLess(solved["components"][0]["junction_temperature_c"], baseline["components"][0]["junction_temperature_c"])
        self.assertLess(abs(solved["summary"]["energy_balance_error_w"]), 1e-10)

    def test_transient_layered_field_against_three_node_exact_solution(self):
        conductance = 1 / 4.5
        air = 1 / 1000.5
        conductance_matrix = np.array([[conductance, -conductance, 0],
                                       [-conductance, 2 * conductance, -conductance],
                                       [0, -conductance, conductance + air]])
        capacities = np.diag([0.01, 0.08, 0.01])
        power = np.array([0.1, 0, 0])
        steady_rise = np.linalg.solve(conductance_matrix, power)
        exact = steady_rise - expm(-np.linalg.solve(capacities, conductance_matrix) * 2) @ steady_rise
        errors = []
        for dt, stride in ((0.1, 4), (0.05, 8)):
            req = request()
            req["transient"] = {"end_time_s": 2, "time_step_s": dt, "output_stride": stride,
                "copper_volumetric_heat_capacity_j_m3k": 1e6,
                "dielectric_volumetric_heat_capacity_j_m3k": 1e6}
            result = run_board_thermal(design(), req)
            self.assertEqual(result["status"], "completed", result)
            self.assertEqual([round(frame["time_s"], 6) for frame in result["transient"]], [0, 0.4, 0.8, 1.2, 1.6, 2])
            final = np.array([layer[0] for layer in result["transient"][-1]["layer_temperatures_c"]]) - 25
            errors.append(abs(final[0] - exact[0]))
            self.assertLess(result["summary"]["max_transient_energy_balance_error_w"], 1e-9)
            self.assertLess(result["summary"]["max_transient_linear_relative_residual"], 1e-9)
            self.assertAlmostEqual(result["transient"][0]["maximum_board_temperature_c"], 25)
        self.assertGreater(errors[0] / errors[1], 1.8)

    def test_transient_missing_capacity_and_output_budget_block(self):
        req = request()
        req["transient"] = {"end_time_s": 2, "time_step_s": 0.1, "output_stride": 1,
            "copper_volumetric_heat_capacity_j_m3k": 1e6}
        self.assertEqual(run_board_thermal(design(), req)["status"], "blocked")
        req["transient"]["dielectric_volumetric_heat_capacity_j_m3k"] = 1e6
        req["transient"]["end_time_s"] = 3
        self.assertEqual(run_board_thermal(design(), req)["status"], "blocked")

    def test_pad_heat_follows_surface_lands(self):
        pads = [{"component": "U1", "name": "A1", "type": "smd", "shape": "circle",
                 "at": [5, 5], "size": [1, 1], "layers": ["F.Cu"]}]
        req = request(include_copper=True, include_vias=False)
        req["components"][0].update(contact_mode="pads")
        req["components"][0].pop("contact_size_mm")
        result = run_board_thermal(design(pads=pads), req)
        self.assertEqual(result["status"], "completed", result)
        part = result["components"][0]
        self.assertEqual(part["pad_count"], 1)
        self.assertEqual(part["pad_contacts"][0]["layer"], "F.Cu")
        self.assertAlmostEqual(part["pad_contacts"][0]["heat_w"], 0.1, places=9)
        self.assertAlmostEqual(part["junction_temperature_c"] - part["case_temperature_c"], 0.2)

    def test_missing_stackup_and_bad_thickness_block(self):
        absent = design()
        absent.stackup = []
        self.assertEqual(run_board_thermal(absent, request())["status"], "blocked")
        invalid = request(thickness_mm=2)
        self.assertEqual(run_board_thermal(design(), invalid)["status"], "blocked")

    def test_unfilled_copper_zone_blocks_with_source_diagnostic(self):
        board = design()
        board.zones = [{"layer": "F.Cu", "points": [[1, 1], [3, 1], [3, 3], [1, 3]]}]
        result = run_board_thermal(board, request(include_copper=True, include_vias=False))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["issues"][0]["code"], "THERMAL_COPPER_UNSUPPORTED_GEOMETRY")

    def test_bga_array_and_qfn_exposed_pad_heat_reaches_distinct_lands(self):
        bga = [{"component": "U1", "name": f"{row}{col}", "type": "smd", "shape": "circle",
                "at": [3.5 + col, 3.5 + row], "size": [0.4, 0.4], "layers": ["F.Cu"]}
               for row in range(4) for col in range(4)]
        qfn = [{"component": "U1", "name": "EP", "type": "smd", "shape": "rect",
                "at": [5, 5], "size": [1, 1], "layers": ["F.Cu"]}]
        for pads, expected in ((bga, 16), (qfn, 1)):
            with self.subTest(pad_count=expected):
                req = request(include_copper=True, include_vias=False, grid_step_mm=0.5)
                req["components"][0].update(contact_mode="pads")
                req["components"][0].pop("contact_size_mm")
                result = run_board_thermal(design(pads=pads), req)
                self.assertEqual(result["status"], "completed", result)
                contacts = result["components"][0]["pad_contacts"]
                self.assertEqual(len(contacts), expected)
                self.assertAlmostEqual(sum(contact["heat_w"] for contact in contacts), 0.1, places=8)
                self.assertLess(abs(result["summary"]["energy_balance_error_w"]), 1e-9)

    def test_untyped_imported_plated_pad_and_oval_slot(self):
        pad = {"component": "U1", "name": "TH1", "shape": "oval", "at": [5, 5],
               "size": [1.5, 1], "drill_size": [0.6, 0.3], "layers": ["*.Cu", "*.Mask"]}
        baseline = run_board_thermal(design(pads=[pad]), request(include_vias=False))
        result = run_board_thermal(design(pads=[pad]), request(include_vias=True))
        self.assertEqual(result["status"], "completed", result)
        self.assertLess(result["grid"]["temperatures_c"][0], baseline["grid"]["temperatures_c"][0])


if __name__ == "__main__":
    unittest.main()
