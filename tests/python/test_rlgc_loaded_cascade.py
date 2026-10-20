# SPDX-License-Identifier: Apache-2.0
"""Physical spatial-chain/RLC endpoint oracle, independent of wave feedback."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
import numpy as np
from scipy.linalg import expm
from numpy.polynomial.legendre import leggauss
from examples.rlgc_loaded_cascade.run_loaded import request
from python.spike_core import rlgc_loaded_cascade as loaded
from tests.python.test_rlgc_coupled_cascade import physical_oracle as wave_oracle, value


def physical_oracle(raw, index):
    # Reuse independent physical self/mutual coefficient assembly, not production
    # modal/wave helpers. Its zero-drive boundary solution is discarded.
    model = {"sections": raw["sections"], "excitations": [{"frequency_hz": s["frequency_hz"]} for s in raw["sources"]]}
    _, _, operators, lengths, coefficients = wave_oracle(model, index, incident=np.zeros(4))
    chain = np.eye(4, dtype=complex)
    for operator, length in zip(operators, lengths): chain = expm(operator*length)@chain
    omega = 2*np.pi*raw["sources"][index]["frequency_hz"]
    terms = sorted(raw["terminations"], key=lambda t: t["port"])
    r, l, c = (np.array([t[key] for t in terms]) for key in ("resistance_ohm", "inductance_h", "capacitance_f"))
    zs, yc = r+1j*omega*l, 1j*omega*c
    left = np.hstack([np.diag(1+zs[:2]*yc[:2]), np.diag(zs[:2])])
    right = np.hstack([np.diag(1+zs[2:]*yc[2:]), -np.diag(zs[2:])])
    source = np.array([value(v) for v in raw["sources"][index]["voltage_v"]])
    initial = np.linalg.solve(np.vstack([left, right@chain]), source)
    states, current = [], initial
    for operator, length in zip(operators, lengths):
        states.append(current.copy()); current = expm(operator*length)@current
    voltage = np.r_[initial[:2], current[:2]]
    line_current = np.r_[initial[2:], -current[2:]]
    return states, operators, lengths, coefficients, voltage, line_current, line_current+yc*voltage


class LoadedCascadeTests(unittest.TestCase):
    def test_physical_chain_endpoints_fields_heat_and_energy(self):
        raw = request(); before = deepcopy(raw); out = loaded.run_rlgc_loaded_cascade(raw)
        self.assertEqual(raw, before); self.assertEqual(out["source_request"], raw)
        for index, point in enumerate(out["points"]):
            states, operators, lengths, coefficients, voltage, current, source_current = physical_oracle(raw, index)
            for j, t in enumerate(point["terminals"]):
                for key, expected in (("voltage_v", voltage[j]), ("current_into_line_a", current[j]), ("source_current_a", source_current[j])):
                    np.testing.assert_allclose(value(t[key]), expected, atol=2e-11, rtol=2e-9)
                np.testing.assert_allclose(t["resistor_heat_w"], t["resistance_ohm"]*abs(source_current[j])**2, atol=2e-12, rtol=2e-9)
                np.testing.assert_allclose(value(t["source_power_va"]), value(raw["sources"][index]["voltage_v"][j])*np.conj(source_current[j]), atol=2e-12, rtol=2e-9)
                np.testing.assert_allclose(value(t["line_power_va"]), voltage[j]*np.conj(current[j]), atol=2e-12, rtol=2e-9)
                for key, expected in (("inductor_average_energy_j", .5*t["inductance_h"]*abs(source_current[j])**2),
                                      ("capacitor_average_energy_j", .5*t["capacitance_f"]*abs(voltage[j])**2)):
                    np.testing.assert_allclose(t[key], expected, atol=2e-20, rtol=2e-9)
            integrated = np.zeros(2)
            for k, section in enumerate(out["cascade_result"]["sections"]):
                child = section["result"]["points"][index]
                for probe in child["probe_values"]:
                    expected = expm(operators[k]*lengths[k]*probe["fractional_position"])@states[k]
                    actual = [value(c["voltage_v"]) for c in probe["conductors"]]+[value(c["current_left_to_right_a"]) for c in probe["conductors"]]
                    np.testing.assert_allclose(actual, expected, atol=2e-11, rtol=2e-9)
                estimates = []
                for order in (32, 64):
                    nodes, weights = leggauss(order); heat = np.zeros(2)
                    for node, weight in zip(nodes, weights):
                        state = expm(operators[k]*lengths[k]*(node+1)/2)@states[k]
                        heat += weight*lengths[k]/2*np.array([np.vdot(state[2:], coefficients[k][0]@state[2:]).real,
                                                              np.vdot(state[:2], coefficients[k][1]@state[:2]).real])
                    estimates.append(heat)
                np.testing.assert_allclose(estimates[0], estimates[1], atol=2e-12, rtol=2e-9)
                np.testing.assert_allclose([child["power_balance"][key] for key in ("conductor_loss_w", "dielectric_loss_w")], heat, atol=2e-12, rtol=2e-9)
                integrated += heat
            balance = point["power_balance"]
            np.testing.assert_allclose([balance["line_conductor_heat_w"], balance["line_dielectric_heat_w"]], integrated, atol=2e-12, rtol=2e-9)
            self.assertAlmostEqual(balance["total_heat_w"], sum(integrated)+balance["terminal_resistor_heat_w"], delta=2e-12)
        json.dumps(out, allow_nan=False); self.assertFalse(out["production_qualified"])

    def test_single_section_equivalence_to_reactive_pair(self):
        raw = request(); raw["sections"] = raw["sections"][:1]
        expected = loaded.reactive.run_rlgc_reactive_pair(loaded._view(raw))
        out = loaded.run_rlgc_loaded_cascade(raw)
        self.assertEqual(out["points"], expected["points"])
        self.assertEqual(out["cascade_result"]["sections"][0]["result"], expected["pair_result"])

    def test_homogeneous_subdivision_and_physical_resistive_limit(self):
        raw = request(); raw["sections"] = raw["sections"][:1]
        for t in raw["terminations"]: t["inductance_h"] = t["capacitance_f"] = 0
        out = loaded.run_rlgc_loaded_cascade(raw)
        for k, point in enumerate(out["points"]):
            expected = physical_oracle(raw, k)[4]
            np.testing.assert_allclose([value(t["voltage_v"]) for t in point["terminals"]], expected, atol=2e-11, rtol=2e-9)
        split = deepcopy(raw)
        for mode in split["sections"][0]["pair"]["modes"].values(): mode["length_m"] /= 2
        split["sections"].append({**deepcopy(split["sections"][0]), "id": "extra"})
        other = loaded.run_rlgc_loaded_cascade(split)
        for a, b in zip(out["points"], other["points"]):
            np.testing.assert_allclose([value(t["voltage_v"]) for t in a["terminals"]], [value(t["voltage_v"]) for t in b["terminals"]], atol=2e-11, rtol=2e-9)
            self.assertAlmostEqual(a["power_balance"]["total_heat_w"], b["power_balance"]["total_heat_w"], delta=2e-12)

    def test_zero_scaling_record_order_permutation_and_reversal(self):
        raw = request(); base = loaded.run_rlgc_loaded_cascade(raw)
        modified = deepcopy(raw); modified["terminations"].reverse()
        self.assertEqual(loaded.run_rlgc_loaded_cascade(modified)["points"], base["points"])
        for factor in (0, -2):
            modified = deepcopy(raw)
            for s in modified["sources"]:
                for z in s["voltage_v"]: z.update(real=factor*z["real"], imag=factor*z["imag"])
            actual = loaded.run_rlgc_loaded_cascade(modified)
            for a, b in zip(base["points"], actual["points"]):
                self.assertAlmostEqual(b["power_balance"]["total_heat_w"], factor**2*a["power_balance"]["total_heat_w"], delta=2e-12)
        for permutation, reverse in (([1, 0, 3, 2], False), ([2, 3, 0, 1], True)):
            modified = deepcopy(raw)
            if reverse: modified["sections"].reverse()
            else:
                for s in modified["sections"]: s["pair"]["conductor_ids"].reverse()
            for s in modified["sources"]: s["voltage_v"] = [s["voltage_v"][i] for i in permutation]
            modified["terminations"] = [{**raw["terminations"][port], "port": j} for j, port in enumerate(permutation)]
            actual = loaded.run_rlgc_loaded_cascade(modified)
            for a, b in zip(base["points"], actual["points"]):
                for j, port in enumerate(permutation):
                    np.testing.assert_allclose(value(b["terminals"][j]["voltage_v"]), value(a["terminals"][port]["voltage_v"]), atol=2e-11, rtol=2e-9)
                self.assertAlmostEqual(a["power_balance"]["total_heat_w"], b["power_balance"]["total_heat_w"], delta=2e-12)

    def test_large_storage_and_absorbing_source_keep_j_var_w_separate(self):
        raw = request()
        for section in raw["sections"]:
            for mode in section["pair"]["modes"].values(): mode["samples"] = [{"frequency_hz": 1000., "resistance_ohm_per_m": 0., "conductance_s_per_m": 0.}]
            section["pair"]["modes"]["odd"] = deepcopy(section["pair"]["modes"]["even"])
        raw["sources"] = [{"frequency_hz": 1000., "voltage_v": [{"real": v, "imag": 0.} for v in (1, 0, 2, 0)]}]
        for t in raw["terminations"]: t.update(resistance_ohm=50., inductance_h=1e-3, capacitance_f=1e-4)
        point = loaded.run_rlgc_loaded_cascade(raw)["points"][0]; budget = point["power_balance"]
        self.assertGreater(budget["terminal_capacitor_average_energy_j"], 1e-8)
        self.assertAlmostEqual(budget["total_heat_w"], budget["terminal_resistor_heat_w"], delta=2e-12)
        self.assertGreater(max(abs(value(t["source_current_a"])-value(t["current_into_line_a"])) for t in point["terminals"]), 1e-4)
        for t in point["terminals"]:
            self.assertAlmostEqual(t["reactive_exchange_var"], 4*np.pi*1000*(t["inductor_average_energy_j"]-t["capacitor_average_energy_j"]), delta=2e-12)
        for t in raw["terminations"]: t.update(inductance_h=0., capacitance_f=0.)
        self.assertLess(loaded.run_rlgc_loaded_cascade(raw)["points"][0]["terminals"][0]["source_power_va"]["real"], 0)

    def test_admission_resources_condition_and_cancellation(self):
        mutations = [lambda r: r.__setitem__("extra", 1), lambda r: r.__setitem__("sections", []),
            lambda r: r["terminations"][0].__setitem__("inductance_h", -1), lambda r: r["terminations"][0].__setitem__("capacitance_f", True),
            lambda r: r["terminations"][0].__setitem__("resistance_ohm", 0),
            lambda r: r["terminations"][0].__setitem__("port", 1),
            lambda r: r["sections"][1]["pair"]["conductor_ids"].reverse(),
            lambda r: r["sources"][0].__setitem__("frequency_hz", 1),
            lambda r: [mode.__setitem__("reference_impedance_ohm", 75) for mode in r["sections"][1]["pair"]["modes"].values()],
            lambda r: r["sources"][0]["voltage_v"][0].__setitem__("real", float('inf'))]
        for mutate in mutations:
            raw = request(); mutate(raw)
            with patch.object(loaded, "_bare", side_effect=AssertionError("reject before numerical work")):
                with self.assertRaises(loaded.LoadedCascadeError): loaded.run_rlgc_loaded_cascade(raw)
        with patch.object(loaded, "_MAX_BYTES", 10):
            with self.assertRaisesRegex(loaded.LoadedCascadeError, "exceeds32MiB"): loaded.run_rlgc_loaded_cascade(request())
        with patch.object(loaded.cascade, "_MAX_WORK", 1):
            with self.assertRaisesRegex(loaded.LoadedCascadeError, "work exceeds"): loaded.run_rlgc_loaded_cascade(request())
        raw = request()
        for section in raw["sections"]:
            for mode in section["pair"]["modes"].values(): mode["samples"] = [{"frequency_hz": 1e-12, "resistance_ohm_per_m": 0., "conductance_s_per_m": 0.}]
        raw["sources"] = [deepcopy(raw["sources"][0])]; raw["sources"][0]["frequency_hz"] = 1e-12
        for t in raw["terminations"]: t.update(resistance_ohm=1e12, inductance_h=0., capacitance_f=0.)
        with self.assertRaisesRegex(loaded.LoadedCascadeError, "condition"): loaded.run_rlgc_loaded_cascade(raw)
        enormous = request(); enormous["sources"][0]["voltage_v"][0]["real"] = 1e308
        with self.assertRaises(loaded.LoadedCascadeError): loaded.run_rlgc_loaded_cascade(enormous)
        with self.assertRaisesRegex(loaded.LoadedCascadeError, "cancelled"): loaded.run_rlgc_loaded_cascade(request(), cancel_check=lambda: True)
        def fail(): raise RuntimeError("callback failed")
        with self.assertRaisesRegex(loaded.LoadedCascadeError, "callback failed"): loaded.run_rlgc_loaded_cascade(request(), cancel_check=fail)

    def test_child_provenance_network_field_ledger_forgery_and_late_cancellation(self):
        original = loaded.cascade.run_rlgc_coupled_cascade
        def swap_heat(child):
            heat = child["sections"][0]["result"]["points"][0]["power_balance"]
            heat["conductor_loss_w"], heat["dielectric_loss_w"] = heat["dielectric_loss_w"], heat["conductor_loss_w"]
        mutations = [lambda c: c.__setitem__("input_digest", "0"*64),
            lambda c: c["network"]["s_parameters"][0][0][0].__setitem__("real", 123),
            lambda c: c["sections"][0]["result"]["points"][0]["probe_values"][0]["conductors"][0]["voltage_v"].__setitem__("real", 999),
            swap_heat, lambda c: c["points"][0]["power_balance"].__setitem__("conductor_loss_w", 999),
            lambda c: c["points"][0]["junctions"][0].__setitem__("power_residual_w", 1),
            lambda c: c["sections"].reverse()]
        for mutate in mutations:
            def forged(*a, **kw):
                child = original(*a, **kw); mutate(child); return child
            with patch.object(loaded.cascade, "run_rlgc_coupled_cascade", side_effect=forged):
                with self.assertRaises(loaded.LoadedCascadeError): loaded.run_rlgc_loaded_cascade(request())
        cancelled = False
        def stop(*a, **kw):
            nonlocal cancelled
            child = original(*a, **kw); cancelled = True; return child
        with patch.object(loaded.cascade, "run_rlgc_coupled_cascade", side_effect=stop):
            with self.assertRaisesRegex(loaded.LoadedCascadeError, "cancelled"):
                loaded.run_rlgc_loaded_cascade(request(), cancel_check=lambda: cancelled)


if __name__ == "__main__":
    unittest.main()
