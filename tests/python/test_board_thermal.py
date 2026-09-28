# SPDX-License-Identifier: Apache-2.0
"""Analytical and conservation checks for the explicit board-plate model."""

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from python.spike_core.board_thermal import run_board_thermal
from python.spike_core.contracts import DesignIR
from python.spike_core.service_simulation_handlers import handle_simulation_request


def design():
    return DesignIR(design_id="thermal-board", name="Fixture", source_format="test",
                    components=[{"reference": "U1", "at": [5, 5]}],
                    metadata={"board_bounds_mm": [0, 0, 10, 10]})


def request(step=10):
    return {"ambient_temperature_c": 25,
            "board": {"conductivity_w_mk": 10, "thickness_mm": 1,
                      "convection_top_w_m2k": 10, "convection_bottom_w_m2k": 10,
                      "grid_step_mm": step},
            "components": [{"component_ref": "U1", "power_w": 0.1,
                            "r_junction_case_k_w": 2, "r_case_board_k_w": 3,
                            "contact_size_mm": 2}]}


class BoardThermalTests(unittest.TestCase):
    def test_one_cell_analytic_temperature_and_junction_chain(self):
        result = run_board_thermal(design(), request())
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["model_status"], "approximate")
        part = result["components"][0]
        self.assertAlmostEqual(result["grid"]["temperatures_c"][0], 75)
        self.assertAlmostEqual(part["board_temperature_c"], 75)
        self.assertAlmostEqual(part["case_temperature_c"], 75.3)
        self.assertAlmostEqual(part["junction_temperature_c"], 75.5)
        self.assertAlmostEqual(result["summary"]["outward_heat_w"], 0.1)
        self.assertFalse(result["provenance"]["production_qualified"])

    def test_fixed_contact_symmetric_refinement_and_energy(self):
        fine = run_board_thermal(design(), request(step=1))
        self.assertEqual(fine["status"], "completed", fine)
        field = fine["grid"]["temperatures_c"]
        self.assertEqual(fine["grid"]["shape"], [10, 10])
        for iy in range(10):
            for ix in range(10):
                self.assertAlmostEqual(field[iy * 10 + ix], field[iy * 10 + (9 - ix)], places=10)
        self.assertLess(abs(fine["summary"]["energy_balance_error_w"]), 1e-11)
        self.assertLess(fine["summary"]["linear_relative_residual"], 1e-10)

    def test_two_cell_lateral_conduction_analytic_oracle(self):
        board = design()
        board.metadata["board_bounds_mm"] = [0, 0, 20, 10]
        solution = run_board_thermal(board, request(step=10))
        self.assertEqual(solution["status"], "completed", solution)
        sink = 20 * 0.01 * 0.01  # two faces, 10 W/m2K each
        lateral = 10 * 0.001 * 0.01 / 0.01  # k * thickness * face length / spacing
        expected_left = 25 + 0.1 * (sink + lateral) / (sink * (sink + 2 * lateral))
        expected_right = 25 + 0.1 * lateral / (sink * (sink + 2 * lateral))
        self.assertAlmostEqual(solution["grid"]["temperatures_c"][0], expected_left, places=10)
        self.assertAlmostEqual(solution["grid"]["temperatures_c"][1], expected_right, places=10)

    def test_unknown_ref_and_unphysical_inputs_block(self):
        for change in (lambda q: q["components"][0].update(component_ref="NOPE"),
                       lambda q: q["components"][0].update(contact_size_mm=20),
                       lambda q: q["components"][0].update(r_junction_case_k_w=0),
                       lambda q: q["board"].update(convection_top_w_m2k=0, convection_bottom_w_m2k=0),
                       lambda q: q["board"].update(grid_step_mm=0.01)):
            with self.subTest(change=change):
                candidate = copy.deepcopy(request())
                change(candidate)
                result = run_board_thermal(design(), candidate)
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["grid"], None)

    def test_worker_method_uses_same_solver(self):
        output = handle_simulation_request("run_board_thermal",
                                           {"design": design().__dict__, "request": request()},
                                           assembly_scope={}, solver_registry=None)
        self.assertTrue(output["ok"])
        self.assertEqual(output["result"]["contract"], "spike/board-thermal-result/v1")
        self.assertEqual(output["result"]["status"], "completed")

    def test_source_import_rejects_non_kicad_text(self):
        output = handle_simulation_request("run_board_thermal",
                                           {"design": design().__dict__, "source_kicad_pcb": "not a PCB",
                                            "request": request()},
                                           assembly_scope={}, solver_registry=None)
        self.assertTrue(output["ok"])
        self.assertEqual(output["result"]["status"], "blocked")
        self.assertEqual(output["result"]["issues"][0]["code"], "BOARD_THERMAL_SOURCE_INVALID")

    def test_desktop_parsed_component_reference_is_accepted(self):
        board = design()
        board.components = [{"ref": "U1", "at": [5, 5]}]
        output = handle_simulation_request("run_board_thermal",
                                           {"design": board.__dict__, "request": request()},
                                           assembly_scope={}, solver_registry=None)
        self.assertTrue(output["ok"])
        result = output["result"]
        self.assertEqual(result["status"], "completed", result)

    def test_imported_pad_contact_excludes_nonplated_hole_and_conserves_heat(self):
        board = design()
        board.pads = [
            {"component": "U1", "name": "A1", "type": "smd", "shape": "circle", "at": [4, 5], "size": [1, 1], "layers": ["F.Cu"]},
            {"component": "U1", "name": "A2", "type": "smd", "shape": "circle", "at": [6, 5], "size": [1, 1], "layers": ["F.Cu"]},
            {"component": "U1", "name": "mount", "type": "np_thru_hole", "shape": "circle", "at": [5, 5], "size": [2, 2], "drill": 2, "layers": ["*.Cu"]},
        ]
        case = request(step=1)
        case["components"][0].pop("contact_size_mm")
        case["components"][0]["contact_mode"] = "pads"
        result = run_board_thermal(board, case)
        self.assertEqual(result["status"], "completed", result)
        part = result["components"][0]
        self.assertEqual(part["pad_count"], 2)
        self.assertEqual({pad["pad_name"] for pad in part["pad_contacts"]}, {"A1", "A2"})
        self.assertAlmostEqual(sum(pad["heat_w"] for pad in part["pad_contacts"]), 0.1)
        self.assertAlmostEqual(part["case_temperature_c"] - part["board_temperature_c"], 0.3)
        self.assertAlmostEqual(part["junction_temperature_c"] - part["case_temperature_c"], 0.2)

    def test_public_request_and_result_schemas(self):
        root = Path(__file__).resolve().parents[2]
        request_schema = json.loads((root / "schemas/board-thermal-request-v1.schema.json").read_text(encoding="utf-8"))
        result_schema = json.loads((root / "schemas/board-thermal-result-v1.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(request_schema)
        Draft202012Validator.check_schema(result_schema)
        Draft202012Validator(request_schema).validate(request())
        Draft202012Validator(result_schema).validate(run_board_thermal(design(), request()))


if __name__ == "__main__":
    unittest.main()
