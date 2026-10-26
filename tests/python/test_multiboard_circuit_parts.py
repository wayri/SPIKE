# SPDX-License-Identifier: Apache-2.0
"""Independent series/parallel impedance checks for explicit chassis paths."""
import copy
import json
import math
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from python.spike_core.solvers.circuits.models.multiboard_circuit import compile_multiboard_circuit, run_multiboard_circuit


def fixture():
    return {"contract": "spike/multiboard-circuit-request/v1", "domain": "si",
            "assembly": {"contract": "spike/assembly-ir/v1", "assembly_id": "case-test", "name": "Chassis path",
                         "boards": [{"id": "board", "design_id": "design"}],
                         "parts": [{"id": "case", "model_id": "case-step", "part_type": "enclosure"}],
                         "electrical_bonds": [{"id": "signal", "endpoint_a": "board::pad", "endpoint_b": "case::contact"},
                                              {"id": "return", "endpoint_a": "case", "endpoint_b": "board:ground"}]},
            "board_models": [{"board_id": "board", "elements": [
                {"id": "source", "type": "voltage_source", "positive_node": "s", "negative_node": "0", "ac_magnitude": 1},
                {"id": "series", "type": "resistor", "positive_node": "s", "negative_node": "out", "resistance_ohm": 10},
                {"id": "load", "type": "resistor", "positive_node": "out", "negative_node": "0", "resistance_ohm": 6}]}],
            "part_models": [{"part_id": "case", "elements": [
                {"id": "load", "type": "capacitor", "positive_node": "out", "negative_node": "0", "capacitance_f": 1e-5}]}],
            "electrical_bond_models": [
                {"bond_id": "signal", "endpoint_a": {"board_id": "board", "node": "out"},
                 "endpoint_b": {"part_id": "case", "node": "out"}, "resistance_ohm": .2, "inductance_h": 1e-5},
                {"bond_id": "return", "endpoint_a": {"part_id": "case", "node": "0"},
                 "endpoint_b": {"board_id": "board", "node": "0"}, "resistance_ohm": .3, "inductance_h": 0}],
            "link_models": [], "ground": {"board_id": "board", "node": "0"},
            "analysis": {"mode": "ac", "start_hz": 1000, "stop_hz": 10000, "points": 3, "scale": "log"}}


class CircuitPartTests(unittest.TestCase):
    def test_chassis_transfer_contact_sensitivity_and_local_zero(self):
        raw = fixture()
        before = copy.deepcopy(raw)
        result = run_multiboard_circuit(raw)
        self.assertEqual(raw, before)
        self.assertEqual(result["status"], "completed")
        self.assertNotIn("case", result["node_map"])
        self.assertNotEqual(result["node_map"]["board"]["0"], result["part_node_map"]["case"]["0"])
        self.assertNotEqual(result["element_map"]["board"]["load"], result["part_element_map"]["case"]["load"])
        data = result["native_result"]["data"]
        def voltage(owner, node, i, parts=False):
            key = result["part_node_map" if parts else "node_map"][owner][node]
            series = data["node_voltage_v"][key]
            return complex(series["real"][i], series["imaginary"][i])
        for i, frequency in enumerate(data["frequency_hz"]):
            omega = 2 * math.pi * frequency
            zc = 1 / (1j * omega * 1e-5)
            path = .5 + 1j * omega * 1e-5 + zc
            load = 1 / (1 / 6 + 1 / path)
            expected = load / (10 + load)
            self.assertAlmostEqual(abs(voltage("board", "out", i) - expected), 0, places=11)
            self.assertAlmostEqual(abs(voltage("case", "0", i, True) - expected / path * .3), 0, places=11)
            self.assertAlmostEqual(abs(voltage("case", "out", i, True) - voltage("case", "0", i, True) - expected / path * zc), 0, places=11)
            self.assertGreater(abs(expected - 6 / 16), .01)
        raw["electrical_bond_models"][0]["resistance_ohm"] = 100
        changed = run_multiboard_circuit(raw)
        key = result["node_map"]["board"]["out"]
        series = changed["native_result"]["data"]["node_voltage_v"][key]
        actual = complex(series["real"][0], series["imaginary"][0])
        omega = 2 * math.pi * 1000
        path = 100.3 + 1j * omega * 1e-5 + 1 / (1j * omega * 1e-5)
        load = 1 / (1 / 6 + 1 / path)
        self.assertAlmostEqual(abs(actual - load / (10 + load)), 0, places=11)
        self.assertGreater(abs(actual - voltage("board", "out", 0)), .01)

    def test_exact_coverage_owner_identity_passivity_and_reference(self):
        for change in (lambda r: r.pop("part_models"),
                       lambda r: r.pop("electrical_bond_models"),
                       lambda r: r["electrical_bond_models"].pop(),
                       lambda r: r["part_models"][0].update(part_id="board"),
                       lambda r: r["part_models"][0]["elements"][0].update(type="current_source"),
                       lambda r: r["part_models"][0]["elements"][0].update(capacitance_f=-1),
                       lambda r: r["ground"].update(part_id="case"),
                       lambda r: r["ground"].update(board_id="case"),
                       lambda r: r["electrical_bond_models"][0].update(resistance_ohm=-1),
                       lambda r: r["electrical_bond_models"][0].update(bond_id="missing"),
                       lambda r: r["electrical_bond_models"][0].update(endpoint_a={"part_id": "case", "node": "out"}),
                       lambda r: r["electrical_bond_models"][0]["endpoint_a"].update(node="missing")):
            raw = fixture(); change(raw)
            with self.assertRaises(ValueError): compile_multiboard_circuit(raw)

    def test_schema_hierarchy_and_explicit_part_ground(self):
        raw = fixture()
        raw["assembly"]["parts"].append({"id": "group", "part_type": "subassembly"})
        raw["ground"] = {"part_id": "case", "node": "0"}
        schema = json.loads((Path(__file__).resolve().parents[2] / "schemas/multiboard-circuit-request-v1.schema.json").read_text())
        validator = Draft202012Validator(schema)
        validator.validate(raw)
        result = run_multiboard_circuit(raw)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["excluded_hierarchy_part_ids"], ["group"])
        self.assertEqual(result["ground_node"], result["part_node_map"]["case"]["0"])
        raw["ground"]["board_id"] = "board"
        self.assertTrue(list(validator.iter_errors(raw)))

    def test_no_bond_return_is_not_implicitly_grounded(self):
        raw = fixture()
        raw["assembly"]["electrical_bonds"] = []
        raw["electrical_bond_models"] = []
        with self.assertRaisesRegex(ValueError, "at least one retained"):
            compile_multiboard_circuit(raw)
        raw = fixture()
        raw["part_models"][0]["elements"].append({"id": "floating", "type": "resistor", "positive_node": "x", "negative_node": "y", "resistance_ohm": 1})
        self.assertEqual(run_multiboard_circuit(raw)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
