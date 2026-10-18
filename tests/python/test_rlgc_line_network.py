# SPDX-License-Identifier: Apache-2.0
"""Original spatial-exponential, finite-ladder and analytic line witnesses."""
from copy import deepcopy
from hashlib import sha256
import json
import math
import unittest
from unittest.mock import patch

import numpy as np
from scipy.linalg import expm

from python.spike_core import rlgc_line_network as line
from python.spike_core.sparameter_sampling import resample_sparameter_network


def request(frequencies=(0., 1e6, 1e8), resistance=3., conductance=2e-4, **changes):
    result = {"contract": line.REQUEST_CONTRACT, "length_m": .4,
              "reference_impedance_ohm": 50., "inductance_h_per_m": 2.5e-7,
              "capacitance_f_per_m": 1e-10,
              "samples": [{"frequency_hz": f, "resistance_ohm_per_m": resistance,
                           "conductance_s_per_m": conductance} for f in frequencies]}
    result.update(changes)
    return result


def matrices(result):
    return [np.array([[complex(v["real"], v["imag"]) for v in row] for row in sample])
            for sample in result["network"]["s_parameters"]]


def boundary_scattering(chain):
    """Solve two independent unit incident-wave boundary value problems.

    The chain acts on normalized (V,I), with I directed left-to-right;
    right-terminal current into the network consequently has opposite sign.
    This oracle does not use the production scattering conversion formula.
    """
    a, b, c, d = chain.ravel()
    system = np.array([[1, -(a + b)], [-1, -(c + d)]])
    outputs = []
    for incident_left, incident_right in ((1, 0), (0, 1)):
        rhs = np.array([(a - b) * incident_right - incident_left,
                        (c - d) * incident_right - incident_left])
        outputs.append(np.linalg.solve(system, rhs))
    return np.column_stack(outputs)


def normalized_coefficients(req, sample):
    w = 2 * math.pi * sample["frequency_hz"]
    z = complex(sample["resistance_ohm_per_m"], w * req["inductance_h_per_m"])
    y = complex(sample["conductance_s_per_m"], w * req["capacitance_f_per_m"])
    return z * req["length_m"] / req["reference_impedance_ohm"], y * req["length_m"] * req["reference_impedance_ohm"]


class RLGCLineNetworkTests(unittest.TestCase):
    def test_independent_spatial_exponential_and_wave_boundary_solves(self):
        req = request((0., 7e3, 1e6, 8e7, 1.1e9), reference_impedance_ohm=73.,
                      inductance_h_per_m=4.2e-7, capacitance_f_per_m=8.1e-11)
        for i, sample in enumerate(req["samples"]):
            sample["resistance_ohm_per_m"] = .7 + 2.1 * i
            sample["conductance_s_per_m"] = 1e-4 * (i + 1)
        actual = matrices(line.build_rlgc_line_network(req))
        for sample, matrix in zip(req["samples"], actual):
            a, b = normalized_coefficients(req, sample)
            expected = boundary_scattering(expm(np.array([[0, a], [b, 0]])))
            np.testing.assert_allclose(matrix, expected, atol=2e-13, rtol=2e-13)

    def test_symmetric_lumped_ladder_second_order_convergence(self):
        req = request((1.7e8,), resistance=12., conductance=.003,
                      reference_impedance_ohm=65., length_m=.3)
        exact = matrices(line.build_rlgc_line_network(req))[0]
        a, b = normalized_coefficients(req, req["samples"][0])
        errors = []
        for cells in (16, 32, 64, 128, 256):
            series_half = np.array([[1, a / (2 * cells)], [0, 1]], dtype=complex)
            shunt = np.array([[1, 0], [b / cells, 1]], dtype=complex)
            section = series_half @ shunt @ series_half
            approximation = boundary_scattering(np.linalg.matrix_power(section, cells))
            errors.append(float(np.max(np.abs(approximation - exact))))
        self.assertLess(errors[-1], 1.5e-5)
        for coarse, fine in zip(errors, errors[1:]):
            self.assertGreater(coarse / fine, 3.9)
            self.assertLess(coarse / fine, 4.1)

    def test_dc_through_series_and_shunt_limits_are_exactly_real(self):
        for resistance, conductance in ((0., 0.), (125., 0.), (0., .05)):
            with self.subTest(resistance=resistance, conductance=conductance):
                req = request((0.,), resistance, conductance)
                r = resistance * req["length_m"] / req["reference_impedance_ohm"]
                g = conductance * req["length_m"] * req["reference_impedance_ohm"]
                expected = np.array([[(r-g)/(2+r+g), 2/(2+r+g)], [2/(2+r+g), (r-g)/(2+r+g)]])
                actual = matrices(line.build_rlgc_line_network(req))[0]
                np.testing.assert_allclose(actual, expected, atol=1e-16, rtol=0)
                self.assertTrue(np.all(actual.imag == 0))

    def test_matched_lossless_delay_and_power_conservation(self):
        req = request((0., 1e6, 1e8, 9e8), 0., 0., length_m=1.2)
        delay = req["length_m"] * math.sqrt(req["inductance_h_per_m"] * req["capacitance_f_per_m"])
        for sample, matrix in zip(req["samples"], matrices(line.build_rlgc_line_network(req))):
            phase = np.exp(-2j * math.pi * sample["frequency_hz"] * delay)
            np.testing.assert_allclose(matrix, [[0, phase], [phase, 0]], atol=1e-14, rtol=0)
            np.testing.assert_allclose(matrix.conj().T @ matrix, np.eye(2), atol=1e-14, rtol=0)

    def test_heaviside_distortionless_attenuation_and_delay(self):
        req = request((0., 1e4, 2e8), 10., .004, length_m=2.)
        delay = req["length_m"] * math.sqrt(req["inductance_h_per_m"] * req["capacitance_f_per_m"])
        attenuation = req["length_m"] * math.sqrt(10. * .004)
        for sample, matrix in zip(req["samples"], matrices(line.build_rlgc_line_network(req))):
            transmission = np.exp(-attenuation - 2j * math.pi * sample["frequency_hz"] * delay)
            np.testing.assert_allclose(matrix, [[0, transmission], [transmission, 0]], atol=5e-15, rtol=0)

    def test_port_reversal_reciprocity_passivity_and_length_units(self):
        req = request((0., 1e5, 3e8, 1e9), 40., .005, reference_impedance_ohm=19.)
        scaled = deepcopy(req)
        scaled["length_m"] *= 1000
        for field in ("inductance_h_per_m", "capacitance_f_per_m"):
            scaled[field] /= 1000
        for sample in scaled["samples"]:
            sample["resistance_ohm_per_m"] /= 1000
            sample["conductance_s_per_m"] /= 1000
        for matrix, other in zip(matrices(line.build_rlgc_line_network(req)), matrices(line.build_rlgc_line_network(scaled))):
            np.testing.assert_allclose(matrix, matrix[::-1, ::-1], atol=0, rtol=0)
            np.testing.assert_allclose(matrix, matrix.T, atol=0, rtol=0)
            self.assertLessEqual(np.linalg.svd(matrix, compute_uv=False)[0], 1 + 1e-12)
            np.testing.assert_allclose(matrix, other, atol=2e-14, rtol=2e-14)

    def test_short_line_retains_first_order_reflection(self):
        req = request((1e8,), 100., 0., length_m=1e-14)
        a, b = normalized_coefficients(req, req["samples"][0])
        matrix = matrices(line.build_rlgc_line_network(req))[0]
        self.assertGreater(abs(matrix[0, 0]), 0)
        self.assertAlmostEqual(abs(matrix[0, 0] - (a - b) / 2), 0, delta=1e-27)

    def test_long_loss_retains_tiny_finite_transmission_without_cosh(self):
        req = request((0.,), 15000., 6., length_m=1.)
        matrix = matrices(line.build_rlgc_line_network(req))[0]
        self.assertGreater(matrix[1, 0].real, 0)
        self.assertAlmostEqual(matrix[1, 0].real / math.exp(-300), 1., delta=2e-13)
        self.assertEqual(matrix[0, 0], 0.)

    def test_small_loss_is_retained_at_large_phase(self):
        # Heaviside matched line: alpha=R/Zref=2e-10 Np/m, beta*l=9e5.
        # A direct product of complex roots erases part of alpha by subtraction.
        frequency = 9e5 / (2 * math.pi * 5e-9)
        req = request((frequency,), 1e-8, 4e-12, length_m=1.)
        matrix = matrices(line.build_rlgc_line_network(req))[0]
        self.assertAlmostEqual(abs(matrix[1, 0]), math.exp(-2e-10), delta=2e-15)
        self.assertEqual(matrix[0, 0], 0.)

    def test_contract_digest_snapshot_and_existing_network_consumer(self):
        req = request()
        before = deepcopy(req)
        result = line.build_rlgc_line_network(req)
        self.assertEqual(set(result), {"contract", "model_status", "production_qualified", "input_digest",
                                       "source_request", "network", "diagnostics", "limitations"})
        self.assertEqual(result["contract"], line.RESULT_CONTRACT)
        self.assertEqual(result["model_status"], "experimental")
        self.assertFalse(result["production_qualified"])
        self.assertEqual(result["source_request"], req)
        digest = sha256(json.dumps(req, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(result["input_digest"], digest)
        self.assertEqual(result["network"]["id"], "rlgc-line-" + digest[:20])
        self.assertEqual(result["network"]["port_names"], ["left", "right"])
        self.assertEqual(result["diagnostics"]["sample_count"], len(req["samples"]))
        self.assertLessEqual(result["diagnostics"]["maximum_passivity_excess"], 1e-9)
        self.assertEqual(result["diagnostics"]["maximum_reciprocity_error"], 0.)
        copied = resample_sparameter_network({"contract": "spike/sparameter-resampling-request/v1",
                                              "source": result["network"], "target_frequencies_hz": [0., 1e6, 1e8],
                                              "dc_policy": {"mode": "require_source"}})
        self.assertEqual(copied["derived_network"]["s_parameters"], result["network"]["s_parameters"])
        self.assertEqual(req, before)
        req["samples"][0]["resistance_ohm_per_m"] = 1000
        self.assertEqual(result["source_request"], before)
        self.assertNotEqual(line.build_rlgc_line_network(req)["input_digest"], digest)

    def test_strict_admission_and_frequency_precision(self):
        invalid = []
        for field in ("length_m", "reference_impedance_ohm", "inductance_h_per_m", "capacitance_f_per_m"):
            for value in (0, -1, True, "1", float("nan"), float("inf"), 10**400):
                req = request()
                req[field] = value
                invalid.append(req)
        for field in ("frequency_hz", "resistance_ohm_per_m", "conductance_s_per_m"):
            for value in (-1, False, "0", float("nan"), float("inf"), 10**400):
                req = request()
                req["samples"][0][field] = value
                invalid.append(req)
        invalid.extend([request(samples=[]), request(samples=tuple(request()["samples"])),
                        request((2., 1.)), request((1., 1.)), request((2**53, 2**53+1)),
                        request(extra=1), request(contract="unsupported")])
        extra = request()
        extra["samples"][0]["extra"] = 1
        missing = request()
        del missing["samples"][0]["resistance_ohm_per_m"]
        invalid.extend([extra, missing])
        for req in invalid:
            with self.subTest(req=repr(req)[:120]):
                with self.assertRaises(line.RLGCLineNetworkError):
                    line.build_rlgc_line_network(req)

    def test_callback_cannot_change_frozen_input_mid_sweep(self):
        req = request()
        before = deepcopy(req)
        calls = 0

        def change_original():
            nonlocal calls
            calls += 1
            if calls == 4:
                req["samples"][0]["resistance_ohm_per_m"] = 1000
            return False

        result = line.build_rlgc_line_network(req, cancel_check=change_original)
        expected = line.build_rlgc_line_network(before)
        self.assertEqual(result, expected)
        self.assertNotEqual(req, before)

    def test_sample_bound_and_cancellation(self):
        req = request(range(1024))
        self.assertEqual(line.build_rlgc_line_network(req)["diagnostics"]["sample_count"], 1024)
        with self.assertRaises(line.RLGCLineNetworkError) as caught:
            line.build_rlgc_line_network(request(range(1025)))
        self.assertEqual(caught.exception.code, "RLGC_LINE_NETWORK_RESOURCE_LIMIT")
        calls = 0

        def cancelled():
            nonlocal calls
            calls += 1
            return calls == 5

        with self.assertRaises(line.RLGCLineNetworkError) as caught:
            line.build_rlgc_line_network(request(), cancel_check=cancelled)
        self.assertEqual(caught.exception.code, "RLGC_LINE_NETWORK_CANCELLED")
        with self.assertRaises(line.RLGCLineNetworkError) as caught:
            line.build_rlgc_line_network(request(), cancel_check=lambda: 1 / 0)
        self.assertEqual(caught.exception.code, "RLGC_LINE_NETWORK_CANCEL_CHECK_FAILED")
        with self.assertRaises(line.RLGCLineNetworkError):
            line.build_rlgc_line_network(request(), cancel_check=True)

    def test_representation_overflow_underflow_and_phase_rejections(self):
        invalid = [request((0.,), 20000., 8., length_m=1.),
                   request((1e18,), 0., 0.), request((1e308,), 0., 0.),
                   request((1e-300,), 0., 0., inductance_h_per_m=1e-300),
                   request((1.,), length_m=1e308, reference_impedance_ohm=1e-300)]
        for req in invalid:
            with self.subTest(req=req):
                with self.assertRaises(line.RLGCLineNetworkError) as caught:
                    line.build_rlgc_line_network(req)
                self.assertIn(caught.exception.code, {"RLGC_LINE_NETWORK_NUMERICAL_FAILURE", "RLGC_LINE_NETWORK_REPRESENTATION_LIMIT"})

    def test_invariant_failures_do_not_return_repaired_samples(self):
        for bad in (np.array([[0, 1.1], [1.1, 0]], complex),
                    np.array([[0, .5], [.4, 0]], complex)):
            with patch.object(line, "_sample_matrix", return_value=bad):
                with self.assertRaises(line.RLGCLineNetworkError) as caught:
                    line.build_rlgc_line_network(request())
                self.assertEqual(caught.exception.code, "RLGC_LINE_NETWORK_NUMERICAL_FAILURE")


if __name__ == "__main__":
    unittest.main()
