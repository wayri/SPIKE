# SPDX-License-Identifier: Apache-2.0
"""Original affine-matrix, real-DC and delayed-line interpolation witnesses."""
from copy import deepcopy
import math
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core import sparameter_sampling as sampling


def pairs(matrix):
    return [[{"real": float(complex(v).real), "imag": float(complex(v).imag)} for v in row] for row in matrix]


def values(record):
    return np.array([[complex(v["real"], v["imag"]) for v in row] for row in record])


def request(frequencies=None, matrices=None, targets=None):
    frequencies = frequencies if frequencies is not None else [0., 100., 800., 2000.]
    a = np.array([[.1, .2, -.05], [.03, .15, .1], [.12, -.07, .08]])
    b = np.array([[1+2j, 3-1j, -2+.5j], [2-3j, -1+1j, 1+.1j], [.2+.7j, -.6+.2j, .5-.8j]]) * 1e-5
    matrices = matrices if matrices is not None else [a + f*b for f in frequencies]
    n = len(matrices[0])
    return {"contract": sampling.REQUEST_CONTRACT,
            "source": {"id": "original-matrix", "port_names": [f"port-{i}" for i in range(n)],
                       "reference_impedance_ohm": 75., "frequencies_hz": list(frequencies),
                       "s_parameters": [pairs(matrix) for matrix in matrices]},
            "target_frequencies_hz": targets if targets is not None else [0., 25., 100., 450., 800., 1400., 2000.],
            "dc_policy": {"mode": "require_source"}}


class SParameterSamplingTests(unittest.TestCase):
    def test_affine_complex_multiport_exactness_and_interpolation_mapping(self):
        req = request()
        before = deepcopy(req)
        out = sampling.resample_sparameter_network(req)
        self.assertEqual(req, before)
        self.assertEqual(out["interpolation_method"], "cartesian_linear")
        self.assertEqual(out["model_status"], "experimental")
        self.assertFalse(out["production_qualified"])
        for actual, frequency in zip(out["derived_network"]["s_parameters"], req["target_frequencies_hz"]):
            expected = values(request(frequencies=[frequency], targets=[frequency])["source"]["s_parameters"][0])
            np.testing.assert_allclose(values(actual), expected, rtol=0, atol=6e-17)
        expected_mapping = [(0., 0., 0.), (0., 100., .25), (100., 100., 0.), (100., 800., .5),
                            (800., 800., 0.), (800., 2000., .5), (2000., 2000., 0.)]
        for diagnostic, expected in zip(out["diagnostics"], expected_mapping):
            self.assertEqual((diagnostic["lower_frequency_hz"], diagnostic["upper_frequency_hz"], diagnostic["weight_upper"]), expected)
            self.assertEqual(diagnostic["kind"], "source_sample" if expected[0] == expected[1] else "linear_interpolation")
        self.assertGreater(abs(values(out["derived_network"]["s_parameters"][3])[0, 1]
                               - values(out["derived_network"]["s_parameters"][3])[1, 0]), .1)

    def test_exact_source_copy_snapshot_identity_and_one_sample_support(self):
        req = request([3.], [[[1, -.25+.5j], [.7-.2j, 0]]], [3.])
        req["source"]["s_parameters"][0][0][0] = {"real": 1, "imag": -0.0}
        before = deepcopy(req)
        out = sampling.resample_sparameter_network(req)
        self.assertEqual(out["derived_network"]["s_parameters"], req["source"]["s_parameters"])
        self.assertIs(type(out["derived_network"]["s_parameters"][0][0][0]["real"]), int)
        self.assertEqual(math.copysign(1, out["derived_network"]["s_parameters"][0][0][0]["imag"]), -1)
        self.assertEqual(out["source"]["input_digest"], sampling._digest(req["source"]))
        self.assertEqual(out["input_digest"], sampling._digest(before))
        self.assertEqual(out["derived_network"]["reference_impedance_ohm"], 75.)
        out["derived_network"]["s_parameters"][0][0][0]["real"] = 99
        out["derived_network"]["port_names"][0] = "changed"
        self.assertEqual(out["source"]["network"], before["source"])
        self.assertEqual(req, before)

    def test_supplied_real_filter_dc_and_no_inferred_zero_frequency(self):
        h10, h100 = 1/(1+1j), 1/(1+10j)
        req = request([10., 100.], [[[h10]], [[h100]]], [10., 55., 100.])
        positive_only = sampling.resample_sparameter_network(req)
        self.assertEqual(positive_only["diagnostics"][0]["kind"], "source_sample")
        req["target_frequencies_hz"] = [0., 5., 10., 55., 100.]
        with self.assertRaises(sampling.SParameterSamplingError) as caught:
            sampling.resample_sparameter_network(req)
        self.assertEqual(caught.exception.code, "SPARAMETER_SAMPLING_OUTSIDE_SUPPORT")
        req["dc_policy"] = {"mode": "supplied", "s_parameters": [[{"real": 1, "imag": 0}]]}
        out = sampling.resample_sparameter_network(req)
        expected = [1., .5*(1+h10), h10, .5*(h10+h100), h100]
        for record, value in zip(out["derived_network"]["s_parameters"], expected):
            self.assertAlmostEqual(abs(values(record)[0, 0] - value), 0., delta=1e-16)
        self.assertEqual(out["dc_policy"], req["dc_policy"])
        self.assertEqual(out["source"]["network"], req["source"])
        self.assertEqual(out["diagnostics"][0]["kind"], "supplied_dc")
        self.assertEqual(out["diagnostics"][1]["lower_frequency_hz"], 0.)
        self.assertEqual(out["diagnostics"][1]["upper_frequency_hz"], 10.)
        self.assertEqual(out["diagnostics"][1]["weight_upper"], .5)

    def test_convex_passive_preservation_and_active_samples_retained(self):
        first = np.array([[0., .8], [.6, 0.]])
        second = np.array([[.2j, -.3j], [.4+.1j, -.1]])
        req = request([1., 9.], [first, second], list(range(1, 10)))
        out = sampling.resample_sparameter_network(req)
        self.assertTrue(all(row["smax"] <= 1 for row in out["diagnostics"]))
        for index, record in enumerate(out["derived_network"]["s_parameters"]):
            expected = (1-index/8)*first + index/8*second
            np.testing.assert_allclose(values(record), expected, rtol=0, atol=1e-16)
            self.assertAlmostEqual(out["diagnostics"][index]["smax"], np.linalg.svd(expected, compute_uv=False)[0], delta=1e-15)
        active = request([1., 2.], [2*first, 3*first], [1., 1.5, 2.])
        result = sampling.resample_sparameter_network(active)
        self.assertTrue(all(row["smax"] > 1 for row in result["diagnostics"]))
        np.testing.assert_allclose(values(result["derived_network"]["s_parameters"][1]), 2.5*first, atol=1e-15)

    def test_delayed_line_cartesian_interpolation_second_order_refinement(self):
        # At an interval midpoint, interpolating exp(-j*w*tau) gives the
        # exact midpoint phase times cos(pi*df*tau). Error is 1-cos(...),
        # hence O(df^2). This is an interpolation oracle, not a time transform.
        errors = []
        tau, bandwidth = 3e-9, 1e8
        for count in (4, 8, 16, 32):
            grid = [bandwidth*i/count for i in range(count+1)]
            matrices = [[[0., np.exp(-2j*math.pi*f*tau)], [np.exp(-2j*math.pi*f*tau), 0.]] for f in grid]
            targets = [.5*(a+b) for a, b in zip(grid, grid[1:])]
            out = sampling.resample_sparameter_network(request(grid, matrices, targets))
            actual = max(abs(values(s)[1, 0] - np.exp(-2j*math.pi*f*tau)) for s, f in zip(out["derived_network"]["s_parameters"], targets))
            expected = 1 - math.cos(math.pi * bandwidth/count * tau)
            self.assertAlmostEqual(actual, expected, delta=5e-16)
            errors.append(actual)
        self.assertTrue(all(3.9 < a/b < 4.01 for a, b in zip(errors, errors[1:])))
        self.assertLess(errors[-1], .00044)

    def test_strict_dc_shapes_ranges_grids_and_finite_admission(self):
        mutations = [lambda r: r.update(extra=True), lambda r: r["source"].update(extra=True),
            lambda r: r["source"].update(port_names=["a", "a", "c"]),
            lambda r: r["source"]["port_names"].__setitem__(0, " "),
            lambda r: r["source"].update(reference_impedance_ohm=True),
            lambda r: r["source"].update(reference_impedance_ohm=0),
            lambda r: r["source"]["s_parameters"].pop(),
            lambda r: r["source"]["s_parameters"][0].pop(),
            lambda r: r["source"]["s_parameters"][0][0][0].update(real=True),
            lambda r: r["source"]["s_parameters"][0][0][0].update(imag=1e-300),
            lambda r: r["source"]["s_parameters"][1][0][0].update(real=float("inf")),
            lambda r: r["target_frequencies_hz"].__setitem__(0, -1),
            lambda r: r["target_frequencies_hz"].__setitem__(0, True),
            lambda r: r["target_frequencies_hz"].__setitem__(1, 0.),
            lambda r: r["target_frequencies_hz"].append(2001.),
            lambda r: r["source"]["frequencies_hz"].__setitem__(1, 0.),
            lambda r: r.update(dc_policy={"mode": "infer"}),
            lambda r: r.update(dc_policy={"mode": "require_source", "s_parameters": []}),
            lambda r: r.update(dc_policy={"mode": "supplied", "s_parameters": r["source"]["s_parameters"][0]})]
        for i, mutate in enumerate(mutations):
            req = request(); mutate(req)
            with self.subTest(case=i), patch.object(sampling.np.linalg, "svd") as solve:
                with self.assertRaises(sampling.SParameterSamplingError):
                    sampling.resample_sparameter_network(req)
                solve.assert_not_called()
        req = request([1.], [[[.1j]]], [0.])
        req["dc_policy"] = {"mode": "supplied", "s_parameters": pairs([[1e-15j]])}
        with self.assertRaisesRegex(sampling.SParameterSamplingError, "exactly real"):
            sampling.resample_sparameter_network(req)

    def test_resources_extreme_frequencies_and_cancellation_discard_partial(self):
        for constant in ("_MAX_REQUEST_BYTES", "_MAX_RESULT_BYTES", "_MAX_MATRIX_ENTRIES", "_MAX_SVD_WORK", "_MAX_FREQUENCIES"):
            with patch.object(sampling, constant, 1), patch.object(sampling.np.linalg, "svd") as solve:
                with self.assertRaises(sampling.SParameterSamplingError) as caught:
                    sampling.resample_sparameter_network(request())
                self.assertEqual(caught.exception.code, "SPARAMETER_SAMPLING_RESOURCE_LIMIT")
                solve.assert_not_called()
        extreme = request([1e308, 1.6e308], [[[.2]], [[.8]]], [1.3e308])
        result = sampling.resample_sparameter_network(extreme)
        self.assertAlmostEqual(values(result["derived_network"]["s_parameters"][0])[0, 0].real, .5, delta=1e-15)
        # Keep exact integer frequency distinctions above float's integer
        # precision. No false source-sample copying after float conversion.
        precise = request([10**20, 10**20+4], [[[.2]], [[.8]]], [10**20+1])
        result = sampling.resample_sparameter_network(precise)
        self.assertEqual(result["diagnostics"][0]["weight_upper"], .25)
        self.assertEqual(result["diagnostics"][0]["kind"], "linear_interpolation")
        collapsed = request([1e20, 10**20+4], [[[.2]], [[.8]]], [10**20+1])
        with self.assertRaisesRegex(sampling.SParameterSamplingError, "interval collapses") as caught:
            sampling.resample_sparameter_network(collapsed)
        self.assertEqual(caught.exception.code, "SPARAMETER_SAMPLING_NUMERICAL_FAILURE")
        completed, original = 0, np.linalg.svd

        def finish(*args, **kwargs):
            nonlocal completed
            out = original(*args, **kwargs)
            completed += 1
            return out

        with patch.object(sampling.np.linalg, "svd", side_effect=finish):
            with self.assertRaises(sampling.SParameterSamplingError) as caught:
                sampling.resample_sparameter_network(request(), cancel_check=lambda: completed >= 2)
            self.assertEqual(caught.exception.code, "SPARAMETER_SAMPLING_CANCELLED")
        self.assertEqual(completed, 2)


if __name__ == "__main__":
    unittest.main()
