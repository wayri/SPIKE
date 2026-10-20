# SPDX-License-Identifier: Apache-2.0
"""Independent physical RLC boundary/PDE, complex power and storage oracles."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
import numpy as np
from scipy.linalg import expm

from examples.rlgc_reactive_pair.run_pair import request
from python.spike_core import rlgc_reactive_pair as reactive


def value(z):
    return complex(z["real"], z["imag"])


def physical_oracle(raw, index):
    e, o = (raw["pair"]["modes"][mode] for mode in ("even", "odd"))
    def coefficient(a, b):
        s, m = a/2+b/2, a/2-b/2
        return np.array([[s, m], [m, s]])
    inductance = coefficient(e["inductance_h_per_m"], o["inductance_h_per_m"])
    capacitance = coefficient(e["capacitance_f_per_m"], o["capacitance_f_per_m"])
    resistance = coefficient(e["samples"][index]["resistance_ohm_per_m"], o["samples"][index]["resistance_ohm_per_m"])
    conductance = coefficient(e["samples"][index]["conductance_s_per_m"], o["samples"][index]["conductance_s_per_m"])
    omega = 2*np.pi*raw["sources"][index]["frequency_hz"]
    zero = np.zeros((2, 2))
    spatial = np.block([[zero, -(resistance+1j*omega*inductance)], [-(conductance+1j*omega*capacitance), zero]])
    terms = sorted(raw["terminations"], key=lambda t: t["port"])
    r, l, c = (np.array([t[key] for t in terms]) for key in ("resistance_ohm", "inductance_h", "capacitance_f"))
    zs, yc = r+1j*omega*l, 1j*omega*c
    left = np.hstack([np.diag(1+zs[:2]*yc[:2]), np.diag(zs[:2])])
    right = np.hstack([np.diag(1+zs[2:]*yc[2:]), -np.diag(zs[2:])])
    full = expm(spatial*e["length_m"])
    source = np.array([value(v) for v in raw["sources"][index]["voltage_v"]])
    initial = np.linalg.solve(np.vstack([left, right@full]), source)
    def state(fraction):
        return expm(spatial*(fraction*e["length_m"]))@initial
    end = state(1)
    voltage, line_current = np.r_[initial[:2], end[:2]], np.r_[initial[2:], -end[2:]]
    source_current = line_current+yc*voltage
    return state, voltage, line_current, source_current


class ReactivePairTests(unittest.TestCase):
    def test_physical_boundary_complex_power_and_storage_oracle(self):
        raw = request(); before = deepcopy(raw); out = reactive.run_rlgc_reactive_pair(raw)
        self.assertEqual(raw, before); self.assertEqual(out["source_request"], raw)
        for index, point in enumerate(out["points"]):
            state, voltage, line_current, source_current = physical_oracle(raw, index)
            source = np.array([value(v) for v in raw["sources"][index]["voltage_v"]])
            for j, term in enumerate(point["terminals"]):
                for key, expected in (("voltage_v", voltage[j]), ("current_into_line_a", line_current[j]), ("source_current_a", source_current[j])):
                    self.assertLessEqual(abs(value(term[key])-expected), 2e-11+2e-9*abs(expected))
                self.assertAlmostEqual(term["resistor_heat_w"], term["resistance_ohm"]*abs(source_current[j])**2, delta=2e-12)
                for key, expected in (("inductor_average_energy_j", .5*term["inductance_h"]*abs(source_current[j])**2),
                                      ("capacitor_average_energy_j", .5*term["capacitance_f"]*abs(voltage[j])**2)):
                    self.assertLessEqual(abs(term[key]-expected), 2e-20+2e-9*abs(expected))
                np.testing.assert_allclose(value(term["source_power_va"]), source[j]*np.conj(source_current[j]), atol=2e-12, rtol=2e-9)
                np.testing.assert_allclose(value(term["line_power_va"]), voltage[j]*np.conj(line_current[j]), atol=2e-12, rtol=2e-9)
            for probe in out["pair_result"]["points"][index]["probe_values"]:
                actual = [value(c["voltage_v"]) for c in probe["conductors"]]+[value(c["current_left_to_right_a"]) for c in probe["conductors"]]
                np.testing.assert_allclose(actual, state(probe["fractional_position"]), atol=2e-11, rtol=2e-9)
        json.dumps(out, allow_nan=False); self.assertFalse(out["production_qualified"])

    def test_independent_lossless_abcd_loaded_transfer(self):
        raw = request(); modes = raw["pair"]["modes"]
        modes["even"]["inductance_h_per_m"] = 250e-9; modes["even"]["capacitance_f_per_m"] = 100e-12
        for sample in modes["even"]["samples"]:
            sample["resistance_ohm_per_m"] = sample["conductance_s_per_m"] = 0
        modes["odd"] = deepcopy(modes["even"])
        for source in raw["sources"]:
            source["voltage_v"] = [{"real": v, "imag": 0.} for v in (1, 0, 0, 0)]
        for point in reactive.run_rlgc_reactive_pair(raw)["points"]:
            w = 2*np.pi*point["frequency_hz"]; left, right = raw["terminations"][0], raw["terminations"][2]
            zl = left["resistance_ohm"]+1j*w*left["inductance_h"]
            yr = 1/(right["resistance_ohm"]+1j*w*right["inductance_h"])+1j*w*right["capacitance_f"]
            theta = w*.08*np.sqrt(250e-9*100e-12)
            a = d = np.cos(theta); b = 50j*np.sin(theta); cc = 1j*np.sin(theta)/50
            expected = 1/((1+zl*1j*w*left["capacitance_f"])*(a+b*yr)+zl*(cc+d*yr))
            np.testing.assert_allclose(value(point["terminals"][2]["voltage_v"]), expected, atol=2e-11, rtol=2e-9)

    def test_zero_lc_reduces_to_resistive_producer(self):
        raw = request()
        for term in raw["terminations"]: term["inductance_h"] = term["capacitance_f"] = 0
        out = reactive.run_rlgc_reactive_pair(raw)
        old = reactive.resistive.run_rlgc_terminated_pair(reactive._adapter(raw))
        for a, b in zip(out["points"], old["points"]):
            for x, y in zip(a["terminals"], b["terminals"]):
                np.testing.assert_allclose(value(x["voltage_v"]), value(y["voltage_v"]), atol=2e-11, rtol=2e-9)
                self.assertAlmostEqual(x["resistor_heat_w"], y["resistor_heat_w"], delta=2e-12)
                self.assertEqual(x["inductor_average_energy_j"], 0); self.assertEqual(x["capacitor_average_energy_j"], 0)

    def test_stored_energy_is_not_heat_and_cap_current_is_distinct(self):
        raw = request()
        for mode in raw["pair"]["modes"].values():
            mode["samples"] = [{"frequency_hz": 1000., "resistance_ohm_per_m": 0., "conductance_s_per_m": 0.}]
        raw["sources"] = [deepcopy(raw["sources"][0])]; raw["sources"][0]["frequency_hz"] = 1000.
        for term in raw["terminations"]: term.update(inductance_h=1e-3, capacitance_f=1e-4)
        point = reactive.run_rlgc_reactive_pair(raw)["points"][0]; budget = point["power_balance"]
        self.assertGreater(budget["terminal_inductor_average_energy_j"], 1e-8)
        self.assertGreater(budget["terminal_capacitor_average_energy_j"], 1e-8)
        self.assertGreater(max(abs(value(t["source_current_a"])-value(t["current_into_line_a"])) for t in point["terminals"]), 1e-4)
        self.assertAlmostEqual(budget["total_heat_w"], sum(t["resistor_heat_w"] for t in point["terminals"]), delta=2e-12)
        self.assertAlmostEqual(value(budget["source_power_va"]).real, budget["total_heat_w"], delta=2e-12)
        self.assertAlmostEqual(value(budget["source_power_va"]).imag-value(budget["line_power_va"]).imag,
                               2*2*np.pi*1000*(budget["terminal_inductor_average_energy_j"]-budget["terminal_capacitor_average_energy_j"]), delta=2e-12)

    def test_order_scaling_zero(self):
        raw = request(); original = reactive.run_rlgc_reactive_pair(raw)
        raw["terminations"].reverse()
        self.assertEqual(original["points"], reactive.run_rlgc_reactive_pair(raw)["points"])
        factor = 2-1j
        for source in raw["sources"]:
            source["voltage_v"] = [{"real": (factor*value(v)).real, "imag": (factor*value(v)).imag} for v in source["voltage_v"]]
        scaled = reactive.run_rlgc_reactive_pair(raw)
        for a, b in zip(original["points"], scaled["points"]):
            for key in ("total_heat_w", "terminal_inductor_average_energy_j", "terminal_capacitor_average_energy_j"):
                self.assertAlmostEqual(b["power_balance"][key], 5*a["power_balance"][key], delta=2e-12)
        for source in raw["sources"]: source["voltage_v"] = [{"real": 0., "imag": 0.} for _ in range(4)]
        for point in reactive.run_rlgc_reactive_pair(raw)["points"]:
            self.assertEqual(point["power_balance"]["total_heat_w"], 0)
            self.assertEqual(point["power_balance"]["terminal_inductor_average_energy_j"], 0)

    def test_invalid_admission_condition_and_resource(self):
        for key, bad in (("inductance_h", -1), ("capacitance_f", True), ("inductance_h", float("inf")), ("capacitance_f", 2), ("resistance_ohm", 0)):
            raw = request(); raw["terminations"][0][key] = bad
            with patch.object(reactive.resistive, "_bare_network") as child:
                with self.assertRaises(reactive.ReactivePairError): reactive.run_rlgc_reactive_pair(raw)
                child.assert_not_called()
        with patch.object(reactive, "_MAX_BYTES", 1), patch.object(reactive.resistive, "_bare_network") as child:
            with self.assertRaises(reactive.ReactivePairError): reactive.run_rlgc_reactive_pair(request())
            child.assert_not_called()
        raw = request()
        for term in raw["terminations"]: term.update(resistance_ohm=1e12, inductance_h=0., capacitance_f=0.)
        for mode in raw["pair"]["modes"].values(): mode["samples"] = [{"frequency_hz": 1e-12, "resistance_ohm_per_m": 0., "conductance_s_per_m": 0.}]
        raw["sources"] = [deepcopy(raw["sources"][0])]; raw["sources"][0]["frequency_hz"] = 1e-12
        with self.assertRaises(reactive.ReactivePairError) as caught: reactive.run_rlgc_reactive_pair(raw)
        self.assertEqual(caught.exception.code, "REACTIVE_PAIR_ILL_CONDITIONED")

    def test_cancellation_and_split_preserving_child_corruption(self):
        with self.assertRaises(reactive.ReactivePairError) as caught: reactive.run_rlgc_reactive_pair(request(), cancel_check=lambda: True)
        self.assertEqual(caught.exception.code, "REACTIVE_PAIR_CANCELLED")
        real = reactive.pair.run_rlgc_coupled_pair
        def corrupt(raw, **kwargs):
            out = real(raw, **kwargs); ledger = out["points"][0]["power_balance"]
            shift = .5*ledger["dielectric_loss_w"]; ledger["conductor_loss_w"] += shift; ledger["dielectric_loss_w"] -= shift
            return out
        with patch.object(reactive.pair, "run_rlgc_coupled_pair", side_effect=corrupt):
            with self.assertRaises(reactive.ReactivePairError) as caught: reactive.run_rlgc_reactive_pair(request())
        self.assertEqual(caught.exception.code, "REACTIVE_PAIR_INVALID_RESULT")

    def test_conductor_permutation_and_reversal(self):
        raw = request(); original = reactive.run_rlgc_reactive_pair(raw)
        for order in ([1, 0, 3, 2], [2, 3, 0, 1]):
            changed = deepcopy(raw)
            for source in changed["sources"]: source["voltage_v"] = [source["voltage_v"][port] for port in order]
            for term in changed["terminations"]: term["port"] = order.index(term["port"])
            result = reactive.run_rlgc_reactive_pair(changed)
            for a, b in zip(original["points"], result["points"]):
                for j, port in enumerate(order):
                    for key in ("voltage_v", "current_into_line_a", "source_current_a", "capacitor_current_a"):
                        np.testing.assert_allclose(value(b["terminals"][j][key]), value(a["terminals"][port][key]), atol=2e-11, rtol=2e-9)
                self.assertAlmostEqual(a["power_balance"]["total_heat_w"], b["power_balance"]["total_heat_w"], delta=2e-12)

    def test_absorbing_source_and_cancellation_after_propagation(self):
        raw = request()
        for mode in raw["pair"]["modes"].values(): mode["samples"] = [{"frequency_hz": 1000., "resistance_ohm_per_m": 0., "conductance_s_per_m": 0.}]
        raw["pair"]["modes"]["odd"] = deepcopy(raw["pair"]["modes"]["even"])
        raw["sources"] = [{"frequency_hz": 1000., "voltage_v": [{"real": v, "imag": 0.} for v in (1, 0, 2, 0)]}]
        for term in raw["terminations"]: term["resistance_ohm"] = 50.
        point = reactive.run_rlgc_reactive_pair(raw)["points"][0]
        self.assertLess(value(point["terminals"][0]["source_power_va"]).real, 0)
        self.assertGreater(value(point["terminals"][2]["source_power_va"]).real, 0)
        real = reactive.resistive._bare_network; cancelled = [False]
        def stop(*args, **kwargs):
            result = real(*args, **kwargs); cancelled[0] = True
            return result
        with patch.object(reactive.resistive, "_bare_network", side_effect=stop):
            with self.assertRaises(reactive.ReactivePairError) as caught:
                reactive.run_rlgc_reactive_pair(request(), cancel_check=lambda: cancelled[0])
        self.assertEqual(caught.exception.code, "REACTIVE_PAIR_CANCELLED")
        def fail(): raise RuntimeError("callback")
        with self.assertRaises(reactive.ReactivePairError) as caught: reactive.run_rlgc_reactive_pair(request(), cancel_check=fail)
        self.assertEqual(caught.exception.code, "REACTIVE_PAIR_CANCEL_CHECK_FAILED")


if __name__ == "__main__":
    unittest.main()
