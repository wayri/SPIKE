# SPDX-License-Identifier: Apache-2.0
"""Original wave-connection and matched-delay references, no chain oracle."""
from copy import deepcopy
import math
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core import sparameter_deembedding as deembedding


def pairs(matrix):
    return [[{"real": float(complex(v).real), "imag": float(complex(v).imag)} for v in row] for row in matrix]


def complex_matrix(sample):
    return np.array([[complex(v["real"], v["imag"]) for v in row] for row in sample])


def network(identity, names, frequencies, matrices, reference=50.):
    return {"id": identity, "port_names": names, "reference_impedance_ohm": reference,
            "frequencies_hz": list(frequencies), "s_parameters": [pairs(s) for s in matrices]}


def connect(left, dut, right):
    """Solve four internal incident waves from continuity and b=S*a.

    Unknowns are (a_leftFixtureRight,a_DUTleft,a_DUTright,a_rightFixtureLeft).
    Each incident wave equals the connected neighbour's outgoing wave.
    External unit incidents are two RHSs. No T/ABCD conversion or production
    helper participates in this embedding oracle.
    """
    matrix = np.array([[1., -dut[0, 0], -dut[0, 1], 0.],
                       [-left[1, 1], 1., 0., 0.],
                       [0., 0., 1., -right[0, 0]],
                       [0., -dut[1, 0], -dut[1, 1], 1.]], dtype=complex)
    rhs = np.array([[0., 0.], [left[1, 0], 0.], [0., right[0, 1]], [0., 0.]], dtype=complex)
    internal = np.linalg.solve(matrix, rhs)
    return np.diag([left[0, 0], right[1, 1]]) + np.array([[left[0, 1], 0., 0., 0.], [0., 0., 0., right[1, 0]]]) @ internal


def request(left=None, dut=None, right=None, frequencies=None):
    frequencies = frequencies or [0., 13., 73000., 2.35e8]
    left = np.array(left if left is not None else [[.08+.04j, .61-.12j], [.72+.03j, -.11+.05j]])
    dut = np.array(dut if dut is not None else [[.13-.17j, .24+.11j], [1.7-.36j, -.23+.07j]])
    right = np.array(right if right is not None else [[-.07+.09j, .68+.02j], [.57-.08j, .09-.06j]])
    measured = connect(left, dut, right)
    return {"contract": deembedding.REQUEST_CONTRACT,
            "measured": network("measurement", ["ext-left", "ext-right"], frequencies, [measured] * len(frequencies)),
            "left_fixture": network("left", ["ext-left", "DUT-left"], frequencies, [left] * len(frequencies)),
            "right_fixture": network("right", ["DUT-right", "ext-right"], frequencies, [right] * len(frequencies))}, dut


class TwoPortDeembeddingTests(unittest.TestCase):
    def test_analytic_matched_delay_attenuation_dc_and_nonuniform_grid(self):
        frequencies = [0., 17., 8.1e6, 2.75e8]
        for reference in (25., 50., 75.):
            rows = {key: [] for key in ("measured", "left_fixture", "right_fixture")}
            expected = []
            for frequency in frequencies:
                left = .85 * np.exp(-2j * math.pi * frequency * 1.3e-9)
                dut = .74 * np.exp(-2j * math.pi * frequency * 2.7e-9)
                right = .91 * np.exp(-2j * math.pi * frequency * .8e-9)
                for key, value in (("measured", left*dut*right), ("left_fixture", left), ("right_fixture", right)):
                    rows[key].append([[0., value], [value, 0.]])
                expected.append([[0., dut], [dut, 0.]])
            req = {"contract": deembedding.REQUEST_CONTRACT,
                   "measured": network("m", ["x", "y"], frequencies, rows["measured"], reference),
                   "left_fixture": network("l", ["x", "p"], frequencies, rows["left_fixture"], reference),
                   "right_fixture": network("r", ["q", "y"], frequencies, rows["right_fixture"], reference)}
            out = deembedding.deembed_two_port(req)
            self.assertEqual(out["derived_network"]["frequencies_hz"], frequencies)
            self.assertEqual(out["derived_network"]["reference_impedance_ohm"], reference)
            for actual, exact, diagnostic in zip(out["derived_network"]["s_parameters"], expected, out["diagnostics"]):
                np.testing.assert_allclose(complex_matrix(actual), exact, rtol=0, atol=5e-15)
                self.assertAlmostEqual(diagnostic["smax"], .74, delta=3e-15)
                self.assertLess(diagnostic["reconstruction_residual"], 5e-15)

    def test_reflective_nonreciprocal_active_dut_from_independent_connections(self):
        req, expected = request()
        original = deepcopy(req)
        out = deembedding.deembed_two_port(req)
        self.assertEqual(req, original)
        self.assertEqual(out["derived_network"]["port_names"], ["DUT-left", "DUT-right"])
        self.assertEqual(out["model_status"], "experimental")
        self.assertFalse(out["production_qualified"])
        for sample, diagnostic in zip(out["derived_network"]["s_parameters"], out["diagnostics"]):
            actual = complex_matrix(sample)
            np.testing.assert_allclose(actual, expected, rtol=0, atol=2e-15)
            self.assertGreater(abs(actual[1, 0] - actual[0, 1]), 1.)
            self.assertGreater(diagnostic["smax"], 1.)
            self.assertAlmostEqual(diagnostic["smax"], np.linalg.svd(expected, compute_uv=False)[0], delta=2e-15)
            self.assertEqual(diagnostic["condition_product"], diagnostic["condition_left"] * diagnostic["condition_right"])
        for key in ("measured", "left_fixture", "right_fixture"):
            self.assertEqual(out["sources"][key]["network"], original[key])
            self.assertEqual(out["sources"][key]["input_digest"], deembedding._digest(original[key]))
        self.assertEqual(out["input_digest"], deembedding._digest(original))
        self.assertTrue(out["derived_network"]["id"].startswith("deembedded-"))
        out["sources"]["measured"]["network"]["port_names"][0] = "changed"
        self.assertEqual(req, original)

    def test_unilateral_dut_and_forward_polarity_are_preserved(self):
        req, expected = request(dut=[[.05j, 0.], [-1.3+.2j, -.1]])
        out = deembedding.deembed_two_port(req)
        for sample in out["derived_network"]["s_parameters"]:
            np.testing.assert_allclose(complex_matrix(sample), expected, rtol=0, atol=2e-15)
        # A physically different signed fixture must change the corrected DUT;
        # the service must not silently flip phase, polarity, or port order.
        req["left_fixture"]["s_parameters"][0][1][0]["real"] *= -1
        changed = deembedding.deembed_two_port(req)
        self.assertGreater(np.linalg.norm(complex_matrix(changed["derived_network"]["s_parameters"][0]) - expected), .1)

    def test_strict_shapes_names_grids_reference_and_finite_values(self):
        mutations = [lambda r: r.update(extra=True), lambda r: r["measured"].update(extra=True),
            lambda r: r["right_fixture"].update(id="left"),
            lambda r: r["left_fixture"].update(port_names=["DUT-left", "ext-left"]),
            lambda r: r["right_fixture"]["port_names"].__setitem__(0, "DUT-left"),
            lambda r: r["measured"].update(port_names=[" ", "ext-right"]),
            lambda r: r["left_fixture"]["frequencies_hz"].__setitem__(1, 14.),
            lambda r: r["measured"]["frequencies_hz"].__setitem__(1, 0.),
            lambda r: r["measured"]["frequencies_hz"].__setitem__(0, -1.),
            lambda r: r["measured"]["frequencies_hz"].__setitem__(0, True),
            lambda r: r["left_fixture"].update(reference_impedance_ohm=75.),
            lambda r: r["left_fixture"].update(reference_impedance_ohm=True),
            lambda r: r["left_fixture"].update(reference_impedance_ohm={"real": 50., "imag": 0.}),
            lambda r: r["measured"]["s_parameters"].pop(),
            lambda r: r["measured"]["s_parameters"][0].append([]),
            lambda r: r["measured"]["s_parameters"][0][0][0].update(real=True),
            lambda r: r["measured"]["s_parameters"][0][0][0].update(imag=float("nan"))]
        for i, mutate in enumerate(mutations):
            req, _ = request(); mutate(req)
            with self.subTest(case=i), patch.object(deembedding, "_remove") as solve:
                with self.assertRaises(deembedding.SParameterDeembeddingError):
                    deembedding.deembed_two_port(req)
                solve.assert_not_called()

    def test_representation_singular_and_product_condition_failures(self):
        for key in ("measured", "left_fixture", "right_fixture"):
            req, _ = request()
            req[key]["s_parameters"][-1][1][0] = {"real": 1e-13, "imag": 0.}
            with self.assertRaises(deembedding.SParameterDeembeddingError) as caught:
                deembedding.deembed_two_port(req)
            self.assertEqual(caught.exception.code, "SPARAMETER_DEEMBEDDING_REPRESENTATION_LIMIT")
        for left, right in (([[0., 0.], [1., 0.]], [[0., 1.], [1., 0.]]),
                            ([[0., 1e-5], [1., 0.]], [[0., 1e-5], [1., 0.]])):
            req, _ = request(left=left, right=right)
            with self.assertRaises(deembedding.SParameterDeembeddingError) as caught:
                deembedding.deembed_two_port(req)
            self.assertEqual(caught.exception.code, "SPARAMETER_DEEMBEDDING_ILL_CONDITIONED")
        # Ideal fixtures retain active samples; an extreme gain exceeds the
        # explicitly admitted T00-to-S representation, without any clipping.
        req, _ = request(left=[[0., 1.], [1., 0.]], right=[[0., 1.], [1., 0.]], dut=[[0., 1.], [1e13, 0.]])
        with self.assertRaises(deembedding.SParameterDeembeddingError) as caught:
            deembedding.deembed_two_port(req)
        self.assertEqual(caught.exception.code, "SPARAMETER_DEEMBEDDING_REPRESENTATION_LIMIT")

    def test_reconstruction_detects_corrupt_solve_and_extreme_norms_fail(self):
        req, _ = request()
        original = np.linalg.solve

        def corrupt(matrix, rhs):
            return original(matrix, rhs) * 1.001

        with patch.object(deembedding.np.linalg, "solve", side_effect=corrupt):
            with self.assertRaisesRegex(deembedding.SParameterDeembeddingError, "reconstruction"):
                deembedding.deembed_two_port(req)
        req, _ = request(left=[[0., 1.], [1., 0.]], right=[[0., 1.], [1., 0.]])
        req["measured"]["s_parameters"][0][0][0] = {"real": 1e200, "imag": 0.}
        with self.assertRaises(deembedding.SParameterDeembeddingError) as caught:
            deembedding.deembed_two_port(req)
        self.assertEqual(caught.exception.code, "SPARAMETER_DEEMBEDDING_NUMERICAL_FAILURE")

    def test_resources_and_cancellation_after_partial_sweep(self):
        for constant in ("_MAX_REQUEST_BYTES", "_MAX_RESULT_BYTES", "_MAX_FREQUENCIES"):
            with patch.object(deembedding, constant, 1), patch.object(deembedding, "_remove") as solve:
                with self.assertRaises(deembedding.SParameterDeembeddingError) as caught:
                    deembedding.deembed_two_port(request()[0])
                self.assertEqual(caught.exception.code, "SPARAMETER_DEEMBEDDING_RESOURCE_LIMIT")
                solve.assert_not_called()
        completed, original = 0, deembedding._remove

        def finish(*args):
            nonlocal completed
            result = original(*args)
            completed += 1
            return result

        with patch.object(deembedding, "_remove", side_effect=finish):
            with self.assertRaises(deembedding.SParameterDeembeddingError) as caught:
                deembedding.deembed_two_port(request()[0], cancel_check=lambda: completed >= 2)
            self.assertEqual(caught.exception.code, "SPARAMETER_DEEMBEDDING_CANCELLED")
        self.assertEqual(completed, 2)


if __name__ == "__main__":
    unittest.main()
