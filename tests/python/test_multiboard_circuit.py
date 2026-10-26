# SPDX-License-Identifier: Apache-2.0
"""Independent KVL and impedance oracles for retained two-board coupling."""
import copy
import math
import unittest

from python.spike_core.solvers.circuits.models.multiboard_circuit import MultiboardCircuitError, compile_multiboard_circuit, run_multiboard_circuit


def fixture():
    return {"contract": "spike/multiboard-circuit-request/v1", "domain": "pi",
            "assembly": {"contract": "spike/assembly-ir/v1", "assembly_id": "test", "name": "two boards",
                         "boards": [{"id": board, "design_id": "same-layout"} for board in ("a", "b")],
                         "harnesses": [{"id": "cable", "endpoint_a": "a::J", "endpoint_b": "b::J", "pin_map": {"1": "1", "2": "2"}}]},
            "board_models": [
                {"board_id": "a", "elements": [{"id": "supply", "type": "voltage_source", "positive_node": "J:1", "negative_node": "J:2", "dc_value": 12, "ac_magnitude": 1}]},
                {"board_id": "b", "elements": [{"id": "load", "type": "resistor", "positive_node": "J:1", "negative_node": "J:2", "resistance_ohm": 6}]}],
            "link_models": [{"link_id": "cable", "kind": "harness", "pins": [
                {"source_pin": "1", "target_pin": "1", "resistance_ohm": .1, "inductance_h": 0},
                {"source_pin": "2", "target_pin": "2", "resistance_ohm": .2, "inductance_h": 0}]}],
            "ground": {"board_id": "a", "node": "J:2"}, "analysis": {"mode": "operating_point"}}


class MultiboardCircuitTests(unittest.TestCase):
    def test_dc_shared_solve_kvl_power_and_contact_sensitivity(self):
        raw = fixture()
        before = copy.deepcopy(raw)
        result = run_multiboard_circuit(raw)
        self.assertEqual(raw, before)
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["production_qualified"])
        data = result["native_result"]["data"]
        nodes = result["node_map"]["b"]
        current = 12 / 6.3
        self.assertAlmostEqual(data["node_voltage_v"][nodes["J:1"]] - data["node_voltage_v"][nodes["J:2"]], current * 6, places=10)
        self.assertAlmostEqual(sum(data["element_power_w"].values()), 0, places=10)
        link_loss = sum(data["element_power_w"][element] for link in result["links"] for element in link["element_ids"])
        self.assertAlmostEqual(link_loss, current ** 2 * .3, places=10)
        raw["link_models"][0]["pins"][0]["resistance_ohm"] = 3
        changed = run_multiboard_circuit(raw)
        voltage = changed["native_result"]["data"]["node_voltage_v"]
        self.assertAlmostEqual(voltage[nodes["J:1"]] - voltage[nodes["J:2"]], 12 * 6 / 9.2, places=10)

    def test_ac_series_impedance_reference_and_frequency_grid(self):
        raw = fixture()
        raw["domain"] = "si"
        raw["analysis"] = {"mode": "ac", "start_hz": 100, "stop_hz": 10000, "points": 3, "scale": "log"}
        raw["link_models"][0]["pins"][0]["inductance_h"] = 1e-3
        result = run_multiboard_circuit(raw)
        self.assertEqual(result["status"], "completed")
        data, nodes = result["native_result"]["data"], result["node_map"]["b"]
        def values(node):
            series = data["node_voltage_v"][node]
            return [complex(a, b) for a, b in zip(series["real"], series["imaginary"])]
        for frequency, a, b in zip(data["frequency_hz"], values(nodes["J:1"]), values(nodes["J:2"])):
            expected = 6 / (6.3 + 2j * math.pi * frequency * .001)
            self.assertAlmostEqual(abs(a - b - expected), 0, places=10)
        self.assertLess(result["native_result"]["diagnostics"]["relative_residual_max"], 1e-10)

    def test_capacitance_reference_and_analytic_pi_transfer(self):
        raw = fixture()
        raw["domain"] = "si"
        raw["analysis"] = {"mode": "ac", "start_hz": 1000, "stop_hz": 1000, "points": 1}
        raw["link_models"][0]["pins"][1]["resistance_ohm"] = 0
        pin = raw["link_models"][0]["pins"][0]
        pin.update(capacitance_f=1e-3, reference={"board_id": "a", "node": "J:2"})
        result = run_multiboard_circuit(raw)
        series = result["native_result"]["data"]["node_voltage_v"][result["node_map"]["b"]["J:1"]]
        z = 1 / (1 / 6 + 2j * math.pi * 1000 * .001 / 2)
        self.assertAlmostEqual(abs(complex(series["real"][0], series["imaginary"][0]) - z / (.1 + z)), 0, places=10)

    def test_separate_contact_properties_enter_solution(self):
        raw = fixture()
        pin = raw["link_models"][0]["pins"][0]
        pin.update(contact_a_resistance_ohm=.4, contact_b_resistance_ohm=.5,
                   contact_a_inductance_h=1e-4, contact_b_inductance_h=2e-4)
        result = run_multiboard_circuit(raw)
        self.assertEqual(result["status"], "completed")
        link = result["links"][0]
        self.assertAlmostEqual(link["total_series_resistance_ohm"], 1)
        self.assertAlmostEqual(link["total_series_inductance_h"], 3e-4)
        self.assertEqual(link["properties"]["contact_b_resistance_ohm"], .5)
        current = 12 / 7.2
        self.assertAlmostEqual(link["current_a"], current, places=10)
        self.assertAlmostEqual(link["conductor_loss_w"], current ** 2 * .1, places=10)
        self.assertAlmostEqual(link["contact_a_loss_w"], current ** 2 * .4, places=10)
        self.assertAlmostEqual(link["contact_b_loss_w"], current ** 2 * .5, places=10)
        self.assertAlmostEqual(link["total_loss_w"], current ** 2, places=10)
        volts = result["native_result"]["data"]["node_voltage_v"]
        nodes = result["node_map"]["b"]
        self.assertAlmostEqual(volts[nodes["J:1"]] - volts[nodes["J:2"]], 12 * 6 / 7.2, places=10)

    def test_schema_accepts_fixture_and_rejects_negative_contacts(self):
        import json
        from pathlib import Path
        from jsonschema import Draft202012Validator
        schema = json.loads((Path(__file__).resolve().parents[2] / "schemas/multiboard-circuit-request-v1.schema.json").read_text())
        validator = Draft202012Validator(schema)
        validator.validate(fixture())
        raw = fixture()
        raw["link_models"][0]["pins"][0]["contact_a_resistance_ohm"] = -1
        self.assertTrue(list(validator.iter_errors(raw)))

    def test_occurrence_identity_and_no_implicit_zero_short(self):
        raw = fixture()
        for model in raw["board_models"]:
            model["elements"].append({"id": "same", "type": "resistor", "positive_node": "0", "negative_node": "J:2", "resistance_ohm": 1})
        result = run_multiboard_circuit(raw)
        self.assertNotEqual(result["node_map"]["a"]["0"], result["node_map"]["b"]["0"])
        self.assertNotEqual(result["element_map"]["a"]["same"], result["element_map"]["b"]["same"])
        voltages = result["native_result"]["data"]["node_voltage_v"]
        self.assertAlmostEqual(voltages[result["node_map"]["b"]["0"]], 12 / 6.3 * .2, places=10)

    def test_missing_coverage_reference_and_unsupported_mutual_rejected(self):
        raw = fixture()
        raw["link_models"][0]["pins"].pop()
        with self.assertRaisesRegex(MultiboardCircuitError, "coverage"):
            compile_multiboard_circuit(raw)
        raw = fixture()
        raw["link_models"][0]["pins"][0]["capacitance_f"] = 1e-9
        with self.assertRaisesRegex(MultiboardCircuitError, "reference"):
            compile_multiboard_circuit(raw)
        raw = fixture()
        raw["link_models"][0]["mutual_inductance_h"] = 1e-6
        with self.assertRaisesRegex(MultiboardCircuitError, "unsupported"):
            compile_multiboard_circuit(raw)

    def test_floating_subcircuit_preserves_failure(self):
        raw = fixture()
        raw["board_models"][1]["elements"].append({"id": "floating", "type": "resistor", "positive_node": "x", "negative_node": "y", "resistance_ohm": 10})
        result = run_multiboard_circuit(raw)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("data", result["native_result"])
        self.assertNotIn("current_a", result["links"][0])

    def test_capacitor_only_return_floats_at_dc_but_executes_at_ac(self):
        raw = fixture()
        raw["board_models"][1]["elements"].append({"id": "ac-reference", "type": "capacitor", "positive_node": "ac-only", "negative_node": "J:2", "capacitance_f": 1e-6})
        self.assertEqual(run_multiboard_circuit(raw)["status"], "failed")
        raw["domain"] = "si"
        raw["analysis"] = {"mode": "ac", "start_hz": 1000, "stop_hz": 1000, "points": 1}
        result = run_multiboard_circuit(raw)
        self.assertEqual(result["status"], "completed")
        self.assertNotIn("current_a", result["links"][0])

    def test_ideal_and_inductor_only_pin_report_zero_dc_loss(self):
        raw = fixture()
        for pin in raw["link_models"][0]["pins"]:
            pin["resistance_ohm"] = 0
        raw["link_models"][0]["pins"][0]["inductance_h"] = 1e-6
        result = run_multiboard_circuit(raw)
        self.assertEqual(result["status"], "completed")
        for link in result["links"]:
            self.assertAlmostEqual(abs(link["current_a"]), 2, places=10)
            self.assertEqual(link["total_loss_w"], 0)

    def test_irrelevant_element_fields_are_rejected(self):
        raw = fixture()
        raw["board_models"][1]["elements"][0]["gain"] = 3
        with self.assertRaisesRegex(MultiboardCircuitError, "unsupported"):
            compile_multiboard_circuit(raw)

    def test_blank_excitation_not_silently_zeroed(self):
        raw = fixture()
        del raw["board_models"][0]["elements"][0]["dc_value"]
        with self.assertRaisesRegex(MultiboardCircuitError, "explicit dc_value"):
            compile_multiboard_circuit(raw)
        raw = fixture()
        raw["domain"] = "si"
        raw["analysis"] = {"mode": "ac", "start_hz": 1000, "stop_hz": 10000, "points": 3}
        del raw["board_models"][0]["elements"][0]["ac_magnitude"]
        with self.assertRaisesRegex(MultiboardCircuitError, "explicit ac_magnitude"):
            compile_multiboard_circuit(raw)

    def test_direct_mate_executes_same_physics_and_negative_r_rejected(self):
        raw = fixture()
        harness = raw["assembly"].pop("harnesses")[0]
        raw["assembly"]["connector_mappings"] = [{"id": "cable", "kind": "connector-mate", "data": {k: harness[k] for k in ("endpoint_a", "endpoint_b", "pin_map")}}]
        raw["link_models"][0]["kind"] = "mate"
        self.assertEqual(run_multiboard_circuit(raw)["status"], "completed")
        raw["link_models"][0]["pins"][0]["resistance_ohm"] = -1
        with self.assertRaisesRegex(MultiboardCircuitError, "nonnegative"):
            compile_multiboard_circuit(raw)


if __name__ == "__main__":
    unittest.main()
