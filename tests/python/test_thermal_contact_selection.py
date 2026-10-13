# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Exact thermal pad selection does not remove other conductive artwork."""

import copy
import unittest

import numpy as np

from python.spike_core.board_thermal import run_board_thermal
from python.spike_core.contracts import SpiDeR


def design():
    return SpiDeR(design_id="contact-selection-oracle", units="mm",
        components=[{"reference": "Q1", "at": [5, 5]}],
        pads=[{"component": "Q1", "name": name, "type": "smd", "shape": "rect",
               "at": [x, 5], "size": [1, 2], "layers": ["F.Cu"]}
              for name, x in [("1", 2), ("2", 5), ("3", 8)]],
        stackup=[{"name": "F.Cu", "type": "copper", "thickness": .1},
                 {"name": "core", "type": "dielectric", "thickness": .8},
                 {"name": "B.Cu", "type": "copper", "thickness": .1}],
        metadata={"board_bounds_mm": [0, 0, 10, 10]})


def request(model="layered"):
    return {"ambient_temperature_c": 25,
        "board": {"model": model, "thickness_mm": 1, "grid_step_mm": 1,
            "convection_top_w_m2k": 10, "convection_bottom_w_m2k": 10,
            "conductivity_w_mk": 1, "dielectric_conductivity_w_mk": 1,
            "copper_conductivity_w_mk": 100, "include_copper": True, "include_vias": False},
        "components": [{"component_ref": "Q1", "power_w": .1,
            "r_junction_case_k_w": 2, "r_case_board_k_w": 3,
            "contact_mode": "pads", "contact_pad_numbers": ["2"]}]}


class ThermalContactSelectionTests(unittest.TestCase):
    def solved(self, board, req):
        result = run_board_thermal(board, req)
        self.assertEqual(result["status"], "completed", result)
        self.assertLess(abs(result["summary"]["energy_balance_error_w"]), 1e-9)
        return result

    def test_only_selected_pad_receives_contact_heat_but_copper_is_unchanged(self):
        board, req = design(), request()
        before = copy.deepcopy(board.pads)
        result = self.solved(board, req)
        selected = result["components"][0]
        self.assertEqual(selected["contact_pad_numbers"], ["2"])
        self.assertEqual([p["pad_name"] for p in selected["pad_contacts"]], ["2"])
        self.assertAlmostEqual(selected["pad_contacts"][0]["heat_w"], .1, places=9)
        self.assertAlmostEqual(selected["case_temperature_c"] - selected["board_temperature_c"], .3, places=9)
        self.assertAlmostEqual(selected["junction_temperature_c"] - selected["case_temperature_c"], .2, places=9)
        req["components"][0].pop("contact_pad_numbers")
        all_pads = self.solved(board, req)
        self.assertEqual(all_pads["components"][0]["pad_count"], 3)
        for a, b in zip(result["layer_grids"], all_pads["layer_grids"]):
            np.testing.assert_array_equal(a["copper_coverage"], b["copper_coverage"])
        self.assertEqual(board.pads, before)

    def test_bottom_selected_pad_and_multiple_lands_with_same_number(self):
        board = design()
        board.pads[1]["layers"] = ["B.Cu"]
        second = copy.deepcopy(board.pads[1])
        second["at"] = [6.5, 5]
        board.pads.append(second)
        part = self.solved(board, request())["components"][0]
        self.assertEqual(part["pad_count"], 2)
        self.assertTrue(all(contact["layer"] == "B.Cu" for contact in part["pad_contacts"]))
        self.assertAlmostEqual(sum(contact["heat_w"] for contact in part["pad_contacts"]), .1, places=9)

    def test_plate_uses_same_exact_selection_and_legacy_has_all_pads(self):
        req = request("plate")
        part = self.solved(design(), req)["components"][0]
        self.assertEqual([p["pad_name"] for p in part["pad_contacts"]], ["2"])
        self.assertAlmostEqual(part["pad_contacts"][0]["heat_w"], .1, places=9)
        req["components"][0].pop("contact_pad_numbers")
        self.assertEqual(self.solved(design(), req)["components"][0]["pad_count"], 3)

    def test_malformed_selection_and_square_selection_block(self):
        invalid = [None, [], "2", [2], [True], [""], [" "], [" 2"], ["2", "2"],
                   ["x" * 129], [str(i) for i in range(257)], ["02"], ["2", "99"]]
        for model in ("layered", "plate"):
            for selected in invalid:
                with self.subTest(model=model, selected=selected):
                    req = request(model)
                    req["components"][0]["contact_pad_numbers"] = selected
                    self.assertEqual(run_board_thermal(design(), req)["status"], "blocked")
            req = request(model)
            req["components"][0].update(contact_mode="square", contact_size_mm=1)
            self.assertEqual(run_board_thermal(design(), req)["status"], "blocked")

    def test_missing_name_or_no_selected_physical_copper_land_blocks(self):
        for change in ({"name": ""}, {"name": None}, {"name": 2},
                       {"type": "np_thru_hole"}, {"layers": ["F.Mask"]}, {"layers": ["In1.Cu"]}):
            with self.subTest(change=change):
                board = design()
                board.pads[1].update(change)
                req = request()
                # Geometry selection must fail even when copper coverage is disabled.
                req["board"]["include_copper"] = False
                self.assertEqual(run_board_thermal(board, req)["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
