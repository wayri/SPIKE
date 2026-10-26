# SPDX-License-Identifier: Apache-2.0
"""Independent cross-ratio calibration plus simultaneous fixture-wave oracles."""
from copy import deepcopy
import hashlib
import json
import unittest

import numpy as np

from python.spike_core.solvers.signal_integrity.networks import calibrated_fixture_uq as subject
from tests.python import test_multiport_calibration_oracles as cal


def forward_fixture(f, d):
    n = len(d)
    eye, zero = np.eye(n), np.zeros((n, n))
    a = np.block([[eye, zero, -f[:n, n:]],
                  [zero, eye, -f[n:, n:]], [zero, -d, eye]])
    b = np.vstack((f[:n, :n], f[n:, :n], zero))
    waves = np.linalg.solve(a, b)
    np.testing.assert_allclose(a @ waves, b, rtol=2e-13, atol=2e-13)
    return waves[:n]


def fixture_labels(n, count):
    return [f"fixture.f{k}.p{i}.p{j}.{part}" for k in range(count)
            for i in range(2*n) for j in range(2*n) for part in ("real", "imag")]


def fixture(n=2, count=1):
    calibration, truth, terms = cal.fixture(n, count)
    rng = np.random.default_rng(382 + n)
    fs, observed = [], []
    for k in range(count):
        def dense(scale):
            return scale*(rng.normal(size=(n, n))+1j*rng.normal(size=(n, n)))/n
        f = np.block([[dense(.10), .81*np.eye(n)+dense(.12)],
                      [.76*np.eye(n)+dense(.13), dense(.09)]])
        fs.append(f)
        d, _, v, u, w = terms[k]
        observed.append(cal.forward(forward_fixture(f, truth[k]), d, u, v, w))
    calibration["dut"]["measured"] = cal.encode(observed)
    labels = cal.basis(n, count)+fixture_labels(n, count)
    network = {"id": "original-coupled-physical-fixture", "port_names": calibration["port_names"]+[f"dut.{i}" for i in range(n)],
               "reference_impedance_ohm": 50., "frequencies_hz": calibration["frequencies_hz"][:],
               "s_parameters": cal.encode(fs)}
    return {"contract": "spike/calibrated-fixture-uq-request/v1", "calibration": calibration,
            "fixture": network, "external_ports": calibration["port_names"][:], "dut_ports": [f"dut.{i}" for i in range(n)],
            "covariance": {"basis": labels, "matrix": np.zeros((len(labels), len(labels))).tolist(),
                           "provenance": "Original synthetic full joint real covariance"}}, truth


def vector(req):
    return np.r_[cal.vector(req["calibration"]), cal.real_vector(cal.decode(req["fixture"]["s_parameters"]))]


def oracle(x, req):
    n, count = len(req["external_ports"]), len(req["calibration"]["frequencies_hz"])
    split = len(cal.basis(n, count))
    reference = req["calibration"]["port_names"].index(req["calibration"]["gain_reference_port"])
    bvec = cal.oracle(x[:split], n, count, reference)
    bs = (bvec[::2]+1j*bvec[1::2]).reshape(count, n, n)
    fv = x[split:]
    fs = (fv[::2]+1j*fv[1::2]).reshape(count, 2*n, 2*n)
    names = req["fixture"]["port_names"]
    order = [names.index(name) for name in req["external_ports"]+req["dut_ports"]]
    result = []
    for b, stored in zip(bs, fs):
        f = stored[np.ix_(order, order)]
        system = np.block([[f[:n, n:], np.zeros((n, n))], [-f[n:, n:], np.eye(n)]])
        waves = np.linalg.solve(system, np.vstack((b-f[:n, :n], f[n:, :n])))
        result.append(np.linalg.solve(waves[n:].T, waves[:n].T).T)
    return cal.real_vector(result)


def jacobian(req):
    x = vector(req)
    h = 2e-6
    return np.column_stack([(oracle(x+shift, req)-oracle(x-shift, req))/(2*h) for shift in h*np.eye(len(x))])


def set_covariance(req, covariance):
    split = len(req["calibration"]["covariance"]["basis"])
    req["covariance"]["matrix"] = covariance.tolist()
    req["calibration"]["covariance"]["matrix"] = covariance[:split, :split].tolist()


def output(result):
    return cal.decode(result["derived_network"]["s_parameters"])


def identity_instrument(req, bs):
    n, count = len(req["external_ports"]), len(bs)
    for standard, reflection in zip(req["calibration"]["reflection_standards"], (1., -1., 0.)):
        standard["reflection"] = cal.encode(np.full((count, n), reflection))
        standard["measured"] = deepcopy(standard["reflection"])
    coupling = req["calibration"]["coupling_standard"]
    coupling["s_parameters"] = cal.encode([.5*(np.ones((n, n))-np.eye(n))]*count)
    coupling["measured"] = deepcopy(coupling["s_parameters"])
    req["calibration"]["dut"]["measured"] = cal.encode(bs)


class CalibratedFixtureIndependentTests(unittest.TestCase):
    def test_two_three_four_port_truth_and_immutable_sources(self):
        for n in (2, 3, 4):
            for count in (1, 2):
                with self.subTest(n=n, count=count):
                    req, truth = fixture(n, count)
                    before = deepcopy(req)
                    result = subject.compose_calibrated_fixture(req)
                    np.testing.assert_allclose(output(result), truth, atol=2e-12, rtol=2e-12)
                    np.testing.assert_allclose(cal.real_vector(output(result)), oracle(vector(req), req), atol=2e-12, rtol=2e-12)
                    self.assertEqual(subject.input_basis(req["calibration"], req["fixture"]), req["covariance"]["basis"])
                    self.assertEqual(req, before)
                    self.assertEqual(result["source_request"], before)
                    self.assertEqual(result["model_status"], "experimental")
                    self.assertFalse(result["production_qualified"])
                    self.assertFalse(result["measurement_qualified"])
                    self.assertFalse(result["linearization_qualified"])
                    encoded = json.dumps(before, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
                    self.assertEqual(result["input_digest"], hashlib.sha256(encoded).hexdigest())
                    self.assertEqual(np.count_nonzero(result["covariance"]), 0)
                    self.assertIn("calibration_result", result)

    def test_all_joint_coordinates_dense_psd_and_frequency_correlations(self):
        for n, count in ((2, 1), (2, 2), (3, 2), (4, 2)):
            with self.subTest(n=n, count=count):
                req, _ = fixture(n, count)
                x = vector(req)
                factor = 1e-4*cal.dense_factor(len(x))
                # Keep the largest valid fixture within the finite JSON budget.
                # This rounding is tiny relative to its positive minimum eigenvalue.
                covariance = np.round(factor @ factor.T, 15)
                set_covariance(req, covariance)
                result = subject.compose_calibrated_fixture(req)
                jac = jacobian(req)
                np.testing.assert_allclose(result["sensitivity"], jac, atol=3e-8, rtol=3e-6)
                wanted = jac @ covariance @ jac.T
                np.testing.assert_allclose(result["covariance"], wanted, atol=2e-14, rtol=5e-6)
                split = len(req["calibration"]["covariance"]["basis"])
                separate = covariance.copy()
                separate[:split, split:] = 0
                separate[split:, :split] = 0
                self.assertGreater(np.linalg.norm(wanted-jac @ separate @ jac.T), 1e-10)
                if count == 2:
                    self.assertGreater(np.linalg.norm(wanted[:2*n*n, 2*n*n:]), 1e-10)

    def test_correlated_common_error_cancels_without_double_counting(self):
        req, truth = fixture()
        eye, zero = np.eye(2), np.zeros((2, 2))
        req["fixture"]["s_parameters"] = cal.encode([np.block([[zero, eye], [eye, zero]])])
        identity_instrument(req, truth)
        direction = np.zeros(len(vector(req)))
        labels = req["covariance"]["basis"]
        for label in ("f0.dut.measured.p0.p1.real", "fixture.f0.p0.p1.real"):
            direction[labels.index(label)] = 1e-4
        covariance = np.outer(direction, direction)
        set_covariance(req, covariance)
        result = subject.compose_calibrated_fixture(req)
        self.assertLess(np.linalg.norm(result["covariance"]), 1e-20)
        self.assertGreater(np.linalg.norm(result["calibration_result"]["covariance"]), 1e-10)
        split = len(req["calibration"]["covariance"]["basis"])
        covariance[:split, split:] = 0
        covariance[split:, :split] = 0
        set_covariance(req, covariance)
        self.assertGreater(np.linalg.norm(subject.compose_calibrated_fixture(req)["covariance"]), 1e-10)

    def test_symmetric_nonlinear_covariance_refinement(self):
        req, _ = fixture(2, 2)
        x = vector(req)
        factor = cal.dense_factor(len(x))
        errors = []
        for scale in (2e-4, 1e-4, 5e-5):
            set_covariance(req, scale**2*(factor @ factor.T))
            linear = np.asarray(subject.compose_calibrated_fixture(req)["covariance"])
            shifts = np.sqrt(len(x))*scale*factor.T
            values = np.array([oracle(x+sign*shift, req) for shift in shifts for sign in (-1, 1)])
            centered = values-values.mean(axis=0)
            nonlinear = centered.T @ centered/len(values)
            errors.append(np.linalg.norm(nonlinear-linear)/np.linalg.norm(linear))
        self.assertLess(errors[1], errors[0]/2.5, errors)
        self.assertLess(errors[2], errors[1]/2.5, errors)
        self.assertLess(errors[2], 2e-5, errors)

    def test_fixture_storage_and_dut_order_covariance_permutations(self):
        req, _ = fixture(3, 2)
        dimension = len(vector(req))
        factor = 1e-4*cal.dense_factor(dimension)
        cov = factor @ factor.T
        set_covariance(req, cov)
        baseline = subject.compose_calibrated_fixture(req)
        changed = deepcopy(req)
        order = [4, 1, 5, 0, 3, 2]
        changed["fixture"]["port_names"] = [req["fixture"]["port_names"][i] for i in order]
        changed["fixture"]["s_parameters"] = cal.encode(cal.decode(req["fixture"]["s_parameters"])[:, order][:, :, order])
        split = len(req["calibration"]["covariance"]["basis"])
        indices = list(range(split))+[split+72*k+2*(6*i+j)+p for k in range(2) for i in order for j in order for p in (0, 1)]
        set_covariance(changed, cov[np.ix_(indices, indices)])
        dut_order = [2, 0, 1]
        changed["dut_ports"] = [req["dut_ports"][i] for i in dut_order]
        result = subject.compose_calibrated_fixture(changed)
        rows = [18*k+2*(3*i+j)+p for k in range(2) for i in dut_order for j in dut_order for p in (0, 1)]
        np.testing.assert_allclose(output(result), output(baseline)[:, dut_order][:, :, dut_order], atol=2e-12, rtol=2e-12)
        np.testing.assert_allclose(result["sensitivity"], np.asarray(baseline["sensitivity"])[np.ix_(rows, indices)], atol=3e-8, rtol=3e-6)
        np.testing.assert_allclose(result["covariance"], np.asarray(baseline["covariance"])[np.ix_(rows, rows)], atol=2e-14, rtol=5e-6)

    def test_mismatched_calibration_covariance_and_late_sample_failure(self):
        req, _ = fixture(2, 2)
        for kind in ("covariance", "late_sample", "map"):
            bad = deepcopy(req)
            if kind == "covariance":
                bad["calibration"]["covariance"]["matrix"][0][0] = 1e-8
            elif kind == "late_sample":
                f = cal.decode(bad["fixture"]["s_parameters"])
                f[1, :2, 2:] = 0
                bad["fixture"]["s_parameters"] = cal.encode(f)
            else:
                bad["dut_ports"][0] = bad["external_ports"][0]
            before = deepcopy(bad)
            with self.assertRaises(subject.CalibratedFixtureUQError):
                subject.compose_calibrated_fixture(bad)
            self.assertEqual(bad, before)

    def test_calibration_external_port_permutation_preserves_physical_dut(self):
        req, _ = fixture(3, 2)
        factor = 1e-4*cal.dense_factor(len(vector(req)))
        covariance = factor @ factor.T
        set_covariance(req, covariance)
        baseline = subject.compose_calibrated_fixture(req)
        changed = deepcopy(req)
        order = [2, 0, 1]
        nested = changed["calibration"]
        nested["port_names"] = [req["external_ports"][i] for i in order]
        changed["external_ports"] = nested["port_names"][:]
        for standard in nested["reflection_standards"]:
            for field in ("reflection", "measured"):
                standard[field] = cal.encode(cal.decode(standard[field])[:, order])
        for record, field in (("coupling_standard", "s_parameters"), ("coupling_standard", "measured"), ("dut", "measured")):
            nested[record][field] = cal.encode(cal.decode(nested[record][field])[:, order][:, :, order])
        local = [3*j+i for j in range(6) for i in order]
        local += [18+9*b+3*i+j for b in range(3) for i in order for j in order]
        indices = [90*k+2*j+p for k in range(2) for j in local for p in (0, 1)]
        indices += list(range(180, len(vector(req))))
        set_covariance(changed, covariance[np.ix_(indices, indices)])
        result = subject.compose_calibrated_fixture(changed)
        np.testing.assert_allclose(output(result), output(baseline), atol=2e-12, rtol=2e-12)
        np.testing.assert_allclose(result["sensitivity"], np.asarray(baseline["sensitivity"])[:, indices], atol=3e-8, rtol=3e-6)
        np.testing.assert_allclose(result["covariance"], baseline["covariance"], atol=2e-14, rtol=5e-6)

    def test_all_direction_recovery_and_feedback_poles_reject(self):
        req, _ = fixture()
        eye, zero = np.eye(2), np.zeros((2, 2))
        epsilon, transmission = 2.**-40, 2.**-20
        cases = ((np.block([[zero, eye], [eye, eye]]), (-1+epsilon)*eye),
                 (np.block([[zero, transmission*eye], [transmission*eye, eye]]), (1-epsilon)*eye))
        for physical, measured in cases:
            bad = deepcopy(req)
            bad["fixture"]["s_parameters"] = cal.encode([physical])
            identity_instrument(bad, [measured])
            before = deepcopy(bad)
            with self.assertRaises(subject.CalibratedFixtureUQError) as caught:
                subject.compose_calibrated_fixture(bad)
            self.assertEqual(caught.exception.code, "CALIBRATED_FIXTURE_UQ_REPRESENTATION_LIMIT")
            self.assertEqual(bad, before)

    def test_late_cancellation_preserves_input(self):
        req, _ = fixture(2, 2)
        before = deepcopy(req)
        polls = [0]
        def count_poll():
            polls[0] += 1
            return False
        subject.compose_calibrated_fixture(req, cancel_check=count_poll)
        limit = polls[0]-1
        polls[0] = 0
        def cancel_late():
            polls[0] += 1
            return polls[0] >= limit
        with self.assertRaises(subject.CalibratedFixtureUQError) as caught:
            subject.compose_calibrated_fixture(req, cancel_check=cancel_late)
        self.assertEqual(caught.exception.code, "CALIBRATED_FIXTURE_UQ_CANCELLED")
        self.assertEqual(req, before)


if __name__ == "__main__":
    unittest.main()
