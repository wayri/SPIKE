# SPDX-License-Identifier: Apache-2.0
"""Independent physical branched spatial boundary system and heat quadrature."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
import numpy as np
from scipy.linalg import expm
from numpy.polynomial.legendre import leggauss
from examples.rlgc_coupled_star.run_star import request
from python.spike_core import rlgc_coupled_star as star


def value(z): return complex(z["real"], z["imag"])


def physical_oracle(raw, index, incident=None):
    def coefficient(a, b): return np.array([[(a+b)/2, (a-b)/2], [(a-b)/2, (a+b)/2]])
    count = len(raw["legs"]); operators, lengths, coefficients, transfer = [], [], [], []
    omega = 2*np.pi*raw["excitations"][index]["frequency_hz"]
    for leg in raw["legs"]:
        even, odd = (leg["pair"]["modes"][m] for m in ("even", "odd"))
        r, g = (coefficient(even["samples"][index][key], odd["samples"][index][key])
                for key in ("resistance_ohm_per_m", "conductance_s_per_m"))
        l, c = (coefficient(even[key], odd[key]) for key in ("inductance_h_per_m", "capacitance_f_per_m"))
        zero = np.zeros((2, 2))
        operator = np.block([[zero, -(r+1j*omega*l)], [-(g+1j*omega*c), zero]])
        operators.append(operator); lengths.append(even["length_m"]); coefficients.append((r, g)); transfer.append(expm(operator*even["length_m"]))
    reference = raw["legs"][0]["pair"]["modes"]["even"]["reference_impedance_ohm"]
    equations = np.zeros((4*count, 4*count), complex)
    for k in range(count): equations[2*k:2*k+2, 4*k:4*k+4] = np.hstack([np.eye(2), reference*np.eye(2)])
    for k in range(1, count):
        rows = slice(2*count+2*(k-1), 2*count+2*k)
        equations[rows, :4] = -transfer[0][:2]
        equations[rows, 4*k:4*k+4] = transfer[k][:2]
    for k in range(count): equations[-2:, 4*k:4*k+4] = transfer[k][2:]
    if incident is None: incident = np.array([value(v) for v in raw["excitations"][index]["incident_waves"]])
    rhs = np.zeros((4*count, *incident.shape[1:]), complex)
    rhs[:2*count] = 2*np.sqrt(reference)*incident
    states = np.linalg.solve(equations, rhs)
    reflected = np.concatenate([(states[4*k:4*k+2]-reference*states[4*k+2:4*k+4])/(2*np.sqrt(reference)) for k in range(count)])
    return reflected, [states[4*k:4*k+4] for k in range(count)], operators, lengths, coefficients


class CoupledStarTests(unittest.TestCase):
    def test_independent_branched_physical_system_fields_and_heat(self):
        raw = request(); before = deepcopy(raw); out = star.run_rlgc_coupled_star(raw)
        self.assertEqual(raw, before); self.assertEqual(out["source_request"], raw)
        for index, point in enumerate(out["points"]):
            reflected, states, operators, lengths, coefficients = physical_oracle(raw, index)
            matrix = star.pair._decode(out["network"]["s_parameters"][index])
            np.testing.assert_allclose(matrix, physical_oracle(raw, index, np.eye(2*len(raw["legs"])))[0], atol=2e-11, rtol=2e-9)
            incident = np.array([value(v) for v in raw["excitations"][index]["incident_waves"]])
            np.testing.assert_allclose(matrix@incident, reflected, atol=2e-11, rtol=2e-9)
            integrated = np.zeros(2)
            for k, leg in enumerate(out["legs"]):
                child = leg["result"]["points"][index]
                for probe in child["probe_values"]:
                    expected = expm(operators[k]*lengths[k]*probe["fractional_position"])@states[k]
                    actual = [value(t["voltage_v"]) for t in probe["conductors"]]+[value(t["current_left_to_right_a"]) for t in probe["conductors"]]
                    np.testing.assert_allclose(actual, expected, atol=2e-11, rtol=2e-9)
                estimates = []
                for order in (32, 64):
                    nodes, weights = leggauss(order); heat = np.zeros(2)
                    for node, weight in zip(nodes, weights):
                        state = expm(operators[k]*lengths[k]*(node+1)/2)@states[k]
                        heat += weight*lengths[k]/2*np.array([np.vdot(state[2:], coefficients[k][0]@state[2:]).real, np.vdot(state[:2], coefficients[k][1]@state[:2]).real])
                    estimates.append(heat)
                np.testing.assert_allclose(estimates[0], estimates[1], atol=2e-12, rtol=2e-9)
                np.testing.assert_allclose([child["power_balance"][key] for key in ("conductor_loss_w", "dielectric_loss_w")], heat, atol=2e-12, rtol=2e-9)
                integrated += heat
            np.testing.assert_allclose([point["power_balance"][key] for key in ("conductor_loss_w", "dielectric_loss_w")], integrated, atol=2e-12, rtol=2e-9)
            for junction in point["junctions"]:
                self.assertLess(abs(value(junction["current_residual_a"])), 2e-11)
                self.assertLess(abs(junction["power_residual_w"]), 2e-12)
        json.dumps(out, allow_nan=False); self.assertFalse(out["production_qualified"])

    def test_closed_form_identical_uncoupled_matched_star(self):
        raw = request(); model = deepcopy(raw["legs"][0]["pair"])
        for mode in model["modes"].values():
            mode.update(inductance_h_per_m=250e-9, capacitance_f_per_m=100e-12)
            for s in mode["samples"]: s.update(resistance_ohm_per_m=0., conductance_s_per_m=0.)
        for leg in raw["legs"]: leg["pair"] = deepcopy(model)
        out = star.run_rlgc_coupled_star(raw)
        for k, matrix in enumerate(out["network"]["s_parameters"]):
            phase = np.exp(-2j*2*np.pi*raw["excitations"][k]["frequency_hz"]*.08*np.sqrt(250e-9*100e-12))
            expected = phase*np.kron(2/3*np.ones((3, 3))-np.eye(3), np.eye(2))
            np.testing.assert_allclose(star.pair._decode(matrix), expected, atol=2e-11, rtol=2e-9)
            self.assertEqual(out["points"][k]["power_balance"]["total_loss_w"], 0.)

    def test_two_leg_equivalence_to_cascade(self):
        raw = request(); raw["legs"] = raw["legs"][:2]
        for e in raw["excitations"]: e["incident_waves"] = e["incident_waves"][:4]
        actual = star.run_rlgc_coupled_star(raw)
        expected = star.cascade.run_rlgc_coupled_cascade({"contract": star.cascade.REQUEST, "sections": raw["legs"], "excitations": raw["excitations"]})
        for a, b in zip(actual["network"]["s_parameters"], expected["network"]["s_parameters"]):
            np.testing.assert_allclose(star.pair._decode(a), star.pair._decode(b), atol=2e-11, rtol=2e-9)
        for a, b in zip(actual["points"], expected["points"]):
            self.assertAlmostEqual(a["power_balance"]["total_loss_w"], b["power_balance"]["total_loss_w"], delta=2e-12)

    def test_zero_scaling_and_leg_conductor_permutation(self):
        raw = request(); base = star.run_rlgc_coupled_star(raw)
        for factor in (0, -2):
            changed = deepcopy(raw)
            for e in changed["excitations"]:
                for z in e["incident_waves"]: z.update(real=factor*z["real"], imag=factor*z["imag"])
            actual = star.run_rlgc_coupled_star(changed)
            for a, b in zip(base["points"], actual["points"]):
                self.assertAlmostEqual(b["power_balance"]["total_loss_w"], factor**2*a["power_balance"]["total_loss_w"], delta=2e-12)
        for permutation, legs in (([4, 5, 0, 1, 2, 3], [2, 0, 1]), ([1, 0, 3, 2, 5, 4], None)):
            changed = deepcopy(raw)
            if legs: changed["legs"] = [changed["legs"][k] for k in legs]
            else:
                for leg in changed["legs"]: leg["pair"]["conductor_ids"].reverse()
            for e in changed["excitations"]: e["incident_waves"] = [e["incident_waves"][k] for k in permutation]
            actual = star.run_rlgc_coupled_star(changed)
            for a, b in zip(base["network"]["s_parameters"], actual["network"]["s_parameters"]):
                np.testing.assert_allclose(star.pair._decode(b), star.pair._decode(a)[np.ix_(permutation, permutation)], atol=2e-11, rtol=2e-9)

    def test_collision_free_physical_port_identity(self):
        raw = request(); raw["legs"][0]["id"] = "A:B"; raw["legs"][1]["id"] = "A"
        for leg in raw["legs"]: leg["pair"]["conductor_ids"] = ["C", "B:C"]
        out = star.run_rlgc_coupled_star(raw)
        self.assertEqual(len(set(out["network"]["port_names"])), 6)
        self.assertEqual([json.loads(s) for s in out["network"]["port_names"]], [[leg["id"], name] for leg in raw["legs"] for name in leg["pair"]["conductor_ids"]])

    def test_eight_leg_upper_boundary(self):
        raw = request(); model = raw["legs"][0]
        raw["legs"] = [{**deepcopy(model), "id": str(k)} for k in range(8)]
        for e in raw["excitations"]:
            e["incident_waves"] = [{"real": .01*(k+1), "imag": -.01*k} for k in range(16)]
        out = star.run_rlgc_coupled_star(raw)
        np.testing.assert_allclose(star.pair._decode(out["network"]["s_parameters"][0]), physical_oracle(raw, 0, np.eye(16))[0], atol=2e-11, rtol=2e-9)
        self.assertEqual(len(out["legs"]), 8); self.assertEqual(len(out["network"]["port_names"]), 16)
        raw["legs"].append({**deepcopy(model), "id": "ninth"})
        with self.assertRaises(star.CoupledStarError): star.run_rlgc_coupled_star(raw)

    def test_malformed_resources_condition_and_unrepresentability(self):
        mutations = [lambda r: r.__setitem__("extra", 0), lambda r: r.__setitem__("legs", r["legs"][:1]),
            lambda r: r["legs"][1].__setitem__("id", r["legs"][0]["id"]), lambda r: r["legs"][1]["pair"]["conductor_ids"].reverse(),
            lambda r: r["legs"][0]["pair"].__setitem__("probes", []), lambda r: r["excitations"][0]["incident_waves"].pop(),
            lambda r: r["excitations"][0]["incident_waves"][0].__setitem__("real", True), lambda r: r["excitations"][0].__setitem__("frequency_hz", 1),
            lambda r: [m.__setitem__("reference_impedance_ohm", 75) for m in r["legs"][1]["pair"]["modes"].values()]]
        for mutate in mutations:
            raw = request(); mutate(raw)
            with patch.object(star.cascade.bound, "_bare_network", side_effect=AssertionError("reject before solver")):
                with self.assertRaises(star.CoupledStarError): star.run_rlgc_coupled_star(raw)
        with patch.object(star, "_MAX_BYTES", 100):
            with self.assertRaisesRegex(star.CoupledStarError, "exceeds32MiB"): star.run_rlgc_coupled_star(request())
        with patch.object(star, "_MAX_WORK", 1):
            with self.assertRaisesRegex(star.CoupledStarError, "work exceeds"): star.run_rlgc_coupled_star(request())
        with patch.object(star.cascade.bound, "_bare_network", return_value=[np.eye(4)]*3):
            with self.assertRaisesRegex(star.CoupledStarError, "condition"): star.run_rlgc_coupled_star(request())
        raw = request(); raw["excitations"][0]["incident_waves"][0]["real"] = 1e308
        with self.assertRaises(star.CoupledStarError): star.run_rlgc_coupled_star(raw)

    def test_cancellation_and_child_field_split_identity_forgery(self):
        with self.assertRaisesRegex(star.CoupledStarError, "cancelled"): star.run_rlgc_coupled_star(request(), cancel_check=lambda: True)
        def fail(): raise RuntimeError("callback failed")
        with self.assertRaisesRegex(star.CoupledStarError, "callback failed"): star.run_rlgc_coupled_star(request(), cancel_check=fail)
        original = star.pair.run_rlgc_coupled_pair
        def swap_heat(child):
            h = child["points"][0]["power_balance"]; h["conductor_loss_w"], h["dielectric_loss_w"] = h["dielectric_loss_w"], h["conductor_loss_w"]
        for mutate in (lambda c: c.__setitem__("input_digest", "0"*64), swap_heat,
                       lambda c: c["points"][0]["probe_values"][0]["conductors"][0]["voltage_v"].__setitem__("real", 999)):
            def forged(*a, **kw):
                child = original(*a, **kw); mutate(child); return child
            with patch.object(star.pair, "run_rlgc_coupled_pair", side_effect=forged):
                with self.assertRaises(star.CoupledStarError): star.run_rlgc_coupled_star(request())
        cancelled = False
        def stop(*a, **kw):
            nonlocal cancelled
            child = original(*a, **kw); cancelled = True; return child
        with patch.object(star.pair, "run_rlgc_coupled_pair", side_effect=stop):
            with self.assertRaisesRegex(star.CoupledStarError, "cancelled"): star.run_rlgc_coupled_star(request(), cancel_check=lambda: cancelled)


if __name__ == "__main__": unittest.main()
