# SPDX-License-Identifier: Apache-2.0
"""Independent spatial boundary, quadrature and RMS energy/loss witnesses."""
from copy import deepcopy
from hashlib import sha256
import json
import math
import unittest
from unittest.mock import patch

import numpy as np
from scipy.integrate import quad
from scipy.linalg import expm

from python.spike_core import rlgc_line_fields as fields
from python.spike_core.rlgc_line_network import build_rlgc_line_network
from tests.python.test_rlgc_line_network import request as line_request


def pair(value):
    return {"real": float(complex(value).real), "imag": float(complex(value).imag)}


def value(record):
    return complex(record["real"], record["imag"])


def request(frequencies=(1e4, 7e7, 4e8), left=1+.2j, right=.3-.4j, **line_changes):
    line = line_request(frequencies, **line_changes)
    return {"contract": fields.REQUEST_CONTRACT, "line_request": line,
            "excitations": [{"frequency_hz": frequency, "incident_left": pair(left), "incident_right": pair(right)}
                            for frequency in frequencies],
            "probes": [{"id": name, "fractional_position": fraction}
                       for name, fraction in (("left", 0.), ("near-left", .15), ("middle", .5), ("near-right", .85), ("right", 1.))]}


def spatial_oracle(line, sample, excitation):
    """Solve terminal wave conditions in physical V/I, then propagate the state.

    This uses no characteristic impedance, traveling-wave coefficient or
    integrated overlap expression from the production implementation.
    """
    omega = 2 * math.pi * sample["frequency_hz"]
    generator = np.array([[0, sample["resistance_ohm_per_m"] + 1j * omega * line["inductance_h_per_m"]],
                          [sample["conductance_s_per_m"] + 1j * omega * line["capacitance_f_per_m"], 0]])
    length, reference = line["length_m"], line["reference_impedance_ohm"]
    transition = expm(generator * length)
    boundary_system = np.vstack([np.array([1, reference]) @ transition, [1, -reference]])
    rhs = 2 * math.sqrt(reference) * np.array([value(excitation["incident_left"]), value(excitation["incident_right"])])
    right_state = np.linalg.solve(boundary_system, rhs)

    def at_position(position):
        return expm(generator * (length - position)) @ right_state

    return at_position


class RLGCLineFieldsTests(unittest.TestCase):
    def test_fields_storage_loss_and_boundaries_against_spatial_exponential(self):
        req = request(length_m=.7, reference_impedance_ohm=73., inductance_h_per_m=4.2e-7, capacitance_f_per_m=8.1e-11)
        result = fields.run_rlgc_line_fields(req)
        line = req["line_request"]
        for sample, excitation, point in zip(line["samples"], req["excitations"], result["points"]):
            oracle = spatial_oracle(line, sample, excitation)
            for probe in point["probe_values"]:
                voltage, current = oracle(probe["fractional_position"] * line["length_m"])
                np.testing.assert_allclose(value(probe["voltage_v"]), voltage, rtol=1e-12, atol=3e-12)
                np.testing.assert_allclose(value(probe["current_left_to_right_a"]), current, rtol=1e-12, atol=3e-14)
                expected = {"transported_power_w": (voltage * current.conjugate()).real,
                            "electric_energy_j_per_m": .5 * line["capacitance_f_per_m"] * abs(voltage)**2,
                            "magnetic_energy_j_per_m": .5 * line["inductance_h_per_m"] * abs(current)**2,
                            "conductor_loss_w_per_m": sample["resistance_ohm_per_m"] * abs(current)**2,
                            "dielectric_loss_w_per_m": sample["conductance_s_per_m"] * abs(voltage)**2}
                for key, expected_value in expected.items():
                    np.testing.assert_allclose(probe[key], expected_value, rtol=2e-12, atol=1e-21 if "energy" in key else 2e-14)
            for name, position, sign in (("left", 0., 1), ("right", line["length_m"], -1)):
                voltage, current = oracle(position)
                boundary = point["boundary_values"][name]
                np.testing.assert_allclose(value(boundary["voltage_v"]), voltage, rtol=1e-12, atol=3e-12)
                np.testing.assert_allclose(value(boundary["current_into_line_a"]), sign * current, rtol=1e-12, atol=3e-14)
                self.assertAlmostEqual(boundary["input_power_w"], sign * (voltage * current.conjugate()).real, delta=2e-12)

    def test_integrated_ledger_against_independent_spatial_quadrature(self):
        req = request(length_m=1.3, resistance=14., conductance=.006)
        line = req["line_request"]
        result = fields.run_rlgc_line_fields(req)
        for sample, excitation, point in zip(line["samples"], req["excitations"], result["points"]):
            oracle = spatial_oracle(line, sample, excitation)
            conductor = quad(lambda x: sample["resistance_ohm_per_m"] * abs(oracle(x)[1])**2,
                             0, line["length_m"], epsabs=1e-13, epsrel=1e-12)[0]
            dielectric = quad(lambda x: sample["conductance_s_per_m"] * abs(oracle(x)[0])**2,
                              0, line["length_m"], epsabs=1e-13, epsrel=1e-12)[0]
            ledger = point["power_balance"]
            self.assertAlmostEqual(ledger["conductor_loss_w"], conductor, delta=2e-12)
            self.assertAlmostEqual(ledger["dielectric_loss_w"], dielectric, delta=2e-12)
            self.assertAlmostEqual(ledger["net_input_w"], conductor + dielectric, delta=2e-12)
            self.assertEqual(ledger["total_loss_w"], ledger["conductor_loss_w"] + ledger["dielectric_loss_w"])
            self.assertEqual(ledger["residual_w"], ledger["net_input_w"] - ledger["total_loss_w"])

    def test_matched_single_wave_rms_power_and_equal_heat_split(self):
        req = request((1e6, 2e8), left=1+.5j, right=0, resistance=10., conductance=.004, length_m=2.)
        result = fields.run_rlgc_line_fields(req)
        expected_heat = 1.25 * (-math.expm1(-.8))
        for point in result["points"]:
            ledger = point["power_balance"]
            self.assertAlmostEqual(ledger["total_loss_w"], expected_heat, delta=2e-14)
            self.assertAlmostEqual(ledger["conductor_loss_w"], expected_heat / 2, delta=2e-14)
            self.assertAlmostEqual(ledger["dielectric_loss_w"], expected_heat / 2, delta=2e-14)
            self.assertAlmostEqual(point["boundary_values"]["left"]["input_power_w"], 1.25, delta=2e-14)
            self.assertLess(point["boundary_values"]["right"]["input_power_w"], 0)
            for probe in point["probe_values"]:
                position = 2 * probe["fractional_position"]
                expected_power = 1.25 * math.exp(-.4 * position)
                self.assertAlmostEqual(probe["transported_power_w"], expected_power, delta=2e-14)
                self.assertAlmostEqual(probe["total_loss_w_per_m"], .4 * expected_power, delta=2e-14)
                self.assertAlmostEqual(probe["electric_energy_j_per_m"], 2.5e-9 * expected_power, delta=1e-22)
                self.assertAlmostEqual(probe["magnetic_energy_j_per_m"], 2.5e-9 * expected_power, delta=1e-22)

    def test_spatial_loss_quadrature_refines_to_analytic_ledger(self):
        req = request((4e8,), length_m=1.3, resistance=14., conductance=.006)
        line = req["line_request"]
        oracle = spatial_oracle(line, line["samples"][0], req["excitations"][0])
        expected = fields.run_rlgc_line_fields(req)["points"][0]["power_balance"]["total_loss_w"]
        errors = []
        for cells in (64, 128, 256, 512, 1024):
            densities = []
            for position in np.linspace(0, line["length_m"], cells + 1):
                voltage, current = oracle(position)
                densities.append(14 * abs(current)**2 + .006 * abs(voltage)**2)
            integral = line["length_m"] / cells * (.5 * (densities[0] + densities[-1]) + sum(densities[1:-1]))
            errors.append(abs(integral - expected))
        self.assertLess(errors[-1], 2e-7)
        for coarse, fine in zip(errors, errors[1:]):
            self.assertGreater(coarse / fine, 3.9)
            self.assertLess(coarse / fine, 4.1)

    def test_lossless_two_sided_standing_wave_and_exact_zero_heat(self):
        req = request((2e8,), left=1, right=1j, resistance=0., conductance=0., length_m=.75)
        point = fields.run_rlgc_line_fields(req)["points"][0]
        beta = 2 * math.pi * 2e8 * 5e-9
        for probe in point["probe_values"]:
            position = .75 * probe["fractional_position"]
            forward = math.sqrt(50) * np.exp(-1j * beta * position)
            backward = 1j * math.sqrt(50) * np.exp(-1j * beta * (.75 - position))
            np.testing.assert_allclose(value(probe["voltage_v"]), forward + backward, atol=2e-14, rtol=0)
            np.testing.assert_allclose(value(probe["current_left_to_right_a"]), (forward - backward) / 50, atol=5e-16, rtol=0)
            self.assertEqual(probe["total_loss_w_per_m"], 0.)
            self.assertAlmostEqual(probe["transported_power_w"], 0., delta=1e-14)
        for key in ("conductor_loss_w", "dielectric_loss_w", "total_loss_w"):
            self.assertEqual(point["power_balance"][key], 0.)

    def test_relative_excitation_phase_changes_interference_loss(self):
        totals = []
        for right in (1, -1):
            req = request((1e4,), left=1, right=right, resistance=0., conductance=.002)
            point = fields.run_rlgc_line_fields(req)["points"][0]
            oracle = spatial_oracle(req["line_request"], req["line_request"]["samples"][0], req["excitations"][0])
            expected = quad(lambda x: .002 * abs(oracle(x)[0])**2, 0, .4, epsabs=1e-14)[0]
            self.assertAlmostEqual(point["power_balance"]["dielectric_loss_w"], expected, delta=2e-14)
            totals.append(expected)
        self.assertGreater(totals[0], 1000 * totals[1])

    def test_short_antiphase_line_retains_small_positive_dielectric_loss(self):
        req = request((1e8,), left=1, right=-1, resistance=1e-4, conductance=4e-8, length_m=1e-8)
        point = fields.run_rlgc_line_fields(req)["points"][0]
        alpha, beta = 2e-14, 2 * math.pi * 1e8 * 5e-9 * 1e-8
        expected = 4e-8 * 100 * 1e-8 * (alpha**2 + beta**2) / 6
        actual = point["power_balance"]["dielectric_loss_w"]
        self.assertGreater(actual, 0)
        self.assertAlmostEqual(actual / expected, 1., delta=1e-12)

    def test_excitation_scaling_and_probe_refinement_do_not_change_integrals(self):
        req = request((7e7,), left=1+.2j, right=.3-.4j)
        original = fields.run_rlgc_line_fields(req)["points"][0]
        refined = deepcopy(req)
        refined["probes"] += [{"id": f"extra-{i}", "fractional_position": i / 10} for i in range(1, 10)]
        self.assertEqual(fields.run_rlgc_line_fields(refined)["points"][0]["power_balance"], original["power_balance"])
        scaled = deepcopy(req)
        factor = 3 - 4j
        for excitation in scaled["excitations"]:
            for key in ("incident_left", "incident_right"):
                excitation[key] = pair(factor * value(excitation[key]))
        actual = fields.run_rlgc_line_fields(scaled)["points"][0]
        for old, new in zip(original["probe_values"], actual["probe_values"]):
            np.testing.assert_allclose(value(new["voltage_v"]), factor * value(old["voltage_v"]), rtol=2e-14, atol=2e-14)
            for key in ("electric_energy_j_per_m", "magnetic_energy_j_per_m", "conductor_loss_w_per_m", "dielectric_loss_w_per_m"):
                np.testing.assert_allclose(new[key], 25 * old[key], rtol=2e-14, atol=1e-21)
        self.assertAlmostEqual(actual["power_balance"]["total_loss_w"], 25 * original["power_balance"]["total_loss_w"], delta=2e-14)

    def test_zero_drive_and_provenance_snapshot(self):
        req = request((1e6,), left=0, right=0)
        before = deepcopy(req)
        result = fields.run_rlgc_line_fields(req)
        self.assertEqual(set(result), {"contract", "model_status", "production_qualified", "input_digest", "source_request", "network", "points", "diagnostics", "limitations"})
        self.assertEqual(result["contract"], fields.RESULT_CONTRACT)
        self.assertEqual(result["model_status"], "experimental")
        self.assertFalse(result["production_qualified"])
        self.assertEqual(result["source_request"], before)
        self.assertEqual(result["network"], build_rlgc_line_network(req["line_request"])["network"])
        digest = sha256(json.dumps(req, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(result["input_digest"], digest)
        self.assertTrue(all(number == 0 for number in result["points"][0]["power_balance"].values()))
        self.assertEqual(result["diagnostics"], {"sample_count": 1, "probe_count": 5, "maximum_power_balance_residual_w": 0.})
        self.assertEqual(req, before)
        req["excitations"][0]["incident_left"] = pair(1)
        self.assertEqual(result["source_request"], before)
        self.assertNotEqual(fields.run_rlgc_line_fields(req)["input_digest"], digest)

    def test_strict_grid_type_and_probe_admission(self):
        invalid = [request((0.,)), request((1e4, 1e4)), request((2e4, 1e4))]
        for path, replacement in ((["contract"], "wrong"), (["probes"], []), (["probes"], tuple(request()["probes"])),
                                  (["excitations"], []), (["excitations", 0, "frequency_hz"], 1e4+1),
                                  (["excitations", 0, "incident_left", "real"], True),
                                  (["excitations", 0, "incident_left", "imag"], math.inf),
                                  (["probes", 0, "fractional_position"], -.1), (["probes", 0, "fractional_position"], 1.01),
                                  (["probes", 0, "fractional_position"], False), (["probes", 0, "id"], " "),
                                  (["probes", 0, "id"], "x" * 81), (["line_request", "samples"], tuple(request()["line_request"]["samples"]))):
            req = request()
            target = req
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = replacement
            invalid.append(req)
        extra, duplicate = request(), request()
        extra["excitations"][0]["incident_left"]["unit"] = "V"
        duplicate["probes"][1]["id"] = duplicate["probes"][0]["id"]
        invalid.extend([extra, duplicate])
        for req in invalid:
            with self.subTest(req=repr(req)[:100]):
                with self.assertRaises(fields.RLGCLineFieldsError):
                    fields.run_rlgc_line_fields(req)

    def test_resource_preflight_and_cancellation(self):
        req = request(tuple(range(1, 1025)))
        req["probes"] = [{"id": f"p-{i}", "fractional_position": i / 31} for i in range(32)]
        with patch.object(fields, "build_rlgc_line_network") as build:
            with self.assertRaises(fields.RLGCLineFieldsError) as caught:
                fields.run_rlgc_line_fields(req)
            self.assertEqual(caught.exception.code, "RLGC_LINE_FIELDS_RESOURCE_LIMIT")
            build.assert_not_called()
        with self.assertRaises(fields.RLGCLineFieldsError) as caught:
            fields.run_rlgc_line_fields(request(), cancel_check=lambda: True)
        self.assertEqual(caught.exception.code, "RLGC_LINE_FIELDS_CANCELLED")
        with self.assertRaises(fields.RLGCLineFieldsError) as caught:
            fields.run_rlgc_line_fields(request(), cancel_check=lambda: 1 / 0)
        self.assertEqual(caught.exception.code, "RLGC_LINE_FIELDS_CANCEL_CHECK_FAILED")
        calls = 0

        def cancelled():
            nonlocal calls
            calls += 1
            return calls == 20

        with self.assertRaises(fields.RLGCLineFieldsError) as caught:
            fields.run_rlgc_line_fields(request(), cancel_check=cancelled)
        self.assertEqual(caught.exception.code, "RLGC_LINE_FIELDS_CANCELLED")

    def test_numerical_failure_and_invariant_failure_are_not_repaired(self):
        for req in (request((1e308,)), request((1e6,), left=1e308), request((1e6,), left=1e-300, right=0)):
            with self.assertRaises(fields.RLGCLineFieldsError):
                fields.run_rlgc_line_fields(req)
        with patch.object(fields, "_integrated_losses", return_value=(np.float64(100), np.float64(100))):
            with self.assertRaises(fields.RLGCLineFieldsError) as caught:
                fields.run_rlgc_line_fields(request())
            self.assertEqual(caught.exception.code, "RLGC_LINE_FIELDS_NUMERICAL_FAILURE")
        with patch.object(fields.np.linalg, "cond", return_value=1e9):
            with self.assertRaises(fields.RLGCLineFieldsError) as caught:
                fields.run_rlgc_line_fields(request())
            self.assertEqual(caught.exception.code, "RLGC_LINE_FIELDS_ILL_CONDITIONED")


if __name__ == "__main__":
    unittest.main()
