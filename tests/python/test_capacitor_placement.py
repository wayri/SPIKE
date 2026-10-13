# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SPIKE contributors
"""Independent synthetic network, nodal and resonance-refinement oracles."""
import copy
import json
import math
from pathlib import Path
import unittest

import numpy as np

from python.spike_core.capacitor_placement import (
    REQUEST_CONTRACT, CapacitorPlacementError, evaluate_capacitor_placement,
)


def request():
    frequencies = [100., 1000., 10000.]
    return {"contract": REQUEST_CONTRACT, "board_occurrence_id": "pcb-1",
            "reference_return": {"occurrence_id": "pcb-1", "net": "PGND"},
            "frequencies_hz": frequencies,
            "ports": [{"id": name, "occurrence_id": "pcb-1"} for name in ("source", "load")],
            "z_ohm": [[[[.1, 0], [.1, 0]], [[.1, 0], [.15, 0]]] for _ in frequencies],
            "loads": [{"port_id": "load", "current_a_rms": 1.}],
            "candidates": [{"id": name, "port_id": name, "occurrence_id": "pcb-1",
                            "x_mm": x, "y_mm": 5., "capacitor": {
                                "capacitance_f": .001, "esr_ohm": .01, "esl_h": 1e-9,
                                "voltage_rating_v": 25., "ripple_current_rating_a_rms": 10.}}
                           for name, x in (("source", 0), ("load", 10))],
            "dc_voltage_v": 5., "target_impedance_ohm": .1,
            "frequency_band_hz": [100., 10000.],
            "provenance": {"source_id": "original-two-node-resistor-network", "conditions": "Rground=.1 ohm, Rlink=.05 ohm; synthetic."}}


class CapacitorPlacementTests(unittest.TestCase):
    def reject(self, value, code):
        with self.assertRaises(CapacitorPlacementError) as caught:
            evaluate_capacitor_placement(value)
        self.assertEqual(caught.exception.code, code)

    def test_two_node_series_parallel_circuit_oracle(self):
        value = request()
        before = copy.deepcopy(value)
        result = evaluate_capacitor_placement(value)
        self.assertEqual(value, before)
        for candidate in result["candidates"]:
            self.assertTrue(candidate["eligible"])
            for sample in candidate["samples"]:
                omega = 2*math.pi*sample["frequency_hz"]
                zcap = complex(.01, omega*1e-9-1/(omega*.001))
                expected = .05+1/(10+1/zcap) if candidate["id"] == "source" else 1/(1/.15+1/zcap)
                actual = complex(*sample["load_impedance_ohm"][0])
                self.assertAlmostEqual(abs(actual-expected), 0, delta=1e-15)
                current = (expected-.05)/zcap if candidate["id"] == "source" else expected/zcap
                self.assertAlmostEqual(sample["capacitor_current_a_rms"][0], abs(current), delta=1e-14)
        self.assertEqual(result["ranked_candidate_ids"], ["load", "source"])
        self.assertEqual(result["recommended_candidate_id"], "load")
        self.assertAlmostEqual(result["baseline"]["worst_target_ratio"], 1.5)
        json.dumps(result, allow_nan=False)

    def test_result_snapshot_is_complete_and_isolated_from_input_mutation(self):
        value = request()
        original = copy.deepcopy(value)
        result = evaluate_capacitor_placement(value)
        self.assertEqual(result["request_snapshot"], original)
        value["z_ohm"][0][0][0][0] = 12
        value["loads"][0]["current_a_rms"] = 4000
        value["dc_voltage_v"] = 800
        value["candidates"][0]["capacitor"]["capacitance_f"] = .01
        self.assertEqual(result["request_snapshot"], original)
        result["request_snapshot"]["reference_return"]["net"] = "changed-snapshot"
        self.assertEqual(value["reference_return"]["net"], "PGND")

    def test_complex_nodal_oracle_and_ordered_multiple_loads(self):
        value = request()
        matrices = []
        nodal = []
        for frequency in value["frequencies_hz"]:
            ground = .02+1j*2*math.pi*frequency*1e-6
            link = .03+1j*2*math.pi*frequency*2e-6
            y = np.array([[1/ground+1/link, -1/link], [-1/link, 1/link]])
            nodal.append(y)
            z = np.linalg.inv(y)
            matrices.append([[[float(v.real), float(v.imag)] for v in row] for row in z])
        value["z_ohm"] = matrices
        value["loads"] = [{"port_id": "load", "current_a_rms": 2}, {"port_id": "source", "current_a_rms": 3}]
        result = evaluate_capacitor_placement(value)
        self.assertEqual(result["load_port_ids"], ["load", "source"])
        for candidate in result["candidates"]:
            c = 0 if candidate["id"] == "source" else 1
            for y, sample in zip(nodal, candidate["samples"]):
                omega = 2*math.pi*sample["frequency_hz"]
                zcap = .01+1j*(omega*1e-9-1/(omega*.001))
                terminated = y.copy()
                terminated[c, c] += 1/zcap
                expected = np.linalg.solve(terminated, np.eye(2))
                for position, index in enumerate((1, 0)):
                    actual = complex(*sample["load_impedance_ohm"][position])
                    self.assertAlmostEqual(abs(actual-expected[index, index]), 0, delta=1e-14)

    def test_nonreciprocal_passive_input_preserves_both_transfer_directions(self):
        value = request()
        z = np.array([[1, .3+.2j], [.1-.2j, 2]], dtype=complex)
        value["z_ohm"] = [[[[float(v.real), float(v.imag)] for v in row] for row in z] for _ in value["frequencies_hz"]]
        result = evaluate_capacitor_placement(value)
        self.assertGreater(result["network_diagnostics"]["maximum_reciprocity_residual"], 0)
        for candidate in result["candidates"]:
            index = 0 if candidate["id"] == "source" else 1
            for sample in candidate["samples"]:
                omega = 2*math.pi*sample["frequency_hz"]
                y = np.linalg.inv(z)
                y[index, index] += 1/(.01+1j*(omega*1e-9-1/(omega*.001)))
                expected = np.linalg.inv(y)[1, 1]
                self.assertAlmostEqual(abs(complex(*sample["load_impedance_ohm"][0])-expected), 0, delta=1e-14)

    def test_high_voltage_and_high_ripple_ratings_exclude_candidates(self):
        value = request()
        value["dc_voltage_v"] = 800
        result = evaluate_capacitor_placement(value)
        self.assertIsNone(result["best_candidate_id"])
        for candidate in result["candidates"]:
            self.assertIn("capacitor_voltage_rating", candidate["issues"])
            self.assertGreater(candidate["required_voltage_rating_v"], 800)
        value = request()
        value["dc_voltage_v"] = 3.3
        value["loads"][0]["current_a_rms"] = 4000
        result = evaluate_capacitor_placement(value)
        self.assertIsNone(result["recommended_candidate_id"])
        for candidate in result["candidates"]:
            self.assertIn("capacitor_ripple_current_rating", candidate["issues"])
            self.assertGreater(candidate["maximum_capacitor_current_a_rms"], 10)

    def test_singular_resonance_is_withheld_and_never_ranked(self):
        value = request()
        value["ports"] = value["ports"][1:]
        value["candidates"] = value["candidates"][1:]
        cap = value["candidates"][0]["capacitor"]
        cap.update(esr_ohm=0, esl_h=0)
        value["z_ohm"] = [[[[0, 1/(2*math.pi*f*cap["capacitance_f"])]]] for f in value["frequencies_hz"]]
        result = evaluate_capacitor_placement(value)
        self.assertFalse(result["candidates"][0]["eligible"])
        self.assertIsNone(result["candidates"][0]["worst_target_ratio"])
        self.assertIsNone(result["best_candidate_id"])
        self.assertEqual(result["candidates"][0]["issues"], ["ill_conditioned_shunt_resonance"])

    def test_zero_baseline_does_not_invent_improvement(self):
        value = request()
        value["z_ohm"] = [[[[0, 0], [0, 0]], [[0, 0], [0, 0]]] for _ in value["frequencies_hz"]]
        result = evaluate_capacitor_placement(value)
        self.assertIsNone(result["recommended_candidate_id"])
        self.assertIsNone(result["candidates"][0]["improvement_fraction"])
        self.assertTrue(all(c["eligible"] for c in result["candidates"]))

    def test_mounted_port_nearly_ideal_short_keeps_small_impedance(self):
        value = request()
        value["ports"] = value["ports"][1:]
        value["candidates"] = value["candidates"][1:]
        value["candidates"][0]["capacitor"].update(capacitance_f=1000, esr_ohm=0, esl_h=0)
        value["z_ohm"] = [[[[1e12, 0]]] for _ in value["frequencies_hz"]]
        result = evaluate_capacitor_placement(value)
        actual = complex(*result["candidates"][0]["samples"][-1]["load_impedance_ohm"][0])
        expected = 1/(1e-12+1j*2*math.pi*10000*1000)
        self.assertGreater(abs(actual), 0)
        self.assertAlmostEqual(abs(actual/expected-1), 0, delta=1e-14)

    def test_frequency_refinement_reveals_unsampled_antiresonance(self):
        # Parallel ideal L and lossy series RC. Analytical impedance is evaluated
        # independently on nested frequency sets, including f0=sqrt(1/LC)/2pi.
        value = request()
        value["ports"] = value["ports"][1:]
        value["candidates"] = value["candidates"][1:]
        cap = value["candidates"][0]["capacitor"]
        cap.update(capacitance_f=1e-6, esr_ohm=.01, esl_h=0, voltage_rating_v=1e6, ripple_current_rating_a_rms=1e6)
        f0 = 1/(2*math.pi*math.sqrt(1e-3*1e-6))
        peaks = []
        for fractions in ((.5, 1.5), (.5, .9, 1.1, 1.5), (.5, .9, 1., 1.1, 1.5)):
            fs = [fraction*f0 for fraction in fractions]
            value["frequencies_hz"] = fs
            value["frequency_band_hz"] = [fs[0], fs[-1]]
            value["z_ohm"] = [[[[0, 2*math.pi*f*1e-3]]] for f in fs]
            result = evaluate_capacitor_placement(value)
            actual = result["candidates"][0]["peak_impedance_ohm"]
            expected = max(abs(1/(1/(1j*2*math.pi*f*1e-3)+1/(.01+1/(1j*2*math.pi*f*1e-6)))) for f in fs)
            self.assertAlmostEqual(actual/expected, 1, delta=1e-10)
            peaks.append(actual)
        self.assertGreater(peaks[1], peaks[0])
        self.assertGreater(peaks[2], peaks[1]*100)
        self.assertIsNone(result["recommended_candidate_id"])

    def test_sampled_passivity_and_return_board_admission(self):
        value = request()
        value["z_ohm"][0] = [[[1, 0], [2, 0]], [[2, 0], [1, 0]]]
        self.reject(value, "nonpassive_network")
        value = request()
        value["reference_return"]["occurrence_id"] = "other-board"
        self.reject(value, "return_binding")
        value = request()
        value["candidates"][0]["occurrence_id"] = "other-board"
        self.reject(value, "candidate_binding")

    def test_malformed_units_values_shapes_and_resource_limits(self):
        value = request()
        value["frequencies_hz"] = [10000, 1000, 100]
        self.reject(value, "frequency_order")
        for bad in (float("nan"), float("inf"), True, "1e-3", -1, 10**1000):
            value = request()
            value["candidates"][0]["capacitor"]["capacitance_f"] = bad
            self.reject(value, "invalid_number")
        value = request()
        value["z_ohm"][0][0][0] = [0]
        self.reject(value, "resource_budget")
        value = request()
        value["candidates"] *= 129
        self.reject(value, "resource_budget")
        value = request()
        value["frequency_band_hz"] = [100, 500]
        self.reject(value, "frequency_band")
        value = request()
        value["ports"][1]["id"] = "source"
        self.reject(value, "duplicate_port")

    def test_schema(self):
        import jsonschema
        path = Path(__file__).resolve().parents[2]/"schemas"/"capacitor-placement-request-v1.schema.json"
        schema = json.loads(path.read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(request(), schema)


if __name__ == "__main__":
    unittest.main()
