# SPDX-License-Identifier: Apache-2.0
"""Independent coupled physical-coordinate PDE and conservation oracles."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import numpy as np
from scipy.linalg import expm

from examples.rlgc_coupled_pair.run_pair import request
from python.spike_core import rlgc_coupled_pair as pair


def value(z):
    return complex(z["real"], z["imag"])


def matrix(raw):
    return np.array([[value(z) for z in row] for row in raw])


def physical_oracle(raw, index):
    """Solve z(right)=exp(M*l)z(left) directly for four physical boundary waves.

    No production basis, scalar propagator, fields or network helpers used.
    """
    even, odd = raw["modes"]["even"], raw["modes"]["odd"]
    def coefficients(e, o):
        self_value, mutual = .5*e+.5*o, .5*e-.5*o
        return np.array([[self_value, mutual], [mutual, self_value]])
    inductance = coefficients(even["inductance_h_per_m"], odd["inductance_h_per_m"])
    capacitance = coefficients(even["capacitance_f_per_m"], odd["capacitance_f_per_m"])
    resistance = coefficients(even["samples"][index]["resistance_ohm_per_m"], odd["samples"][index]["resistance_ohm_per_m"])
    conductance = coefficients(even["samples"][index]["conductance_s_per_m"], odd["samples"][index]["conductance_s_per_m"])
    omega = 2*np.pi*even["samples"][index]["frequency_hz"]
    z, y = resistance+1j*omega*inductance, conductance+1j*omega*capacitance
    zero = np.zeros((2, 2)); identity = np.eye(2)
    spatial = np.block([[zero, -z], [-y, zero]])
    root = np.sqrt(even["reference_impedance_ohm"])
    left_in = np.block([[root*identity, zero], [identity/root, zero]])
    left_out = np.block([[root*identity, zero], [-identity/root, zero]])
    right_in = np.block([[zero, root*identity], [zero, -identity/root]])
    right_out = np.block([[zero, root*identity], [zero, identity/root]])
    full = expm(spatial*even["length_m"])
    scattering = np.linalg.solve(right_out-full@left_out, full@left_in-right_in)
    incident = np.array([value(z) for z in raw["excitations"][index]["incident_waves"]])
    initial = (left_in+left_out@scattering)@incident
    def state(fraction):
        return expm(spatial*(fraction*even["length_m"]))@initial
    def densities(fraction):
        voltage, current = np.split(state(fraction), 2)
        return np.array([np.vdot(current, resistance@current).real, np.vdot(voltage, conductance@voltage).real,
                         .5*np.vdot(current, inductance@current).real, .5*np.vdot(voltage, capacitance@voltage).real])
    return scattering, state, densities


class CoupledPairTests(unittest.TestCase):
    def test_direct_coupled_spatial_boundary_and_quadratic_oracles(self):
        raw = request(); before = deepcopy(raw); out = pair.run_rlgc_coupled_pair(raw)
        self.assertEqual(raw, before); self.assertEqual(out["source_request"], raw)
        for k, point in enumerate(out["points"]):
            expected, state, densities = physical_oracle(raw, k)
            np.testing.assert_allclose(matrix(out["network"]["s_parameters"][k]), expected, atol=2e-11, rtol=2e-9)
            for probe in point["probe_values"]:
                actual = [value(c["voltage_v"]) for c in probe["conductors"]]+[value(c["current_left_to_right_a"]) for c in probe["conductors"]]
                np.testing.assert_allclose(actual, state(probe["fractional_position"]), atol=2e-11, rtol=2e-9)
                physical = densities(probe["fractional_position"])
                observed = probe["pair"]
                np.testing.assert_allclose([observed["conductor_loss_w_per_m"], observed["dielectric_loss_w_per_m"],
                    observed["magnetic_energy_j_per_m"], observed["electric_energy_j_per_m"]], physical, atol=2e-12, rtol=2e-9)
            integrated = []
            for count in (32, 64):
                nodes, weights = np.polynomial.legendre.leggauss(count)
                integrated.append(sum(w*densities((x+1)/2)[:2] for x, w in zip(nodes, weights))*.5*raw["modes"]["even"]["length_m"])
            np.testing.assert_allclose(integrated[0], integrated[1], atol=2e-12, rtol=2e-9)
            balance = point["power_balance"]
            np.testing.assert_allclose([balance["conductor_loss_w"], balance["dielectric_loss_w"]], integrated[1], atol=2e-12, rtol=2e-9)
            self.assertLess(abs(balance["residual_w"]), 1e-10)
        self.assertFalse(out["production_qualified"]); json.dumps(out, allow_nan=False)

    def test_lossless_crosstalk_passivity_reciprocity(self):
        raw = request()
        for mode in raw["modes"].values():
            for sample in mode["samples"]:
                sample["resistance_ohm_per_m"] = sample["conductance_s_per_m"] = 0.
        out = pair.run_rlgc_coupled_pair(raw)
        self.assertEqual(out["network"]["port_names"], ["P:left", "N:left", "P:right", "N:right"])
        for k, record in enumerate(out["network"]["s_parameters"]):
            s = matrix(record); expected, _, _ = physical_oracle(raw, k)
            np.testing.assert_allclose(s, expected, atol=2e-11, rtol=2e-9)
            np.testing.assert_allclose(s.conj().T@s, np.eye(4), atol=2e-12)
            np.testing.assert_allclose(s, s.T, atol=2e-12)
            self.assertGreater(abs(s[1, 0]), 1e-5); self.assertGreater(abs(s[3, 0]), 1e-5)
            self.assertEqual(out["points"][k]["power_balance"]["total_loss_w"], 0)

    def test_equal_modes_remove_crosstalk(self):
        raw = request(); raw["modes"]["odd"] = deepcopy(raw["modes"]["even"])
        out = pair.run_rlgc_coupled_pair(raw)
        for record in out["network"]["s_parameters"]:
            s = matrix(record)
            np.testing.assert_allclose(s[np.ix_([0, 2], [1, 3])], 0, atol=2e-16)
            np.testing.assert_allclose(s[np.ix_([1, 3], [0, 2])], 0, atol=2e-16)

    def test_zero_and_pure_modes(self):
        for inactive, waves in (("odd", [1, 1, 0, 0]), ("even", [1, -1, 0, 0]), ("even", [0, 0, 0, 0])):
            raw = request()
            for drive in raw["excitations"]:
                drive["incident_waves"] = [{"real": v, "imag": 0.} for v in waves]
            out = pair.run_rlgc_coupled_pair(raw)
            for point in out["modes"][inactive]["points"]:
                self.assertEqual(point["power_balance"]["total_loss_w"], 0)

    def test_coherent_scaling_and_probe_independent_integrals(self):
        raw = request(); original = pair.run_rlgc_coupled_pair(raw); factor = 2-1j
        for drive in raw["excitations"]:
            drive["incident_waves"] = [{"real": (factor*value(z)).real, "imag": (factor*value(z)).imag} for z in drive["incident_waves"]]
        raw["probes"] = [raw["probes"][1]]
        changed = pair.run_rlgc_coupled_pair(raw)
        for a, b in zip(original["points"], changed["points"]):
            self.assertAlmostEqual(b["power_balance"]["total_loss_w"], 5*a["power_balance"]["total_loss_w"], delta=2e-12)
            for left, right in zip(a["probe_values"][1]["conductors"], b["probe_values"][0]["conductors"]):
                self.assertAlmostEqual(abs(value(right["voltage_v"])-factor*value(left["voltage_v"])), 0, delta=2e-11)

    def test_bad_modal_identity_and_admission(self):
        for mutate in (lambda r: r["modes"]["odd"].__setitem__("length_m", .2),
                       lambda r: r["modes"]["odd"].__setitem__("reference_impedance_ohm", 75),
                       lambda r: r["modes"]["odd"]["samples"][0].__setitem__("frequency_hz", 1),
                       lambda r: r["modes"]["odd"].__setitem__("inductance_h_per_m", True),
                       lambda r: r["modes"]["even"].__setitem__("capacitance_f_per_m", 1),
                       lambda r: r.__setitem__("extra", 1),
                       lambda r: r["excitations"][0]["incident_waves"].pop(),
                       lambda r: r["excitations"][0]["incident_waves"][0].__setitem__("real", float("inf"))):
            raw = request(); mutate(raw)
            with patch.object(pair, "run_rlgc_line_fields") as child:
                with self.assertRaises(pair.CoupledPairError): pair.run_rlgc_coupled_pair(raw)
                child.assert_not_called()

    def test_cancellation_and_resource_preflight(self):
        with patch.object(pair, "run_rlgc_line_fields") as child:
            with self.assertRaises(pair.CoupledPairError): pair.run_rlgc_coupled_pair(request(), cancel_check=lambda: True)
            child.assert_not_called()
        with patch.object(pair, "_MAX_BYTES", 10), patch.object(pair, "run_rlgc_line_fields") as child:
            with self.assertRaises(pair.CoupledPairError): pair.run_rlgc_coupled_pair(request())
            child.assert_not_called()

    def test_forged_child_identity_rejected(self):
        real = pair.run_rlgc_line_fields
        def corrupt(child_request, **kwargs):
            result = real(child_request, **kwargs); result["input_digest"] = "0"*64
            return result
        with patch.object(pair, "run_rlgc_line_fields", side_effect=corrupt):
            with self.assertRaises(pair.CoupledPairError): pair.run_rlgc_coupled_pair(request())

    def test_reversal_and_conductor_permutation(self):
        raw = request(); original = pair.run_rlgc_coupled_pair(raw)
        for order, fraction, current_sign in (([1, 0, 3, 2], .37, 1), ([2, 3, 0, 1], .63, -1)):
            changed = deepcopy(raw)
            for drive in changed["excitations"]:
                drive["incident_waves"] = [drive["incident_waves"][j] for j in order]
            changed["probes"] = [{"id": "test", "fractional_position": fraction}]
            result = pair.run_rlgc_coupled_pair(changed)
            for first, second in zip(original["points"], result["points"]):
                conductors = first["probe_values"][1]["conductors"]
                if order[0] == 1:
                    conductors = conductors[::-1]
                for a, b in zip(conductors, second["probe_values"][0]["conductors"]):
                    self.assertAlmostEqual(abs(value(b["voltage_v"])-value(a["voltage_v"])), 0, delta=2e-11)
                    self.assertAlmostEqual(abs(value(b["current_left_to_right_a"])-current_sign*value(a["current_left_to_right_a"])), 0, delta=2e-11)
                self.assertAlmostEqual(first["power_balance"]["total_loss_w"], second["power_balance"]["total_loss_w"], delta=2e-12)

    def test_cancel_between_modes_and_callback_failure(self):
        real = pair.run_rlgc_line_fields; cancelled = [False]
        def complete_then_cancel(raw, **kwargs):
            result = real(raw, **kwargs); cancelled[0] = True
            return result
        with patch.object(pair, "run_rlgc_line_fields", side_effect=complete_then_cancel) as child:
            with self.assertRaises(pair.CoupledPairError) as caught:
                pair.run_rlgc_coupled_pair(request(), cancel_check=lambda: cancelled[0])
            self.assertEqual(caught.exception.code, "COUPLED_PAIR_CANCELLED"); self.assertEqual(child.call_count, 1)
        def fail():
            raise RuntimeError("callback failure")
        with self.assertRaises(pair.CoupledPairError) as caught:
            pair.run_rlgc_coupled_pair(request(), cancel_check=fail)
        self.assertEqual(caught.exception.code, "COUPLED_PAIR_CANCEL_CHECK_FAILED")

    def test_corrupt_child_coverage_and_qualification_rejected(self):
        real = pair.run_rlgc_line_fields
        for mutate in (lambda r: r["points"].pop(), lambda r: r.__setitem__("production_qualified", True),
                       lambda r: r["points"][0]["probe_values"][0].__setitem__("id", "wrong"),
                       lambda r: r["network"]["s_parameters"][0].pop()):
            def corrupt(raw, **kwargs):
                result = real(raw, **kwargs); mutate(result)
                return result
            with patch.object(pair, "run_rlgc_line_fields", side_effect=corrupt):
                with self.assertRaises(pair.CoupledPairError): pair.run_rlgc_coupled_pair(request())


if __name__ == "__main__":
    unittest.main()
