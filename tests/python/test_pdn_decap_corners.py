# SPDX-License-Identifier: Apache-2.0
"""Original scalar and multiport circuit oracles for supplied decap corners."""
from copy import deepcopy
import math
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core import pdn_decap_corners as corners
from tests.python.test_pdn_network import basic, element, z, PROV


def request():
    base = basic([element("source", "source_output_impedance", positive="V", negative="GND",
                          resistance_ohm=.08, inductance_h=2e-7)], frequencies=[100., 1000., 10000., 100000., 1000000.])
    return {"contract": corners.REQUEST_CONTRACT, "base_request": base,
            "corners": [{"id": "nominal", "bias_voltage_v": 1.2, "temperature_k": 298.15},
                        {"id": "hot-biased", "bias_voltage_v": 3.3, "temperature_k": 358.15}],
            "capacitors": [
                {"id": "bulk", "positive": "V", "negative": "GND", "provenance": dict(PROV), "corners": [
                    {"corner_id": "nominal", "capacitance_f": 10e-6, "esr_ohm": .02, "esl_h": 2e-9},
                    {"corner_id": "hot-biased", "capacitance_f": 4e-6, "esr_ohm": .08, "esl_h": 4e-9}]},
                {"id": "small", "positive": "V", "negative": "GND", "provenance": {"kind": "measured", "source_id": "synthetic-provenance-label"}, "corners": [
                    {"corner_id": "nominal", "capacitance_f": .22e-6, "esr_ohm": 0., "esl_h": 0.},
                    {"corner_id": "hot-biased", "capacitance_f": .1e-6, "esr_ohm": .04, "esl_h": 0.}]}],
            "target_impedance_ohm_by_port": {"load": .1}}


def cap_z(cap, corner_id, omega):
    physical = next(row for row in cap["corners"] if row["corner_id"] == corner_id)
    return physical["esr_ohm"] + 1j * omega * physical["esl_h"] + 1 / (1j * omega * physical["capacitance_f"])


class PdnDecapCornersTests(unittest.TestCase):
    def test_parallel_source_rlc_oracle_and_exact_worst_sample(self):
        req = request()
        before = deepcopy(req)
        out = corners.run_pdn_decap_corners(req)
        self.assertEqual(req, before)
        worst = None
        for row in out["corners"]:
            identity = row["corner"]["id"]
            for i, sample in enumerate(row["samples"]):
                omega = 2 * math.pi * sample["frequency_hz"]
                expected = 1 / (1 / (.08 + 1j * omega * 2e-7) + sum(1 / cap_z(cap, identity, omega) for cap in req["capacitors"]))
                actual = z(row["network_result"], index=i)
                self.assertAlmostEqual(actual.real, expected.real, delta=3e-12)
                self.assertAlmostEqual(actual.imag, expected.imag, delta=3e-12)
                magnitude = sample["impedance_magnitude_ohm_by_port"]["load"]
                self.assertAlmostEqual(magnitude, abs(expected), delta=3e-12)
                ratio = sample["target_ratio_by_port"]["load"]
                self.assertEqual(ratio, magnitude / .1)
                if worst is None or ratio > worst[0]:
                    worst = (ratio, identity, sample["frequency_hz"])
            self.assertEqual(row["generated_request"]["nodes"], req["base_request"]["nodes"])
            self.assertTrue(all(e["type"] == "decap" for e in row["generated_request"]["elements"][1:]))
        self.assertEqual(out["worst_case"]["target_ratio"], worst[0])
        self.assertEqual(out["worst_case"]["corner_id"], worst[1])
        self.assertEqual(out["worst_case"]["frequency_hz"], worst[2])
        self.assertEqual(out["input_digest"], corners._digest(before))
        self.assertEqual(out["model_status"], "experimental")
        self.assertFalse(out["production_qualified"])

    def test_multiport_shared_return_against_direct_nodal_admittance(self):
        req = request()
        sources = [("A", "RET", .2, 1e-7), ("B", "RET", .3, 2e-7), ("RET", "GND", .05, 8e-8)]
        req["base_request"] = basic([element(f"s{i}", "source_output_impedance", positive=a, negative=b,
            resistance_ohm=r, inductance_h=l) for i, (a, b, r, l) in enumerate(sources)], nodes=["A", "B", "RET"],
            ports=[{"id": "a", "mode": "single", "positive": "A", "negative": "GND"},
                   {"id": "b", "mode": "single", "positive": "B", "negative": "GND"},
                   {"id": "diff", "mode": "differential", "positive": "A", "negative": "B"}],
            frequencies=[1000., 100000.])
        req["capacitors"][0].update(positive="A", negative="RET")
        req["capacitors"][1].update(positive="B", negative="GND")
        req["target_impedance_ohm_by_port"] = {"a": .1, "b": .2, "diff": .3}
        out = corners.run_pdn_decap_corners(req)
        nodes = {"A": 0, "B": 1, "RET": 2}
        ports = np.array([[1., 0., 1.], [0., 1., -1.], [0., 0., 0.]])
        for corner in out["corners"]:
            for index, sample in enumerate(corner["samples"]):
                omega = 2 * math.pi * sample["frequency_hz"]
                admittance = np.zeros((3, 3), dtype=complex)

                def branch(a, b, impedance):
                    incidence = np.zeros(3)
                    if a in nodes: incidence[nodes[a]] += 1
                    if b in nodes: incidence[nodes[b]] -= 1
                    admittance[:] += np.outer(incidence, incidence) / impedance

                for a, b, resistance, inductance in sources:
                    branch(a, b, resistance + 1j * omega * inductance)
                for cap in req["capacitors"]:
                    branch(cap["positive"], cap["negative"], cap_z(cap, corner["corner"]["id"], omega))
                expected = ports.T @ np.linalg.solve(admittance, ports)
                actual = [[z(corner["network_result"], row, col, index) for col in range(3)] for row in range(3)]
                np.testing.assert_allclose(actual, expected, rtol=1e-11, atol=1e-12)
                for j, port in enumerate(out["port_ids"]):
                    self.assertAlmostEqual(sample["target_ratio_by_port"][port], abs(expected[j, j]) / req["target_impedance_ohm_by_port"][port], delta=1e-11)

    def test_order_invariance_metadata_mapping_and_collision_avoidance(self):
        req = request()
        req["base_request"]["elements"][0]["id"] = "decap-corner-0"
        req["base_request"]["ports"][0]["id"] = "decap-corner-0-1"
        req["target_impedance_ohm_by_port"] = {"decap-corner-0-1": .1}
        first = corners.run_pdn_decap_corners(req)
        changed = deepcopy(req)
        changed["capacitors"].reverse()
        for cap in changed["capacitors"]:
            cap["corners"].reverse()
        changed["corners"][0].update(bias_voltage_v=7., temperature_k=400.)
        second = corners.run_pdn_decap_corners(changed)
        for left, right in zip(first["corners"], second["corners"]):
            for i in range(5):
                self.assertAlmostEqual(abs(z(left["network_result"], index=i) - z(right["network_result"], index=i)), 0., delta=1e-12)
            mapping = left["element_mapping"]
            self.assertEqual(mapping[0]["element_id"], "decap-corner-0-2")
            self.assertEqual(mapping[1]["provenance"], req["capacitors"][1]["provenance"])
            self.assertEqual(left["generated_input_digest"], corners._digest(left["generated_request"]))
            self.assertEqual(left["network_result"]["diagnostics"]["provenance_counts"]["measured"], 1)
        self.assertNotEqual(first["input_digest"], second["input_digest"])

    def test_target_failure_is_valid_and_target_change_does_not_change_network(self):
        req = request(); req["target_impedance_ohm_by_port"]["load"] = 100.
        good = corners.run_pdn_decap_corners(req)
        self.assertTrue(good["meets_target"])
        req["target_impedance_ohm_by_port"]["load"] = 1e-6
        bad = corners.run_pdn_decap_corners(req)
        self.assertFalse(bad["meets_target"])
        self.assertGreater(bad["worst_case"]["target_ratio"], 1)
        for a, b in zip(good["corners"], bad["corners"]):
            self.assertEqual(a["network_result"], b["network_result"])

    def test_malformed_corner_topology_and_value_admission_before_solves(self):
        mutations = [lambda r: r.update(extra=True), lambda r: r["corners"][1].update(id="nominal"),
            lambda r: r["corners"][0].update(bias_voltage_v=-1.),
            lambda r: r["corners"][0].update(temperature_k=True),
            lambda r: r["capacitors"][1].update(id="bulk"),
            lambda r: r["capacitors"][0].update(negative="V"),
            lambda r: r["capacitors"][0].update(positive="unknown"),
            lambda r: r["capacitors"][0]["corners"][1].update(corner_id="nominal"),
            lambda r: r["capacitors"][0]["corners"][1].update(corner_id="unknown"),
            lambda r: r["capacitors"][0]["corners"][0].update(capacitance_f=0.),
            lambda r: r["capacitors"][0]["corners"][0].update(esr_ohm=True),
            lambda r: r["capacitors"][0]["corners"][0].update(esl_h=-1.),
            lambda r: r["capacitors"][0]["provenance"].update(kind="assumed"),
            lambda r: r.update(target_impedance_ohm_by_port={}),
            lambda r: r["target_impedance_ohm_by_port"].update(load=0.),
            lambda r: r["base_request"].update(load_transient={}),
            lambda r: r["capacitors"][0]["corners"][0].update(esr_ohm=float("inf"))]
        for i, mutate in enumerate(mutations):
            req = request(); mutate(req)
            with self.subTest(case=i), patch.object(corners, "evaluate_pdn_network") as solve:
                with self.assertRaises(corners.PdnDecapCornersError):
                    corners.run_pdn_decap_corners(req)
                solve.assert_not_called()

    def test_resource_preflight_and_aggregate_work_bound(self):
        for constant in ("_MAX_REQUEST_BYTES", "_MAX_RESULT_BYTES", "_MAX_DENSE_WORK"):
            with patch.object(corners, constant, 1), patch.object(corners, "evaluate_pdn_network") as solve:
                with self.assertRaises(corners.PdnDecapCornersError) as caught:
                    corners.run_pdn_decap_corners(request())
                self.assertEqual(caught.exception.code, "PDN_DECAP_CORNERS_RESOURCE_LIMIT")
                solve.assert_not_called()
        req = request()
        req["corners"] = [{"id": str(i), "bias_voltage_v": 1., "temperature_k": 300.} for i in range(8)]
        req["base_request"] = basic([element(str(i), "resistor", positive=f"v{i}", negative="GND", resistance_ohm=1.) for i in range(8)],
            nodes=[f"v{i}" for i in range(8)], ports=[{"id": "load", "mode": "single", "positive": "v0", "negative": "GND"}],
            frequencies=[float(i + 1) for i in range(512)])
        req["capacitors"] = [{"id": f"c{i}", "positive": f"v{i}", "negative": "GND", "provenance": dict(PROV),
            "corners": [{"corner_id": str(j), "capacitance_f": 1e-6, "esr_ohm": .1, "esl_h": 1e-9} for j in range(8)]} for i in range(8)]
        with patch.object(corners, "evaluate_pdn_network") as solve:
            with self.assertRaisesRegex(corners.PdnDecapCornersError, "Aggregate corner dense work"):
                corners.run_pdn_decap_corners(req)
            solve.assert_not_called()

    def test_cancel_numerical_failure_and_nonfinite_ratio_publish_no_partial_result(self):
        real_solve, completed = corners.evaluate_pdn_network, False

        def finish(raw, **kwargs):
            nonlocal completed
            result = real_solve(raw, **kwargs)
            completed = True
            return result

        with patch.object(corners, "evaluate_pdn_network", side_effect=finish):
            with self.assertRaises(corners.PdnDecapCornersError) as caught:
                corners.run_pdn_decap_corners(request(), cancel_check=lambda: completed)
            self.assertEqual(caught.exception.code, "PDN_DECAP_CORNERS_CANCELLED")
        self.assertTrue(completed)
        req = request(); req["base_request"]["nodes"].append("floating")
        with self.assertRaises(corners.PdnDecapCornersError) as caught:
            corners.run_pdn_decap_corners(req)
        self.assertEqual(caught.exception.code, "PDN_DECAP_CORNERS_SINGULAR_NETWORK")
        req = request(); req["target_impedance_ohm_by_port"]["load"] = 5e-324
        with self.assertRaises(corners.PdnDecapCornersError) as caught:
            corners.run_pdn_decap_corners(req)
        self.assertEqual(caught.exception.code, "PDN_DECAP_CORNERS_NUMERICAL_FAILURE")


if __name__ == "__main__":
    unittest.main()
