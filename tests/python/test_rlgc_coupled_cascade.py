# SPDX-License-Identifier: Apache-2.0
"""Independent physical spatial chain and heat quadrature for coupled sections."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
import numpy as np
from scipy.linalg import expm
from numpy.polynomial.legendre import leggauss
from examples.rlgc_coupled_cascade.run_cascade import request
from python.spike_core import rlgc_coupled_cascade as cascade


def value(v):
    return complex(v["real"], v["imag"])


def physical_oracle(raw, index, incident=None):
    """Direct self/mutual physical matrices and exterior V +/- ZI equations."""
    def physical(a, b):
        return np.array([[(a+b)/2, (a-b)/2], [(a-b)/2, (a+b)/2]])
    operators, coefficients, lengths = [], [], []
    omega = 2*np.pi*raw["excitations"][index]["frequency_hz"]
    for section in raw["sections"]:
        even, odd = (section["pair"]["modes"][m] for m in ("even", "odd"))
        r = physical(even["samples"][index]["resistance_ohm_per_m"], odd["samples"][index]["resistance_ohm_per_m"])
        g = physical(even["samples"][index]["conductance_s_per_m"], odd["samples"][index]["conductance_s_per_m"])
        l = physical(even["inductance_h_per_m"], odd["inductance_h_per_m"])
        c = physical(even["capacitance_f_per_m"], odd["capacitance_f_per_m"])
        zero = np.zeros((2, 2))
        operators.append(np.block([[zero, -(r+1j*omega*l)], [-(g+1j*omega*c), zero]]))
        coefficients.append((r, g)); lengths.append(even["length_m"])
    chain = np.eye(4, dtype=complex)
    for operator, length in zip(operators, lengths): chain = expm(operator*length)@chain
    reference = raw["sections"][0]["pair"]["modes"]["even"]["reference_impedance_ohm"]
    left = np.hstack([np.eye(2), reference*np.eye(2)])
    right = np.hstack([np.eye(2), -reference*np.eye(2)])
    if incident is None: incident = np.array([value(v) for v in raw["excitations"][index]["incident_waves"]])
    initial = np.linalg.solve(np.vstack([left, right@chain]), 2*np.sqrt(reference)*incident)
    states, current = [], initial
    for operator, length in zip(operators, lengths):
        states.append(current.copy()); current = expm(operator*length)@current
    voltage = np.concatenate([initial[:2], current[:2]], axis=0)
    inward = np.concatenate([initial[2:], -current[2:]], axis=0)
    reflected = (voltage-reference*inward)/(2*np.sqrt(reference))
    return reflected, states, operators, lengths, coefficients


class CoupledCascadeTests(unittest.TestCase):
    def test_physical_spatial_chain_fields_and_individual_heat_quadrature(self):
        raw = request(); before = deepcopy(raw); out = cascade.run_rlgc_coupled_cascade(raw)
        self.assertEqual(raw, before); self.assertEqual(out["source_request"], raw)
        for index, point in enumerate(out["points"]):
            reflected, states, operators, lengths, coefficients = physical_oracle(raw, index)
            incident = np.array([value(v) for v in raw["excitations"][index]["incident_waves"]])
            scattering = cascade.pair._decode(out["network"]["s_parameters"][index])
            np.testing.assert_allclose(scattering@incident, reflected, atol=2e-11, rtol=2e-9)
            expected_s = physical_oracle(raw, index, np.eye(4))[0]
            np.testing.assert_allclose(scattering, expected_s, atol=2e-11, rtol=2e-9)
            total = 0.
            for k, section in enumerate(out["sections"]):
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
                np.testing.assert_allclose([child["power_balance"][key] for key in ("conductor_loss_w", "dielectric_loss_w")], estimates[-1], atol=2e-12, rtol=2e-9)
                total += sum(estimates[-1])
            self.assertAlmostEqual(point["power_balance"]["total_loss_w"], total, delta=2e-12+2e-9*total)
            for junction in point["junctions"]:
                self.assertLess(abs(junction["power_residual_w"]), 2e-12)
        json.dumps(out, allow_nan=False); self.assertFalse(out["production_qualified"])

    def test_single_section_matches_unchanged_pair(self):
        raw = request(); raw["sections"] = raw["sections"][:1]
        expected = cascade.pair.run_rlgc_coupled_pair(cascade._child(raw["sections"][0], raw["excitations"]))
        actual = cascade.run_rlgc_coupled_cascade(raw)
        self.assertEqual(actual["sections"][0]["result"], expected)
        self.assertEqual(actual["network"]["s_parameters"], expected["network"]["s_parameters"])
        self.assertEqual(actual["points"][0]["junctions"], [])

    def test_homogeneous_segmentation(self):
        one = request(); one["sections"] = one["sections"][:1]
        split = deepcopy(one); section = split["sections"][0]
        for mode in section["pair"]["modes"].values(): mode["length_m"] /= 3
        split["sections"] = [{**deepcopy(section), "id": str(k)} for k in range(3)]
        a, b = (cascade.run_rlgc_coupled_cascade(r) for r in (one, split))
        for x, y in zip(a["network"]["s_parameters"], b["network"]["s_parameters"]):
            np.testing.assert_allclose(cascade.pair._decode(x), cascade.pair._decode(y), atol=2e-11, rtol=2e-9)
        for x, y in zip(a["points"], b["points"]):
            for key in ("conductor_loss_w", "dielectric_loss_w"):
                self.assertAlmostEqual(x["power_balance"][key], y["power_balance"][key], delta=2e-12)

    def test_uncoupled_scalar_cascade_reduction(self):
        from python.spike_core.rlgc_line_cascade import run_rlgc_line_cascade
        raw = request()
        for section in raw["sections"]: section["pair"]["modes"]["odd"] = deepcopy(section["pair"]["modes"]["even"])
        out = cascade.run_rlgc_coupled_cascade(raw)
        scalar = {"contract": "spike/rlgc-line-cascade-request/v1", "sections": [
            {"id": s["id"], "line_request": s["pair"]["modes"]["even"], "probes": s["pair"]["probes"]} for s in raw["sections"]],
            "excitations": [{"frequency_hz": e["frequency_hz"], "incident_left": e["incident_waves"][0], "incident_right": e["incident_waves"][2]} for e in raw["excitations"]]}
        expected = run_rlgc_line_cascade(scalar)
        for x, y in zip(out["network"]["s_parameters"], expected["network"]["s_parameters"]):
            matrix = cascade.pair._decode(x)
            np.testing.assert_allclose(matrix[np.ix_([0, 2], [0, 2])], cascade.pair._decode(y), atol=2e-11, rtol=2e-9)
            np.testing.assert_allclose(matrix[np.ix_([0, 2], [1, 3])], 0, atol=2e-11)

    def test_zero_scaling_reversal_and_conductor_permutation(self):
        raw = request(); original = cascade.run_rlgc_coupled_cascade(raw)
        for factor in (0, -2):
            modified = deepcopy(raw)
            for source in modified["excitations"]:
                for v in source["incident_waves"]: v.update(real=factor*v["real"], imag=factor*v["imag"])
            actual = cascade.run_rlgc_coupled_cascade(modified)
            for x, y in zip(original["points"], actual["points"]):
                self.assertAlmostEqual(y["power_balance"]["total_loss_w"], factor**2*x["power_balance"]["total_loss_w"], delta=2e-12)
        for permutation, reverse in (([1, 0, 3, 2], False), ([2, 3, 0, 1], True)):
            modified = deepcopy(raw)
            if reverse: modified["sections"].reverse()
            else:
                for s in modified["sections"]: s["pair"]["conductor_ids"].reverse()
            for e in modified["excitations"]: e["incident_waves"] = [e["incident_waves"][i] for i in permutation]
            actual = cascade.run_rlgc_coupled_cascade(modified)
            for x, y in zip(original["network"]["s_parameters"], actual["network"]["s_parameters"]):
                np.testing.assert_allclose(cascade.pair._decode(y), cascade.pair._decode(x)[np.ix_(permutation, permutation)], atol=2e-11, rtol=2e-9)

    def test_malformed_identity_reference_grid_and_resources(self):
        mutations = [lambda r: r.__setitem__("extra", 1), lambda r: r.__setitem__("sections", []),
            lambda r: r["sections"][1].__setitem__("id", "first"),
            lambda r: r["sections"][1]["pair"]["conductor_ids"].reverse(),
            lambda r: r["excitations"][0]["incident_waves"][0].__setitem__("real", True),
            lambda r: r["sections"][0]["pair"].__setitem__("probes", []),
            lambda r: r["sections"][1]["pair"]["modes"]["even"].__setitem__("reference_impedance_ohm", 75),
            lambda r: r["sections"][1]["pair"]["modes"]["odd"]["samples"][0].__setitem__("frequency_hz", 1),
            lambda r: r["sections"][0]["pair"]["modes"]["even"].__setitem__("length_m", float('inf'))]
        for mutate in mutations:
            raw = request(); mutate(raw)
            with patch.object(cascade.bound, "_bare_network", side_effect=AssertionError("must reject before solve")):
                with self.assertRaises(cascade.CoupledCascadeError): cascade.run_rlgc_coupled_cascade(raw)
        with patch.object(cascade, "_MAX_BYTES", 100):
            with self.assertRaisesRegex(cascade.CoupledCascadeError, "exceeds32MiB"): cascade.run_rlgc_coupled_cascade(request())
        with patch.object(cascade, "_MAX_WORK", 1):
            with self.assertRaisesRegex(cascade.CoupledCascadeError, "work exceeds"): cascade.run_rlgc_coupled_cascade(request())

    def test_singular_connection_and_nonfinite_fail_closed(self):
        connection, injection = cascade._connection(2)
        with self.assertRaisesRegex(cascade.CoupledCascadeError, "condition"):
            cascade._solve([np.eye(4), np.eye(4)], connection, injection)
        with self.assertRaises(cascade.CoupledCascadeError):
            cascade._solve([np.full((4, 4), np.nan), np.eye(4)], connection, injection)

    def test_cancellation_callbacks_and_forged_child(self):
        with self.assertRaisesRegex(cascade.CoupledCascadeError, "cancelled"):
            cascade.run_rlgc_coupled_cascade(request(), cancel_check=lambda: True)
        def fail(): raise RuntimeError("callback failed")
        with self.assertRaisesRegex(cascade.CoupledCascadeError, "callback failed"):
            cascade.run_rlgc_coupled_cascade(request(), cancel_check=fail)
        original = cascade.pair.run_rlgc_coupled_pair
        def swap_heat(child):
            heat = child["points"][0]["power_balance"]
            heat["conductor_loss_w"], heat["dielectric_loss_w"] = heat["dielectric_loss_w"], heat["conductor_loss_w"]
        for mutate in (lambda c: c.__setitem__("input_digest", "0"*64),
                       lambda c: c["points"][0]["probe_values"][0]["conductors"][0]["voltage_v"].__setitem__("real", 999),
                       swap_heat):
            def forged(*args, **kwargs):
                child = original(*args, **kwargs); mutate(child); return child
            with patch.object(cascade.pair, "run_rlgc_coupled_pair", side_effect=forged):
                with self.assertRaises(cascade.CoupledCascadeError): cascade.run_rlgc_coupled_cascade(request())
        cancelled = False
        def finish_then_cancel(*args, **kwargs):
            nonlocal cancelled
            child = original(*args, **kwargs); cancelled = True; return child
        with patch.object(cascade.pair, "run_rlgc_coupled_pair", side_effect=finish_then_cancel):
            with self.assertRaisesRegex(cascade.CoupledCascadeError, "cancelled"):
                cascade.run_rlgc_coupled_cascade(request(), cancel_check=lambda: cancelled)


if __name__ == "__main__":
    unittest.main()
