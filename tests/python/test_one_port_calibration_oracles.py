# SPDX-License-Identifier: Apache-2.0
"""Independent cross-ratio and deterministic nonlinear covariance oracles."""
from copy import deepcopy
from itertools import permutations
from pathlib import Path
import sys
import unittest

import numpy as np

from python.spike_core.solvers.signal_integrity.networks import one_port_calibration as subject


NAMES = ("standard0.reflection", "standard1.reflection", "standard2.reflection",
         "standard0.measured", "standard1.measured", "standard2.measured", "dut.measured")


def ri(z):
    return {"real": float(z.real), "imag": float(z.imag)}


def read_ri(z):
    return complex(z["real"], z["imag"])


def basis(count):
    return [f"f{k}.{name}.{part}" for k in range(count) for name in NAMES
            for part in ("real", "imag")]


def fixture(count=2, reactive=True):
    """Original synthetic error boxes and reactive supplied standard values."""
    frequencies = [7.3e7*(k+1)**2 for k in range(count)]
    known, observed, expected, terms = [], [], [], []
    for k, f in enumerate(frequencies):
        w = 2*np.pi*f
        if reactive:
            gs = [(1-1j*w*65e-15*50)/(1+1j*w*65e-15*50),
                  (1j*w*35e-12-50)/(1j*w*35e-12+50),
                  (49.4+0.3j-50)/(49.4+0.3j+50)]
        else:
            gs = [1+0j, -1+0j, 0j]
        d, t, s = .035+.021j*(k+1), .83-.09j, -.13+.04j*(k+1)
        gd = [.27-.31j, -.43+.22j, 1.3+.11j][k % 3]
        # Forward wave-box synthesis is separate from calibration recovery.
        ms = [d+t*g/(1-s*g) for g in gs+[gd]]
        known.append(gs); observed.append(ms); expected.append(gd); terms.append((d,t,s))
    req = {"contract": "spike/one-port-calibration-request/v1", "id": "independent-case",
           "port_name": "DUT-plane", "reference_impedance_ohm": 50.,
           "frequencies_hz": frequencies,
           "standards": [{"id": f"supplied-{j}", "provenance": "Original synthetic circuit identity",
                          "reflection": [ri(row[j]) for row in known],
                          "measured": [ri(row[j]) for row in observed]} for j in range(3)],
           "dut": {"id": "unknown", "provenance": "Original synthetic error-box ratio",
                   "measured": [ri(row[3]) for row in observed]},
           "covariance": {"basis": basis(count), "matrix": np.zeros((14*count, 14*count)).tolist(),
                          "provenance": "Explicit synthetic joint real covariance"}}
    return req, np.array(expected), terms


def vector(req):
    values = []
    for k in range(len(req["frequencies_hz"])):
        zs = [read_ri(s["reflection"][k]) for s in req["standards"]]
        zs += [read_ri(s["measured"][k]) for s in req["standards"]]
        zs += [read_ri(req["dut"]["measured"][k])]
        values.extend(v for z in zs for v in (z.real, z.imag))
    return np.array(values)


def cross_ratio(x):
    """Homogeneous four-difference identity; no solve or production helper."""
    result = []
    for block in np.asarray(x).reshape(-1, 14):
        g0,g1,g2,m0,m1,m2,md = block[::2]+1j*block[1::2]
        n = (md-m0)*(m1-m2)*(g1-g0)
        h = (md-m2)*(m1-m0)*(g1-g2)
        g = (n*g2-h*g0)/(n-h)
        result.extend((g.real, g.imag))
    return np.array(result)


def finite_jacobian(x):
    delta = 2e-6*np.eye(len(x))
    return np.column_stack([(cross_ratio(x+h)-cross_ratio(x-h))/(4e-6) for h in delta])


def dense_factor(n):
    i, j = np.indices((n, n))
    # Dense deterministic mixed-sign correlations and unequal marginal scales.
    return np.diag(.3+np.arange(n)/n) + .12*np.cos((i+1)*(j+2)) + .07*np.sin(i+2*j)


def output(result):
    return np.array([read_ri(row[0][0]) for row in result["derived_network"]["s_parameters"]])


class IndependentOnePortCalibrationTests(unittest.TestCase):
    def test_reactive_standards_and_active_dut_cross_ratio(self):
        req, expected, terms = fixture(3)
        result = subject.calibrate_one_port(req)
        np.testing.assert_allclose(output(result), expected, rtol=2e-12, atol=2e-12)
        oracle = cross_ratio(vector(req))
        np.testing.assert_allclose(output(result), oracle[::2]+1j*oracle[1::2], rtol=2e-12, atol=2e-12)
        for got, wanted in zip(result["coefficients"], terms):
            np.testing.assert_allclose([read_ri(got[key]) for key in
                                      ("directivity", "reflection_tracking", "source_match")],
                                      wanted, rtol=2e-12, atol=2e-12)
        self.assertGreater(abs(output(result)[2]), 1.)
        self.assertEqual(subject.input_basis(3), basis(3))

    def test_scalar_ideal_open_short_load_coefficients(self):
        req, expected, _ = fixture(1, reactive=False)
        mo, ms, ml = [read_ri(s["measured"][0]) for s in req["standards"]]
        a,c = mo-ml,ms-ml
        wanted = [ml,-2*a*c/(a-c),(a+c)/(a-c)]
        result = subject.calibrate_one_port(req)
        np.testing.assert_allclose([read_ri(result["coefficients"][0][key]) for key in
                                  ("directivity", "reflection_tracking", "source_match")],
                                  wanted, rtol=2e-12, atol=2e-12)
        np.testing.assert_allclose(output(result), expected, rtol=2e-12, atol=2e-12)

    def test_all_real_imaginary_sensitivities_independent_difference(self):
        req, _, _ = fixture(3)
        got = subject.calibrate_one_port(req)
        jac = finite_jacobian(vector(req))
        np.testing.assert_allclose(got["sensitivity"], jac, rtol=2e-7, atol=2e-9)
        for k in range(3):
            self.assertEqual(np.count_nonzero(np.asarray(got["sensitivity"])[2*k:2*k+2, :14*k]), 0)

    def test_dense_joint_covariance_preserves_all_correlations(self):
        req, _, _ = fixture(3)
        factor = 2e-4*dense_factor(42)
        cov = factor@factor.T
        req["covariance"]["matrix"] = cov.tolist()
        got = subject.calibrate_one_port(req)
        jac = finite_jacobian(vector(req))
        expected = jac@cov@jac.T
        np.testing.assert_allclose(got["covariance"], expected, rtol=5e-7, atol=2e-16)
        self.assertGreater(np.linalg.norm(expected[:2, 2:]), 1e-9)
        independent = jac@np.diag(np.diag(cov))@jac.T
        self.assertGreater(np.linalg.norm(expected-independent)/np.linalg.norm(expected), .05)
        self.assertGreater(abs(expected[0,1]), 1e-10)

    def test_standard_permutations_reorder_joint_covariance(self):
        req, _, _ = fixture(2)
        factor = 1e-4*dense_factor(28)
        cov = factor@factor.T
        req["covariance"]["matrix"] = cov.tolist()
        baseline = subject.calibrate_one_port(req)
        for order in permutations(range(3)):
            changed = deepcopy(req)
            changed["standards"] = [deepcopy(req["standards"][i]) for i in order]
            complex_order = list(order)+[3+i for i in order]+[6]
            indexes = [14*k+2*j+part for k in range(2) for j in complex_order for part in (0,1)]
            changed["covariance"]["matrix"] = cov[np.ix_(indexes,indexes)].tolist()
            actual = subject.calibrate_one_port(changed)
            np.testing.assert_allclose(output(actual), output(baseline), rtol=2e-12, atol=2e-12)
            np.testing.assert_allclose(actual["covariance"], baseline["covariance"], rtol=2e-12, atol=2e-16)
            np.testing.assert_allclose(actual["sensitivity"], np.asarray(baseline["sensitivity"])[:,indexes],
                                       rtol=2e-12, atol=2e-12)

    def test_zero_and_rank_one_covariance_against_oracle(self):
        req, _, _ = fixture(2)
        jac = finite_jacobian(vector(req))
        v = 1e-4*np.cos(np.arange(28)*.3)
        for cov in (np.zeros((28,28)),np.outer(v,v)):
            req["covariance"]["matrix"] = cov.tolist()
            got = subject.calibrate_one_port(req)
            np.testing.assert_allclose(got["covariance"], jac@cov@jac.T, rtol=5e-7, atol=2e-16)

    def test_deterministic_nonlinear_covariance_convergence(self):
        req, _, _ = fixture(2)
        x = vector(req)
        factor = dense_factor(len(x))
        errors = []
        for epsilon in (.004,.002,.001):
            cov = epsilon**2*(factor@factor.T)
            req["covariance"]["matrix"] = cov.tolist()
            linear = np.asarray(subject.calibrate_one_port(req)["covariance"])
            shifts = np.sqrt(len(x))*epsilon*factor.T
            points = np.array([cross_ratio(x+sign*h) for h in shifts for sign in (-1,1)])
            centered = points-points.mean(axis=0)
            nonlinear = centered.T@centered/len(points)
            errors.append(np.linalg.norm(nonlinear-linear)/np.linalg.norm(linear))
        self.assertLess(errors[1], .35*errors[0], errors)
        self.assertLess(errors[2], .35*errors[1], errors)
        self.assertLess(errors[2], 2e-4, errors)

    def test_dut_inverse_pole_is_rejected_at_last_frequency_without_mutation(self):
        req, _, terms = fixture(2)
        d,t,s = terms[1]
        req["dut"]["measured"][1] = ri(-(t-d*s)/s)
        before = deepcopy(req)
        with self.assertRaises(subject.OnePortCalibrationError) as caught:
            subject.calibrate_one_port(req)
        self.assertEqual(caught.exception.code, "ONE_PORT_CALIBRATION_REPRESENTATION_LIMIT")
        self.assertEqual(req, before)

    def test_coincident_standards_and_collapsed_measurements_reject(self):
        for mode in ("reflection", "measured"):
            req, _, _ = fixture(2)
            for standard in req["standards"]:
                standard[mode][1] = ri(.1+.2j)
            with self.subTest(mode=mode), self.assertRaises(subject.OnePortCalibrationError) as caught:
                subject.calibrate_one_port(req)
            self.assertEqual(caught.exception.code, "ONE_PORT_CALIBRATION_ILL_CONDITIONED")

    def test_small_indefinite_covariance_is_not_hidden_by_large_variance(self):
        req, _, _ = fixture(2)
        cov = np.eye(28)*1e-8
        cov[0,0] = cov[1,1] = 1e-40
        cov[0,1] = cov[1,0] = 1.01e-40
        req["covariance"]["matrix"] = cov.tolist()
        with self.assertRaises(subject.OnePortCalibrationError) as caught:
            subject.calibrate_one_port(req)
        self.assertEqual(caught.exception.code, "ONE_PORT_CALIBRATION_INVALID_COVARIANCE")

    def test_derived_network_mutation_cannot_change_retained_source(self):
        req, _, _ = fixture(2)
        before = deepcopy(req)
        result = subject.calibrate_one_port(req)
        result["derived_network"]["frequencies_hz"][0] *= 2
        result["derived_network"]["s_parameters"][0][0][0]["real"] = 99.
        self.assertEqual(result["source_request"], before)
        self.assertEqual(req, before)


if __name__ == "__main__":
    unittest.main()
