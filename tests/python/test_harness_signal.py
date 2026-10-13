# SPDX-License-Identifier: Apache-2.0
"""Analytical transmission-line and conductor identity regression fixtures."""
import copy
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
from jsonschema import Draft202012Validator

from python.spike_core.harness import export_harness, validate_harness
from python.spike_core.harness_signal import compile_harness_si, prepare_harness_em, run_harness_si
from python.spike_core.harness_pi import run_harness_pi


def fixture():
    return {"contract": "spike/harness-si-request/v1", "harness": {
        "contract": "spike/harness/v1", "id": "h", "name": "Explicit matched differential loop",
        "connectors": [{"id": c, "pins": [{"id": "1"}, {"id": "2"}]} for c in ("a", "b")],
        "wires": [{"id": w, "role": "signal", "length_mm": 1000,
                   "from": {"connector": "a", "pin": p}, "to": {"connector": "b", "pin": p}}
                  for w, p in (("p", "1"), ("n", "2"))],
        "pairs": [{"id": "pair", "kind": "differential", "wire_ids": ["p", "n"], "twisted": True, "twist_pitch_mm": 20}]},
        "selection": {"pair_id": "pair"}, "provenance": {"source": "Independent lossless analytical loop fixture"},
        "model": {"kind": "rlgc", "coupled": False, "length_m": 1, "resistance_ohm_per_m": 0,
                  "inductance_h_per_m": 1e-6, "capacitance_f_per_m": 100e-12, "loss_tangent": 0,
                  "inductive_coupling": 0, "capacitive_coupling": 0, "reference_impedance_ohm": 100,
                  "frequency_stop_hz": 1e8, "frequency_points": 9}}


class HarnessIntentTests(unittest.TestCase):
    def test_roles_pairs_and_twist_roundtrip_without_mutation(self):
        raw = fixture()["harness"]
        before = copy.deepcopy(raw)
        out = json.loads(export_harness(raw))
        self.assertEqual(raw, before)
        self.assertEqual(out["pairs"], raw["pairs"])
        self.assertEqual(out["wires"], raw["wires"])
        old = copy.deepcopy(raw)
        del old["pairs"]
        for wire in old["wires"]:
            del wire["role"]
        self.assertNotIn("pairs", validate_harness(old))

    def test_invalid_pair_membership_cable_roles_and_twist(self):
        for mode, code in (("missing", "MEMBERSHIP"), ("duplicate", "MEMBERSHIP"),
                           ("split", "CABLE"), ("mixed", "CABLE"), ("role", "ROLE"),
                           ("endpoint", "ENDPOINTS"), ("pitch", "TWIST_METADATA")):
            raw = fixture()["harness"]
            if mode == "missing": raw["pairs"][0]["wire_ids"][1] = "absent"
            if mode == "duplicate": raw["pairs"].append(dict(raw["pairs"][0], id="second"))
            if mode == "split": raw["cables"] = [{"id": "c1", "wire_ids": ["p"]}, {"id": "c2", "wire_ids": ["n"]}]
            if mode == "mixed": raw["cables"] = [{"id": "c1", "wire_ids": ["p"]}]
            if mode == "role": raw["wires"][0]["role"] = "power"
            if mode == "endpoint": raw["wires"][1]["from"] = copy.deepcopy(raw["wires"][0]["from"])
            if mode == "pitch": raw["pairs"][0]["twisted"] = False
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, code): validate_harness(raw)

    def test_return_reference_requires_explicit_return_role(self):
        raw = fixture()["harness"]
        raw["wires"][0]["return_wire_id"] = "n"
        with self.assertRaisesRegex(ValueError, "RETURN_REFERENCE"): validate_harness(raw)
        raw["pairs"] = []
        raw["wires"][1]["role"] = "return"
        self.assertTrue(validate_harness(raw))

    def test_parallel_power_and_return_are_independent_mna_branches(self):
        from tests.python.test_harness_pi import fixture as pi_fixture
        raw = pi_fixture()
        wires = raw["harness"]["wires"]
        wires[0]["role"], wires[1]["role"] = "power", "return"
        wires[0]["return_wire_id"] = "return"
        wires.extend([dict(copy.deepcopy(wires[0]), id="feed2"), dict(copy.deepcopy(wires[1]), id="return2")])
        for c in raw["harness"]["connectors"]:
            for p in c["pins"]: p["max_connections"] = 2
        result = run_harness_pi(raw)
        self.assertEqual(result["status"], "completed")
        self.assertEqual({w["wire_id"] for w in result["wires"]}, {"feed", "feed2", "return", "return2"})
        for w in result["wires"]: self.assertAlmostEqual(w["current_a"], 1, places=10)
        # Two identical branches halve each wire resistance; contacts stay series.
        sink = next(c for c in result["connections"] if c["id"] == "sink")
        self.assertAlmostEqual(sink["voltage_v"], 12 - 2 * (.1/2 + .2/2 + .01 + .02), places=10)
        self.assertAlmostEqual(result["total_wire_loss_w"], .6, places=10)

    def test_explicit_power_subset_of_mixed_harness(self):
        from tests.python.test_harness_pi import fixture as pi_fixture
        raw = pi_fixture()
        wires = raw["harness"]["wires"]
        wires[0].update(role="power", return_wire_id="return")
        wires[1]["role"] = "return"
        wires.extend([dict(copy.deepcopy(wires[0]), id="feed2"), dict(copy.deepcopy(wires[1]), id="return2")])
        for c in raw["harness"]["connectors"]:
            for p in c["pins"]: p["max_connections"] = 2
            if c["id"] != "source":
                c["pins"].extend([{"id": "3", "required": True}, {"id": "4", "required": True}])
        for wire_id, pin in (("data+", "3"), ("data-", "4")):
            wires.append({"id": wire_id, "role": "signal", "from": {"connector": "plug", "pin": pin}, "to": {"connector": "load", "pin": pin}})
        raw["harness"]["pairs"] = [{"id": "data", "kind": "differential", "wire_ids": ["data+", "data-"]}]
        raw["harness"]["cables"] = [{"id": "bundle", "wire_ids": [w["id"] for w in wires]}]
        raw["wire_ids"] = ["feed", "feed2", "return", "return2"]
        original = copy.deepcopy(raw)
        result = run_harness_pi(raw)
        self.assertEqual(raw, original)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["selected_wire_ids"], raw["wire_ids"])
        self.assertEqual(result["excluded_wire_ids"], ["data+", "data-"])
        for wire in result["wires"]: self.assertAlmostEqual(wire["current_a"], 1, places=10)
        self.assertAlmostEqual(result["total_wire_loss_w"], .6, places=10)
        sink = next(c for c in result["connections"] if c["id"] == "sink")
        self.assertAlmostEqual(sink["voltage_v"], 11.64, places=10)
        schema = Path(__file__).resolve().parents[2] / "schemas/harness-pi-result-v1.schema.json"
        Draft202012Validator(json.loads(schema.read_text())).validate(result)
        for ids in ([], ["feed", "feed"], ["absent"], ["feed", "feed2"]):
            raw["wire_ids"] = ids
            with self.subTest(ids=ids), self.assertRaises(ValueError): run_harness_pi(raw)
        del raw["wire_ids"]
        with self.assertRaisesRegex(ValueError, "unresolved"): run_harness_pi(raw)


class HarnessSignalTests(unittest.TestCase):
    def test_lossless_matched_line_independent_delay_oracle(self):
        raw = fixture()
        result = run_harness_si(raw)
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["field_coupling_executed"])
        self.assertFalse(result["production_qualified"])
        schema = Path(__file__).resolve().parents[2] / "schemas/harness-si-result-v1.schema.json"
        Draft202012Validator(json.loads(schema.read_text())).validate(result)
        s = np.asarray(result["s_real"]) + 1j * np.asarray(result["s_imag"])
        # TEM modal model: Z=sqrt(L/C)=100 ohm, delay=l*sqrt(L*C)=10 ns.
        delay = raw["model"]["length_m"] * math.sqrt(1e-6 * 100e-12)
        expected = np.exp(-2j * np.pi * np.asarray(result["frequency_hz"]) * delay)
        np.testing.assert_allclose(s[:, 1, 0], expected, atol=1e-12)
        np.testing.assert_allclose(s[:, 0, 1], expected, atol=1e-12)
        np.testing.assert_allclose(s[:, 0, 0], 0, atol=1e-12)
        np.testing.assert_allclose(s[:, 1, 1], 0, atol=1e-12)

    def test_reversed_second_wire_preserves_differential_polarity(self):
        raw = fixture()
        w = raw["harness"]["wires"][1]
        w["from"], w["to"] = w["to"], w["from"]
        out = compile_harness_si(raw)
        self.assertEqual(out["wire_ids"], ["p", "n"])
        self.assertEqual(out["port_bindings"][0], {"positive": {"connector": "a", "pin": "1"}, "negative": {"connector": "a", "pin": "2"}})

    def test_result_snapshot_is_independent_of_request(self):
        raw = fixture()
        result = run_harness_si(raw)
        self.assertEqual(result["request_snapshot"], raw)
        raw["harness"]["pairs"][0]["wire_ids"].reverse()
        self.assertEqual(result["request_snapshot"]["harness"]["pairs"][0]["wire_ids"], ["p", "n"])
        result["request_snapshot"]["model"]["length_m"] = 2
        self.assertEqual(raw["model"]["length_m"], 1)

    def test_each_model_field_is_required_and_length_is_bound(self):
        for key in fixture()["model"]:
            raw = fixture()
            del raw["model"][key]
            with self.subTest(key=key), self.assertRaises(ValueError): compile_harness_si(raw)
        raw = fixture()
        raw["model"]["length_m"] = .9
        with self.assertRaisesRegex(ValueError, "SI_LENGTH"): compile_harness_si(raw)

    def test_single_ended_reference_branch_and_budget_rejections(self):
        raw = fixture()
        raw["harness"]["pairs"] = []
        raw["harness"]["wires"][1]["role"] = "return"
        raw["selection"] = {"signal_wire_id": "p", "return_wire_id": "n"}
        self.assertEqual(run_harness_si(raw)["mode"], "single_ended")
        raw["model"]["frequency_points"] = 2050
        with self.assertRaises(ValueError): compile_harness_si(raw)
        raw["model"]["frequency_points"] = 9
        raw["harness"]["wires"].append(dict(copy.deepcopy(raw["harness"]["wires"][0]), id="parallel"))
        for c in raw["harness"]["connectors"]:
            for p in c["pins"]: p["max_connections"] = 2
        with self.assertRaisesRegex(ValueError, "SI_BRANCH"): compile_harness_si(raw)

    def test_em_retains_geometry_but_never_claims_execution(self):
        harness = fixture()["harness"]
        harness["routes"] = [{"id": "r", "frame_id": "assembly", "points_mm": [[0, 0, 0], [500, 0, 0]]}]
        for w in harness["wires"]: w.update(route_id="r", area_mm2=.5)
        request = {"contract": "spike/harness-em-request/v1", "harness": harness, "wire_ids": ["p", "n"]}
        result = prepare_harness_em(request)
        self.assertEqual(result["status"], "unsupported")
        self.assertFalse(result["field_coupling_executed"])
        schema = Path(__file__).resolve().parents[2] / "schemas/harness-em-handoff-v1.schema.json"
        Draft202012Validator(json.loads(schema.read_text())).validate(result)
        self.assertEqual(result["geometry"][0]["route"], harness["routes"][0])
        self.assertEqual(result["pairs"], harness["pairs"])
        self.assertIn("HARNESS_EM_SOLVER_UNAVAILABLE", {i["code"] for i in result["issues"]})
        del harness["wires"][0]["route_id"]
        self.assertIn("HARNESS_EM_GEOMETRY_REQUIRED", {i["code"] for i in prepare_harness_em(request)["issues"]})

    def test_em_shared_route_amplification_rejected_before_output_copy(self):
        harness = fixture()["harness"]
        # One modest input route would expand to 100002 point copies.
        harness["routes"] = [{"id": "r", "frame_id": "assembly", "points_mm": [[i * .001, 0, 0] for i in range(50001)]}]
        for wire in harness["wires"]: wire.update(route_id="r", area_mm2=.5)
        raw = {"contract": "spike/harness-em-request/v1", "harness": harness, "wire_ids": ["p", "n"]}
        # Admission is already covered elsewhere; isolate the output-allocation
        # boundary so deepcopy proves no route copies happen before rejection.
        with patch("python.spike_core.harness_signal._request", return_value=(harness, {"harness_digest": "a" * 64})), \
             patch("python.spike_core.harness_signal.copy.deepcopy") as copier:
            with self.assertRaisesRegex(ValueError, "HARNESS_EM_OUTPUT_LIMIT.*route points"):
                prepare_harness_em(raw)
            copier.assert_not_called()

    def test_em_route_extension_bytes_are_bounded_without_large_point_arrays(self):
        harness = fixture()["harness"]
        harness["routes"] = [{"id": "r", "frame_id": "assembly", "points_mm": [[0, 0, 0], [1, 0, 0]],
                              "extensions": {"vendor": "x" * 10000}}]
        for wire in harness["wires"]: wire.update(route_id="r", area_mm2=.5)
        raw = {"contract": "spike/harness-em-request/v1", "harness": harness, "wire_ids": ["p", "n"]}
        with patch("python.spike_core.harness_signal.MAX_EM_HANDOFF_BYTES", 25000), \
             self.assertRaisesRegex(ValueError, "HARNESS_EM_OUTPUT_LIMIT.*MiB"):
            prepare_harness_em(raw)


if __name__ == "__main__":
    unittest.main()
