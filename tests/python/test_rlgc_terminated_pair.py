# SPDX-License-Identifier: Apache-2.0
"""Independent physical-coordinate Thevenin/PDE and heat-accounting oracles."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import numpy as np
from scipy.linalg import expm

from examples.rlgc_terminated_pair.run_pair import request
from python.spike_core import rlgc_terminated_pair as terminated


def value(z):
    return complex(z["real"], z["imag"])


def physical_oracle(raw, index):
    """Solve physical V/I states with V+RI=Vs at left, V-RI=Vs at right.

    No production wave conversion, feedback matrix or scalar propagation used.
    """
    modes = raw["pair"]["modes"]
    e, o = modes["even"], modes["odd"]
    def coefficient(a, b):
        s, m = a/2+b/2, a/2-b/2
        return np.array([[s, m], [m, s]])
    inductance = coefficient(e["inductance_h_per_m"], o["inductance_h_per_m"])
    capacitance = coefficient(e["capacitance_f_per_m"], o["capacitance_f_per_m"])
    resistance = coefficient(e["samples"][index]["resistance_ohm_per_m"], o["samples"][index]["resistance_ohm_per_m"])
    conductance = coefficient(e["samples"][index]["conductance_s_per_m"], o["samples"][index]["conductance_s_per_m"])
    omega = 2*np.pi*e["samples"][index]["frequency_hz"]
    zero, identity = np.zeros((2, 2)), np.eye(2)
    spatial = np.block([[zero, -(resistance+1j*omega*inductance)], [-(conductance+1j*omega*capacitance), zero]])
    terms = {term["port"]: term["resistance_ohm"] for term in raw["terminations"]}
    left = np.hstack([identity, np.diag([terms[0], terms[1]])])
    right = np.hstack([identity, -np.diag([terms[2], terms[3]])])
    transfer = expm(spatial*e["length_m"])
    source = np.array([value(v) for v in raw["sources"][index]["voltage_v"]])
    initial = np.linalg.solve(np.vstack([left, right@transfer]), source)
    def state(fraction):
        return expm(spatial*(fraction*e["length_m"]))@initial
    def heat(fraction):
        voltage, current = np.split(state(fraction), 2)
        return np.array([np.vdot(current, resistance@current).real, np.vdot(voltage, conductance@voltage).real])
    end = state(1)
    voltage = np.r_[initial[:2], end[:2]]
    inward = np.r_[initial[2:], -end[2:]]
    return state, heat, voltage, inward


class TerminatedPairTests(unittest.TestCase):
    def test_physical_boundary_fields_and_heat_oracle(self):
        raw = request(); before = deepcopy(raw); out = terminated.run_rlgc_terminated_pair(raw)
        self.assertEqual(raw, before); self.assertEqual(out["source_request"], raw)
        for index, point in enumerate(out["points"]):
            state, heat, voltage, current = physical_oracle(raw, index)
            np.testing.assert_allclose([value(t["voltage_v"]) for t in point["terminals"]], voltage, atol=2e-11, rtol=2e-9)
            np.testing.assert_allclose([value(t["current_into_line_a"]) for t in point["terminals"]], current, atol=2e-11, rtol=2e-9)
            child = out["pair_result"]["points"][index]
            for probe in child["probe_values"]:
                actual = [value(c["voltage_v"]) for c in probe["conductors"]]+[value(c["current_left_to_right_a"]) for c in probe["conductors"]]
                np.testing.assert_allclose(actual, state(probe["fractional_position"]), atol=2e-11, rtol=2e-9)
            nodes, weights = np.polynomial.legendre.leggauss(64)
            expected = sum(w*heat((x+1)/2) for x, w in zip(nodes, weights))*.5*raw["pair"]["modes"]["even"]["length_m"]
            budget = point["power_balance"]
            np.testing.assert_allclose([budget["line_conductor_heat_w"], budget["line_dielectric_heat_w"]], expected, atol=2e-12, rtol=2e-9)
            expected_terminal = sum(t["resistance_ohm"]*abs(current[t["port"]])**2 for t in raw["terminations"])
            self.assertAlmostEqual(budget["terminal_resistor_heat_w"], expected_terminal, delta=2e-12)
            self.assertAlmostEqual(budget["source_power_w"], expected_terminal+sum(expected), delta=2e-12)
        json.dumps(out, allow_nan=False); self.assertFalse(out["production_qualified"])

    def test_matched_uncoupled_lossless_divider_and_phase(self):
        raw = request(); modes = raw["pair"]["modes"]
        modes["even"]["inductance_h_per_m"] = 250e-9; modes["even"]["capacitance_f_per_m"] = 100e-12
        for sample in modes["even"]["samples"]:
            sample["resistance_ohm_per_m"] = sample["conductance_s_per_m"] = 0
        modes["odd"] = deepcopy(modes["even"])
        for term in raw["terminations"]: term["resistance_ohm"] = 50.
        for source in raw["sources"]:
            source["voltage_v"] = [{"real": v, "imag": 0} for v in (1, 0, 0, 0)]
        out = terminated.run_rlgc_terminated_pair(raw)
        for point in out["points"]:
            phase = 2*np.pi*point["frequency_hz"]*.08*np.sqrt(250e-9*100e-12)
            self.assertAlmostEqual(abs(value(point["terminals"][0]["voltage_v"])-.5), 0, delta=2e-12)
            self.assertAlmostEqual(abs(value(point["terminals"][2]["voltage_v"])-.5*np.exp(-1j*phase)), 0, delta=2e-12)
            self.assertAlmostEqual(point["power_balance"]["source_power_w"], .01, delta=2e-12)
            self.assertAlmostEqual(point["power_balance"]["terminal_resistor_heat_w"], .01, delta=2e-12)
            self.assertEqual(point["power_balance"]["line_conductor_heat_w"], 0)

    def test_absorbing_source_and_signed_work(self):
        raw = request()
        for mode in raw["pair"]["modes"].values():
            mode["samples"] = [{"frequency_hz": 1000., "resistance_ohm_per_m": 0., "conductance_s_per_m": 0.}]
        raw["pair"]["modes"]["odd"] = deepcopy(raw["pair"]["modes"]["even"])
        raw["sources"] = [{"frequency_hz": 1000., "voltage_v": [{"real": v, "imag": 0.} for v in (1, 0, 2, 0)]}]
        for term in raw["terminations"]: term["resistance_ohm"] = 50.
        point = terminated.run_rlgc_terminated_pair(raw)["points"][0]
        self.assertLess(point["terminals"][0]["source_power_w"], 0)
        self.assertGreater(point["terminals"][2]["source_power_w"], 0)
        self.assertAlmostEqual(point["power_balance"]["source_power_w"], point["power_balance"]["total_heat_w"], delta=2e-12)

    def test_order_scaling_zero_and_probe_independence(self):
        raw = request(); original = terminated.run_rlgc_terminated_pair(raw)
        raw["terminations"].reverse()
        reordered = terminated.run_rlgc_terminated_pair(raw)
        self.assertEqual(original["points"], reordered["points"])
        factor = 2-1j
        for source in raw["sources"]:
            source["voltage_v"] = [{"real": (factor*value(z)).real, "imag": (factor*value(z)).imag} for z in source["voltage_v"]]
        raw["pair"]["probes"] = raw["pair"]["probes"][:1]
        scaled = terminated.run_rlgc_terminated_pair(raw)
        for a, b in zip(original["points"], scaled["points"]):
            self.assertAlmostEqual(b["power_balance"]["total_heat_w"], 5*a["power_balance"]["total_heat_w"], delta=2e-12)
        for source in raw["sources"]:
            source["voltage_v"] = [{"real": 0., "imag": 0.} for _ in range(4)]
        for point in terminated.run_rlgc_terminated_pair(raw)["points"]:
            self.assertTrue(all(v == 0 for v in point["power_balance"].values()))

    def test_invalid_inputs_rejected_before_solves(self):
        for mutate in (lambda r: r["terminations"].pop(), lambda r: r["terminations"][0].__setitem__("resistance_ohm", 0),
                       lambda r: r["terminations"][0].__setitem__("port", True),
                       lambda r: r["terminations"][0].__setitem__("resistance_ohm", float("inf")),
                       lambda r: r["terminations"][0].__setitem__("port", 1),
                       lambda r: r["sources"][0]["voltage_v"].pop(),
                       lambda r: r["sources"][0]["voltage_v"][0].__setitem__("real", False),
                       lambda r: r["sources"][0].__setitem__("frequency_hz", 1),
                       lambda r: r["pair"].__setitem__("extra", 1)):
            raw = request(); mutate(raw)
            with patch.object(terminated, "build_rlgc_line_network") as child:
                with self.assertRaises(terminated.TerminatedPairError): terminated.run_rlgc_terminated_pair(raw)
                child.assert_not_called()

    def test_feedback_condition_and_resource_limits(self):
        raw = request()
        for mode in raw["pair"]["modes"].values():
            mode["samples"] = [{"frequency_hz": 1e-12, "resistance_ohm_per_m": 0., "conductance_s_per_m": 0.}]
        raw["sources"] = [deepcopy(raw["sources"][0])]; raw["sources"][0]["frequency_hz"] = 1e-12
        for term in raw["terminations"]: term["resistance_ohm"] = 1e12
        with self.assertRaises(terminated.TerminatedPairError) as caught:
            terminated.run_rlgc_terminated_pair(raw)
        self.assertEqual(caught.exception.code, "TERMINATED_PAIR_ILL_CONDITIONED")
        with patch.object(terminated, "_MAX_BYTES", 1), patch.object(terminated, "build_rlgc_line_network") as child:
            with self.assertRaises(terminated.TerminatedPairError): terminated.run_rlgc_terminated_pair(request())
            child.assert_not_called()

    def test_cancellation_and_forged_child(self):
        with self.assertRaises(terminated.TerminatedPairError) as caught:
            terminated.run_rlgc_terminated_pair(request(), cancel_check=lambda: True)
        self.assertEqual(caught.exception.code, "TERMINATED_PAIR_CANCELLED")
        real = terminated.pair.run_rlgc_coupled_pair
        for mutate in (lambda r: r.__setitem__("input_digest", "0"*64),
                       lambda r: r["points"][0]["boundary_values"][0]["voltage_v"].__setitem__("real", 100),
                       lambda r: r["points"][0]["power_balance"].__setitem__("total_loss_w", 100)):
            def corrupt(raw, **kwargs):
                result = real(raw, **kwargs); mutate(result)
                return result
            with patch.object(terminated.pair, "run_rlgc_coupled_pair", side_effect=corrupt):
                with self.assertRaises(terminated.TerminatedPairError): terminated.run_rlgc_terminated_pair(request())

    def test_conductor_permutation_and_line_reversal(self):
        raw = request(); original = terminated.run_rlgc_terminated_pair(raw)
        for order, fraction, sign in (([1, 0, 3, 2], .37, 1), ([2, 3, 0, 1], .63, -1)):
            changed = deepcopy(raw)
            for source in changed["sources"]:
                source["voltage_v"] = [source["voltage_v"][port] for port in order]
            for term in changed["terminations"]:
                term["port"] = order.index(term["port"])
            changed["pair"]["probes"] = [{"id": "check", "fractional_position": fraction}]
            out = terminated.run_rlgc_terminated_pair(changed)
            for first, second in zip(original["points"], out["points"]):
                for j, port in enumerate(order):
                    for key in ("voltage_v", "current_into_line_a"):
                        self.assertAlmostEqual(abs(value(second["terminals"][j][key])-value(first["terminals"][port][key])), 0, delta=2e-11)
                self.assertAlmostEqual(first["power_balance"]["total_heat_w"], second["power_balance"]["total_heat_w"], delta=2e-12)
            for first, second in zip(original["pair_result"]["points"], out["pair_result"]["points"]):
                conductors = first["probe_values"][1]["conductors"]
                if order[0] == 1: conductors = conductors[::-1]
                for a, b in zip(conductors, second["probe_values"][0]["conductors"]):
                    self.assertAlmostEqual(abs(value(b["current_left_to_right_a"])-sign*value(a["current_left_to_right_a"])), 0, delta=2e-11)

    def test_cancel_during_bare_network_and_callback_failure(self):
        cancelled = [False]; real = terminated.build_rlgc_line_network
        def stop(raw, **kwargs):
            result = real(raw, **kwargs); cancelled[0] = True
            return result
        with patch.object(terminated, "build_rlgc_line_network", side_effect=stop) as builder:
            with self.assertRaises(terminated.TerminatedPairError) as caught:
                terminated.run_rlgc_terminated_pair(request(), cancel_check=lambda: cancelled[0])
            self.assertEqual(caught.exception.code, "TERMINATED_PAIR_CANCELLED")
            self.assertEqual(builder.call_count, 1)
        def fail():
            raise RuntimeError("callback")
        with self.assertRaises(terminated.TerminatedPairError) as caught:
            terminated.run_rlgc_terminated_pair(request(), cancel_check=fail)
        self.assertEqual(caught.exception.code, "TERMINATED_PAIR_CANCEL_CHECK_FAILED")

    def test_split_preserving_heat_and_interior_field_forgery_rejected(self):
        real = terminated.pair.run_rlgc_coupled_pair
        def shift_split(result):
            ledger = result["points"][0]["power_balance"]
            shift = ledger["dielectric_loss_w"]*.5
            ledger["conductor_loss_w"] += shift; ledger["dielectric_loss_w"] -= shift
        for mutate in (shift_split,
                       lambda r: r["points"][0]["probe_values"][1]["conductors"][0]["voltage_v"].__setitem__("real", 100),
                       lambda r: r["points"][0]["probe_values"][1]["pair"].__setitem__("electric_energy_j_per_m", 100)):
            def corrupt(raw, **kwargs):
                result = real(raw, **kwargs); mutate(result)
                return result
            with patch.object(terminated.pair, "run_rlgc_coupled_pair", side_effect=corrupt):
                with self.assertRaises(terminated.TerminatedPairError) as caught:
                    terminated.run_rlgc_terminated_pair(request())
            self.assertEqual(caught.exception.code, "TERMINATED_PAIR_INVALID_RESULT")


if __name__ == "__main__":
    unittest.main()
