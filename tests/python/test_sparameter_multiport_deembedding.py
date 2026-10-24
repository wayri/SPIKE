# SPDX-License-Identifier: Apache-2.0
"""Independently assembled internal-wave fixtures; no recovery-formula oracle."""
from copy import deepcopy
import unittest

import numpy as np

from python.spike_core import sparameter_multiport_deembedding as subject


def records(matrix):
    return [[{"real": float(v.real), "imag": float(v.imag)} for v in row]
            for row in np.asarray(matrix, dtype=complex)]


def matrix(record):
    return np.array([[complex(v["real"], v["imag"]) for v in row] for row in record])


def internal_wave_oracle(fixture, dut):
    """Unknowns (bE,bI,bD), with aI=bD and aD=bI; exterior aE=I.

    Assemble all three constitutive equations simultaneously. This does not
    invert transmission blocks, use DUT recovery, or call production helpers.
    """
    n = len(dut)
    ident, zero = np.eye(n), np.zeros((n, n))
    system = np.block([[ident, zero, -fixture[:n, n:]],
                       [zero, ident, -fixture[n:, n:]],
                       [zero, -dut, ident]])
    forcing = np.vstack((fixture[:n, :n], fixture[n:, :n], zero))
    waves = np.linalg.solve(system, forcing)
    np.testing.assert_allclose(system @ waves, forcing, atol=2e-13, rtol=2e-13)
    return waves[:n]


def request(fixture, dut, *, dc=False, shuffle=True):
    n = len(dut)
    external = [f"outside-{j}" for j in range(n)]
    internal = [f"device-{n-j}" for j in range(n)]
    all_names = external + internal
    order = np.random.default_rng(43 + n).permutation(2*n) if shuffle else np.arange(2*n)
    def network(identity, names, values):
        return {"id": identity, "port_names": names, "reference_impedance_ohm": 50.,
                "frequencies_hz": [0. if dc else 7.3e7], "s_parameters": [records(values)]}
    return {"contract": subject.REQUEST_CONTRACT,
            "measured": network("measurement", external, internal_wave_oracle(fixture, dut)),
            "fixture": network("fixture", [all_names[i] for i in order], fixture[np.ix_(order, order)]),
            "external_ports": external, "dut_ports": internal}


def fixture_case(n, *, real=False):
    rng = np.random.default_rng(724 + n)
    def dense(scale):
        values = rng.normal(size=(n, n))
        if not real:
            values = values + 1j*rng.normal(size=(n, n))
        return scale*values/n
    fixture = np.block([[dense(.14), .72*np.eye(n)+dense(.13)],
                        [.83*np.eye(n)+dense(.17), dense(.11)]])
    dut = 1.4*np.eye(n)+dense(.75)
    return fixture, dut


class MultiportDeembeddingTests(unittest.TestCase):
    def assert_error(self, req, code, **kwargs):
        with self.assertRaises(subject.MultiportDeembeddingError) as caught:
            subject.deembed_multiport(req, **kwargs)
        self.assertEqual(caught.exception.code, "MULTIPORT_DEEMBEDDING_"+code)

    def test_independent_dense_internal_wave_oracle_and_shuffled_names(self):
        for n in (1, 2, 3, 4, 8):
            for real in (False, True):
                with self.subTest(n=n, dc=real):
                    fixture, dut = fixture_case(n, real=real)
                    req = request(fixture, dut, dc=real)
                    before = deepcopy(req)
                    result = subject.deembed_multiport(req)
                    actual = matrix(result["derived_network"]["s_parameters"][0])
                    np.testing.assert_allclose(actual, dut, atol=2e-12, rtol=2e-12)
                    self.assertEqual(req, before)
                    self.assertEqual(result["source_request"], before)
                    self.assertEqual(result["derived_network"]["port_names"], req["dut_ports"])
                    self.assertFalse(result["production_qualified"])
                    self.assertEqual(result["model_status"], "experimental")
                    self.assertGreater(result["diagnostics"][0]["sampled_smax"], 1.)
                    self.assertLessEqual(result["diagnostics"][0]["reconstruction_residual"], 1e-10)
                    if real:
                        self.assertTrue(np.all(actual.imag == 0))

    def test_zero_dut_transmission_reflection_and_matched_load(self):
        fixture, _ = fixture_case(3)
        for dut in (np.zeros((3, 3)), np.diag([.9, -.7, 1.8])):
            result = subject.deembed_multiport(request(fixture, dut))
            np.testing.assert_allclose(matrix(result["derived_network"]["s_parameters"][0]),
                                       dut, atol=2e-12, rtol=2e-12)

    def test_nonuniform_frequency_sweep_and_map_covariance(self):
        fixture, dut = fixture_case(3, real=True)
        req = request(fixture, dut, dc=True)
        frequencies = [0., 17., 2.1e6, 8.3e8]
        expected = []
        for source in ("fixture", "measured"):
            req[source]["frequencies_hz"] = frequencies
            req[source]["s_parameters"] = []
        for frequency in frequencies:
            phase = np.exp(-2j*np.pi*frequency*1.3e-9)
            current = request(fixture*phase, dut*phase, dc=frequency == 0)
            expected.append(dut*phase)
            for source in ("fixture", "measured"):
                req[source]["s_parameters"].append(current[source]["s_parameters"][0])
        result = subject.deembed_multiport(req)
        for actual, wanted in zip(result["derived_network"]["s_parameters"], expected):
            np.testing.assert_allclose(matrix(actual), wanted, atol=2e-12, rtol=2e-12)
        changed = deepcopy(req)
        permutation = [2, 0, 1]
        changed["dut_ports"] = [req["dut_ports"][i] for i in permutation]
        remapped = subject.deembed_multiport(changed)
        for actual, wanted in zip(remapped["derived_network"]["s_parameters"], expected):
            np.testing.assert_allclose(matrix(actual), wanted[np.ix_(permutation, permutation)],
                                       atol=2e-12, rtol=2e-12)

    def test_singular_weak_and_condition_product_transmissions(self):
        ident, zero = np.eye(2), np.zeros((2, 2))
        for ei, ie, code in ((zero, ident, "ILL_CONDITIONED"),
                             (ident, zero, "ILL_CONDITIONED"),
                             (ident*1e-13, ident, "REPRESENTATION_LIMIT"),
                             (ident, ident*1e-13, "REPRESENTATION_LIMIT"),
                             (np.diag([1., 1e-9]), ident, "ILL_CONDITIONED"),
                             (np.diag([1., 1e-5]), np.diag([1., 1e-5]), "ILL_CONDITIONED")):
            with self.subTest(code=code, ei=ei, ie=ie):
                self.assert_error(request(np.block([[zero, ei], [ie, zero]]), zero), code)

    def test_singular_recovery_and_ill_conditioned_reconnection(self):
        ident, zero = np.eye(2), np.zeros((2, 2))
        req = request(np.block([[zero, ident], [ident, ident]]), zero, shuffle=False)
        req["measured"]["s_parameters"] = [records(-ident)]
        self.assert_error(req, "ILL_CONDITIONED")
        # D*Fii=0 gives well-conditioned recovery; Fii*D is large and
        # nonnormal, so only the independent reconnection screen detects it.
        ii = np.array([[0., 1e6], [0., 0.]])
        self.assert_error(request(np.block([[zero, ident], [ident, ii]]),
                                  np.diag([0., .5])), "ILL_CONDITIONED")

    def test_invalid_identity_mapping_grid_reference_and_finite_data(self):
        fixture, dut = fixture_case(2)
        original = request(fixture, dut)
        changes = [lambda r: r["fixture"].update(id="measurement"),
                   lambda r: r.update(dut_ports=["device-2", "device-2"]),
                   lambda r: r.update(external_ports=list(reversed(r["external_ports"]))),
                   lambda r: r.update(dut_ports=["missing", "device-1"]),
                   lambda r: r["fixture"].update(reference_impedance_ohm=75.),
                   lambda r: r["fixture"].update(frequencies_hz=[1.]),
                   lambda r: r["measured"].update(reference_impedance_ohm=True),
                   lambda r: r["measured"]["s_parameters"][0][0][0].update(real=float("inf")),
                   lambda r: r["fixture"]["port_names"].__setitem__(0, r["fixture"]["port_names"][1]),
                   lambda r: r.update(extra=True),
                   lambda r: r["measured"].update(frequencies_hz=None)]
        for index, change in enumerate(changes):
            with self.subTest(case=index):
                req = deepcopy(original)
                change(req)
                self.assert_error(req, "INVALID_REQUEST")
        req = deepcopy(original)
        for source in ("fixture", "measured"):
            req[source]["frequencies_hz"] = [0.]
        self.assert_error(req, "INVALID_REQUEST")

    def test_resource_bounds_and_cancellation_are_atomic(self):
        fixture, dut = fixture_case(2)
        req = request(fixture, dut)
        oversized = deepcopy(req)
        oversized["measured"]["port_names"] = [str(i) for i in range(9)]
        self.assert_error(oversized, "RESOURCE_LIMIT")
        oversized = deepcopy(req)
        oversized["measured"]["frequencies_hz"] = list(range(4097))
        self.assert_error(oversized, "RESOURCE_LIMIT")
        before = deepcopy(req)
        self.assert_error(req, "CANCELLED", cancel_check=lambda: True)
        calls = []
        def late_cancel():
            calls.append(1)
            return len(calls) >= 5
        self.assert_error(req, "CANCELLED", cancel_check=late_cancel)
        self.assertEqual(req, before)
        def broken_hook():
            raise RuntimeError("hook failure")
        self.assert_error(req, "CANCEL_CHECK_FAILED", cancel_check=broken_hook)
        self.assert_error(req, "INVALID_REQUEST", cancel_check=3)


if __name__ == "__main__":
    unittest.main()
