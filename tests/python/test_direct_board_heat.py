# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Direct board deposition conserves supplied power without package claims."""

import copy
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.board_thermal import _pad_boundary_polygon, run_board_thermal
from python.spike_core.contracts import SpiDeR
from python.spike_core.layered_board_thermal import MAX_DIRECT_CONTACT_WEIGHTS


def design():
    return SpiDeR(design_id="direct-board-oracle", units="mm",
        components=[{"reference": "Q1", "at": [5, 5]}, {"reference": "Q2", "at": [5, 5]}],
        pads=[{"component": "Q1", "name": "1", "type": "smd", "shape": "rect",
               "at": [2, 5], "size": [1, 1], "layers": ["F.Cu"]},
              {"component": "Q1", "name": "2", "type": "smd", "shape": "rect",
               "at": [5, 5], "size": [2, 1], "layers": ["B.Cu"]}],
        stackup=[{"name": "F.Cu", "type": "copper", "thickness": .1},
                 {"name": "core", "type": "dielectric", "thickness": .8},
                 {"name": "B.Cu", "type": "copper", "thickness": .1}],
        metadata={"board_bounds_mm": [0, 0, 10, 10]})


def request():
    return {"ambient_temperature_c": 25,
        "board": {"model": "layered", "thickness_mm": 1, "grid_step_mm": 10,
            "x_edges_mm": [0, 3, 10], "y_edges_mm": [0, 4, 10],
            "convection_top_w_m2k": 0, "convection_bottom_w_m2k": 10,
            "dielectric_conductivity_w_mk": 1, "copper_conductivity_w_mk": 100,
            "include_copper": False, "include_vias": False}, "components": [],
        "board_heat_sources": [{"id": "Q1-loss", "component_ref": "Q1", "power_w": .1,
                               "contact_mode": "square", "contact_size_mm": 10}]}


class DirectBoardHeatTests(unittest.TestCase):
    def solved(self, req, board=None):
        result = run_board_thermal(board or design(), req)
        self.assertEqual(result["status"], "completed", result)
        self.assertLess(abs(result["summary"]["energy_balance_error_w"]), 1e-9)
        self.assertEqual(result["model_status"], "approximate")
        return result

    def test_board_only_uniform_flux_exact_reference_and_no_junction_claim(self):
        result = self.solved(request())
        for layer, expected in zip(result["layer_grids"], [125.95, 125.5, 125.05]):
            np.testing.assert_allclose(layer["temperatures_c"], expected, atol=1e-9, rtol=0)
        self.assertEqual(result["components"], [])
        self.assertIsNone(result["summary"]["maximum_junction_temperature_c"])
        source = result["board_heat_sources"][0]
        self.assertEqual(source["face"], "top")
        self.assertAlmostEqual(source["board_temperature_c"], 125.95, places=9)
        self.assertIsNone(source["case_temperature_c"])
        self.assertIsNone(source["junction_temperature_c"])
        self.assertEqual(source["temperature_status"], "board_only_junction_unsolved")
        self.assertIn("THERMAL_DIRECT_BOARD_HEAT", [i["code"] for i in result["issues"]])

    def test_selected_bottom_pad_has_all_power_but_other_copper_remains(self):
        req = request()
        req["board"].update(include_copper=True, copper_raster_step_mm=.5)
        source = req["board_heat_sources"][0]
        source.pop("contact_size_mm")
        source.update(contact_mode="pads", contact_pad_numbers=["2"])
        result = self.solved(req)
        contact = result["board_heat_sources"][0]["pad_contacts"][0]
        self.assertEqual(contact["pad_name"], "2")
        self.assertEqual(contact["layer"], "B.Cu")
        self.assertAlmostEqual(contact["heat_w"], .1, places=12)
        self.assertAlmostEqual(contact["area_mm2"], 2, places=12)
        source.pop("contact_pad_numbers")
        all_pads = self.solved(req)
        contacts = all_pads["board_heat_sources"][0]["pad_contacts"]
        self.assertEqual(len(contacts), 2)
        self.assertAlmostEqual(contacts[0]["heat_w"], .1 / 3, places=12)
        self.assertAlmostEqual(contacts[1]["heat_w"], .2 / 3, places=12)
        for a, b in zip(result["layer_grids"], all_pads["layer_grids"]):
            np.testing.assert_array_equal(a["copper_coverage"], b["copper_coverage"])

    def test_mixed_sources_count_power_once_and_retain_component_junction_only(self):
        req = request()
        req["components"] = [{"component_ref": "Q2", "power_w": .05, "contact_mode": "square",
            "contact_size_mm": 10, "r_junction_case_k_w": 2, "r_case_board_k_w": 3}]
        result = self.solved(req)
        self.assertAlmostEqual(result["summary"]["total_power_w"], .15, places=12)
        self.assertAlmostEqual(result["summary"]["outward_heat_w"], .15, places=10)
        self.assertEqual(result["summary"]["maximum_junction_temperature_c"],
                         result["components"][0]["junction_temperature_c"])
        self.assertIsNone(result["board_heat_sources"][0]["junction_temperature_c"])

    def test_transient_board_only_matches_same_deposition_from_legacy_square(self):
        req = request()
        req["transient"] = {"end_time_s": 1, "time_step_s": .1, "output_stride": 1,
            "copper_volumetric_heat_capacity_j_m3k": 1e6,
            "dielectric_volumetric_heat_capacity_j_m3k": 1e6}
        direct = self.solved(req)
        legacy = copy.deepcopy(req)
        legacy.pop("board_heat_sources")
        legacy["components"] = [{"component_ref": "Q1", "power_w": .1, "contact_mode": "square",
            "contact_size_mm": 10, "r_junction_case_k_w": 2, "r_case_board_k_w": 3}]
        reference = self.solved(legacy)
        for a, b in zip(direct["transient"], reference["transient"]):
            np.testing.assert_allclose(a["layer_temperatures_c"], b["layer_temperatures_c"], rtol=0, atol=1e-12)
        self.assertLess(direct["summary"]["max_transient_energy_balance_error_w"], 1e-10)

    def test_plate_and_empty_or_excessive_source_lists_rejected(self):
        for sources in ([], None, "source", [request()["board_heat_sources"][0]] * 257):
            req = request()
            req["board_heat_sources"] = sources
            self.assertEqual(run_board_thermal(design(), req)["status"], "blocked")
        req = request()
        req["board"]["model"] = "plate"
        self.assertEqual(run_board_thermal(design(), req)["status"], "blocked")
        req = request()
        req.pop("board_heat_sources")
        self.assertEqual(run_board_thermal(design(), req)["status"], "blocked")
        req = request()
        req["components"] = [{"component_ref": "Q2"}] * 256
        self.assertEqual(run_board_thermal(design(), req)["status"], "blocked")

    def test_unknown_duplicate_and_package_fields_rejected(self):
        cases = [{"id": ""}, {"id": " x"}, {"id": "x" * 129}, {"component_ref": "Q404"},
                 {"power_w": -1}, {"power_w": None}, {"contact_mode": "unknown"},
                 {"r_case_board_k_w": 3}, {"r_junction_case_k_w": 2}, {"contact_pad_numbers": ["2"]}]
        for edits in cases:
            with self.subTest(edits=edits):
                req = request()
                req["board_heat_sources"][0].update(edits)
                self.assertEqual(run_board_thermal(design(), req)["status"], "blocked")
        for duplicate_id in (True, False):
            req = request()
            other = copy.deepcopy(req["board_heat_sources"][0])
            other.update(component_ref="Q2" if duplicate_id else "Q1", id="Q1-loss" if duplicate_id else "other")
            req["board_heat_sources"].append(other)
            self.assertEqual(run_board_thermal(design(), req)["status"], "blocked")
        req = request()
        req["components"] = [{"component_ref": "Q1", "power_w": .05, "contact_mode": "square",
            "contact_size_mm": 10, "r_junction_case_k_w": 2, "r_case_board_k_w": 3}]
        self.assertEqual(run_board_thermal(design(), req)["status"], "blocked")

    def test_overlap_budget_stops_repeated_lands_during_contact_generation(self):
        self.assertEqual(MAX_DIRECT_CONTACT_WEIGHTS, 1_000_000)
        board, req = design(), request()
        pad = {"component": "Q1", "name": "2", "type": "smd", "shape": "rect",
               "at": [5, 5], "size": [10, 10], "layers": ["F.Cu"]}
        board.pads = [copy.deepcopy(pad) for _ in range(10)]
        req["board_heat_sources"] = [{"id": "Q1-loss", "component_ref": "Q1", "power_w": .1,
                                      "contact_mode": "pads"}]
        # Four overlaps per land: fail inside the second land, before collecting
        # its weights or visiting the remaining eight duplicate physical lands.
        with patch("python.spike_core.layered_board_thermal.MAX_DIRECT_CONTACT_WEIGHTS", 5):
            with patch("python.spike_core.board_thermal._pad_boundary_polygon", wraps=_pad_boundary_polygon) as geometry:
                result = run_board_thermal(board, req)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("overlap-weight budget", result["issues"][0]["message"])
        self.assertEqual(geometry.call_count, 2)

    def test_overlap_budget_accumulates_across_both_board_faces(self):
        board, req = design(), request()
        board.pads = [{"component": "Q1", "name": "2", "type": "smd", "shape": "rect",
                       "at": [5, 5], "size": [10, 10], "layers": ["F.Cu", "B.Cu"]}]
        req["board_heat_sources"] = [{"id": "Q1-loss", "component_ref": "Q1", "power_w": .1,
                                      "contact_mode": "pads"}]
        with patch("python.spike_core.layered_board_thermal.MAX_DIRECT_CONTACT_WEIGHTS", 8):
            self.solved(req, board)
        with patch("python.spike_core.layered_board_thermal.MAX_DIRECT_CONTACT_WEIGHTS", 7):
            result = run_board_thermal(board, req)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("overlap-weight budget", result["issues"][0]["message"])

    def test_overlap_budget_accumulates_across_pad_and_square_sources(self):
        board, req = design(), request()
        board.pads = [{"component": "Q1", "name": "2", "type": "smd", "shape": "rect",
                       "at": [5, 5], "size": [10, 10], "layers": ["F.Cu"]}]
        sources = [{"id": "Q1-loss", "component_ref": "Q1", "power_w": .1, "contact_mode": "pads"},
                   {"id": "Q2-loss", "component_ref": "Q2", "power_w": .1,
                    "contact_mode": "square", "contact_size_mm": 10}]
        for order in (sources, list(reversed(sources))):
            req["board_heat_sources"] = order
            with patch("python.spike_core.layered_board_thermal.MAX_DIRECT_CONTACT_WEIGHTS", 8):
                self.solved(req, board)
            with patch("python.spike_core.layered_board_thermal.MAX_DIRECT_CONTACT_WEIGHTS", 7):
                result = run_board_thermal(board, req)
            self.assertEqual(result["status"], "blocked")
            self.assertIn("overlap-weight budget", result["issues"][0]["message"])


if __name__ == "__main__":
    unittest.main()
