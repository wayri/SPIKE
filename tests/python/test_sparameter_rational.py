# SPDX-License-Identifier: Apache-2.0
"""Original RC/Debye coefficient, step and numerical-transform witnesses."""
from copy import deepcopy
import math
import unittest
from unittest.mock import patch

import numpy as np
from scipy.integrate import quad

from python.spike_core import sparameter_rational as rational


DIRECT = np.array([[.05, .02], [-.04, .1]])
RESIDUES = np.array([[[.25, .12], [.07, -.03]], [[.1, -.02], [.19, .04]]])
# Original synthetic relaxation branches, tau=R*C in seconds.
TIMES = np.array([2000. * 100e-9, 400. * 25e-9])


def pairs(matrix):
    return [[{"real": float(v.real), "imag": float(v.imag)} for v in row] for row in np.asarray(matrix, dtype=complex)]


def values(matrix):
    return np.array([[complex(v["real"], v["imag"]) for v in row] for row in matrix])


def request(scale=1.):
    frequencies = [0., 10., 100., 1000., 5000., 20000., 100000., 500000.]
    matrices = [scale * (DIRECT + sum(residue / (1 + 2j*math.pi*f*tau) for residue, tau in zip(RESIDUES, TIMES)))
                for f in frequencies]
    return {"contract": rational.REQUEST_CONTRACT,
            "source": {"id": "synthetic-relaxation", "port_names": ["left", "right"], "reference_impedance_ohm": 50.,
                       "frequencies_hz": frequencies, "s_parameters": [pairs(matrix) for matrix in matrices]},
            "pole_rates_rad_s": (1 / TIMES).tolist(), "max_absolute_error": 1e-12 * abs(scale)}


class SParameterRationalTests(unittest.TestCase):
    def test_known_real_rc_coefficients_source_identity_and_sample_reconstruction(self):
        req = request()
        before = deepcopy(req)
        out = rational.fit_sparameter_rational(req)
        self.assertEqual(req, before)
        np.testing.assert_allclose(out["model"]["direct"], DIRECT, rtol=0, atol=5e-16)
        np.testing.assert_allclose(out["model"]["residues"], RESIDUES, rtol=0, atol=5e-16)
        self.assertEqual(out["model"]["stability"], "strictly_stable_supplied_real_poles")
        self.assertEqual(out["model"]["causality"], "proper_real_rational_by_construction")
        self.assertEqual(out["model_status"], "experimental")
        self.assertFalse(out["production_qualified"])
        self.assertLess(out["diagnostics"]["max_absolute_error"], 5e-16)
        self.assertLess(out["diagnostics"]["least_squares_optimality_residual"], 1e-15)
        self.assertLess(out["diagnostics"]["conservative_passivity_bound"], 1.)
        for actual, expected in zip(out["reconstructed_network"]["s_parameters"], before["source"]["s_parameters"]):
            np.testing.assert_allclose(values(actual), values(expected), rtol=0, atol=5e-16)
        self.assertEqual(out["source"]["network"], before["source"])
        self.assertEqual(out["source"]["input_digest"], rational.sampling._digest(before["source"]))
        self.assertEqual(out["input_digest"], rational.sampling._digest(before))
        self.assertEqual(out["reconstructed_network"]["frequencies_hz"], before["source"]["frequencies_hz"])
        out["reconstructed_network"]["port_names"][0] = "changed"
        self.assertEqual(out["source"]["network"], before["source"])
        self.assertEqual(req, before)

    def test_state_step_and_independent_numerical_impulse_transform(self):
        out = rational.fit_sparameter_rational(request())
        direct, residues, poles = np.array(out["model"]["direct"]), np.array(out["model"]["residues"]), np.array(out["pole_rates_rad_s"])
        for time in (0., 1e-6, 1e-5, 1e-4, 1e-3):
            # Zero-state unit input gives x=1-exp(-p*t); the direct term
            # supplies the instantaneous response at t=0+.
            actual = direct + sum(r * (-math.expm1(-p*time)) for r, p in zip(residues, poles))
            exact = DIRECT + sum(r * (-math.expm1(-time/tau)) for r, tau in zip(RESIDUES, TIMES))
            np.testing.assert_allclose(actual, exact, rtol=0, atol=8e-16)
        for frequency in (0., 37., 2300.):
            # Independently integrate the causal RC impulse exp(-t/tau)/tau
            # using u=t/tau, not the production frequency-basis calculation.
            transforms = []
            for tau in TIMES:
                omega_tau = 2*math.pi*frequency*tau
                real = quad(lambda u: math.exp(-u)*math.cos(omega_tau*u), 0., 35., epsabs=1e-12, epsrel=1e-12)[0]
                imag = -quad(lambda u: math.exp(-u)*math.sin(omega_tau*u), 0., 35., epsabs=1e-12, epsrel=1e-12)[0]
                transforms.append(real + 1j*imag)
            reference = DIRECT + sum(r*h for r, h in zip(RESIDUES, transforms))
            model = direct + sum(r*p/(p+2j*math.pi*frequency) for r, p in zip(residues, poles))
            np.testing.assert_allclose(model, reference, rtol=0, atol=8e-13)

    def test_active_nonreciprocal_zero_source_and_numeric_scales(self):
        for scale in (4., 1e-150, 1e150):
            out = rational.fit_sparameter_rational(request(scale))
            np.testing.assert_allclose(np.array(out["model"]["direct"])/scale, DIRECT, rtol=0, atol=7e-16)
            np.testing.assert_allclose(np.array(out["model"]["residues"])/scale, RESIDUES, rtol=0, atol=7e-16)
            self.assertGreater(abs(out["model"]["residues"][0][0][1] - out["model"]["residues"][0][1][0]), 0.)
            if scale == 4.:
                self.assertGreater(out["diagnostics"]["sampled_smax_max"], 1.)
                self.assertGreater(out["diagnostics"]["conservative_passivity_bound"], 1.)
        req = request()
        req["source"]["s_parameters"] = [pairs(np.zeros((2, 2))) for _ in req["source"]["frequencies_hz"]]
        out = rational.fit_sparameter_rational(req)
        self.assertEqual(out["diagnostics"]["max_absolute_error"], 0.)
        self.assertEqual(out["diagnostics"]["least_squares_optimality_residual"], 0.)
        self.assertEqual(out["diagnostics"]["conservative_passivity_bound"], 0.)

    def test_rad_per_second_pole_order_and_common_frequency_scaling(self):
        req = request()
        req["pole_rates_rad_s"].reverse()
        out = rational.fit_sparameter_rational(req)
        self.assertEqual(out["pole_rates_rad_s"], req["pole_rates_rad_s"])
        np.testing.assert_allclose(out["model"]["residues"], RESIDUES[::-1], rtol=0, atol=5e-16)
        req = request()
        req["pole_rates_rad_s"] = [p*1e6 for p in req["pole_rates_rad_s"]]
        req["source"]["frequencies_hz"] = [f*1e6 for f in req["source"]["frequencies_hz"]]
        out = rational.fit_sparameter_rational(req)
        np.testing.assert_allclose(out["model"]["residues"], RESIDUES, rtol=0, atol=5e-16)
        req = request(); req["pole_rates_rad_s"] = [p/(2*math.pi) for p in req["pole_rates_rad_s"]]
        with self.assertRaises(rational.SParameterRationalError) as caught:
            rational.fit_sparameter_rational(req)
        self.assertEqual(caught.exception.code, "SPARAMETER_RATIONAL_ERROR_LIMIT")

    def test_missing_pole_and_anti_causal_source_fail_sample_error(self):
        req = request(); req["pole_rates_rad_s"].pop()
        with self.assertRaises(rational.SParameterRationalError) as caught:
            rational.fit_sparameter_rational(req)
        self.assertEqual(caught.exception.code, "SPARAMETER_RATIONAL_ERROR_LIMIT")
        req = request()
        req["source"]["s_parameters"] = [pairs(values(matrix).conj()) for matrix in req["source"]["s_parameters"]]
        with self.assertRaises(rational.SParameterRationalError) as caught:
            rational.fit_sparameter_rational(req)
        self.assertEqual(caught.exception.code, "SPARAMETER_RATIONAL_ERROR_LIMIT")

    def test_rank_condition_and_corrupted_least_squares_failures(self):
        req = request()
        req["source"]["frequencies_hz"] = req["source"]["frequencies_hz"][:2]
        req["source"]["s_parameters"] = req["source"]["s_parameters"][:2]
        req["pole_rates_rad_s"] = [100., 1000., 10000.]
        with self.assertRaises(rational.SParameterRationalError) as caught:
            rational.fit_sparameter_rational(req)
        self.assertEqual(caught.exception.code, "SPARAMETER_RATIONAL_RANK_DEFICIENT")
        req = request(); req["pole_rates_rad_s"] = [5000., 5000.*(1+1e-12)]
        with self.assertRaises(rational.SParameterRationalError) as caught:
            rational.fit_sparameter_rational(req)
        self.assertEqual(caught.exception.code, "SPARAMETER_RATIONAL_ILL_CONDITIONED")
        original = np.linalg.lstsq

        def corrupt(*args, **kwargs):
            solution, residuals, rank, singular_values = original(*args, **kwargs)
            return solution*1.01, residuals, rank, singular_values

        with patch.object(rational.np.linalg, "lstsq", side_effect=corrupt):
            with self.assertRaisesRegex(rational.SParameterRationalError, "optimality"):
                rational.fit_sparameter_rational(request())

    def test_strict_dc_physical_scalars_shapes_and_resources(self):
        mutations = [lambda r: r.update(extra=True), lambda r: r["source"].update(extra=True),
            lambda r: r.update(pole_rates_rad_s=[1., 1.]), lambda r: r.update(pole_rates_rad_s=[-1.]),
            lambda r: r.update(pole_rates_rad_s=[True]), lambda r: r.update(max_absolute_error=0.),
            lambda r: r.update(max_absolute_error=True), lambda r: r.update(max_absolute_error=float("nan")),
            lambda r: r["source"].update(reference_impedance_ohm=True),
            lambda r: r["source"].update(port_names=["same", "same"]),
            lambda r: r["source"]["s_parameters"].pop(),
            lambda r: r["source"]["s_parameters"][0][0][0].update(imag=1e-100),
            lambda r: r["source"]["s_parameters"][1][0][0].update(real=True),
            lambda r: r["source"]["frequencies_hz"].__setitem__(1, 0.)]
        for index, mutate in enumerate(mutations):
            req = request(); mutate(req)
            with self.subTest(case=index), patch.object(rational.np.linalg, "lstsq") as solve:
                with self.assertRaises(rational.SParameterRationalError):
                    rational.fit_sparameter_rational(req)
                solve.assert_not_called()
        for constant in ("_MAX_REQUEST_BYTES", "_MAX_RESULT_BYTES", "_MAX_SOURCE_ENTRIES", "_MAX_WORK"):
            with patch.object(rational, constant, 1), patch.object(rational.np.linalg, "lstsq") as solve:
                with self.assertRaises(rational.SParameterRationalError) as caught:
                    rational.fit_sparameter_rational(request())
                self.assertEqual(caught.exception.code, "SPARAMETER_RATIONAL_RESOURCE_LIMIT")
                solve.assert_not_called()
        req = request()
        req["source"]["frequencies_hz"] = [10**20, 10**20+1]
        req["source"]["s_parameters"] = req["source"]["s_parameters"][:2]
        req["max_absolute_error"] = 1.
        with patch.object(rational.np.linalg, "lstsq") as solve:
            with self.assertRaisesRegex(rational.SParameterRationalError, "grid collapses") as caught:
                rational.fit_sparameter_rational(req)
            self.assertEqual(caught.exception.code, "SPARAMETER_RATIONAL_NUMERICAL_FAILURE")
            solve.assert_not_called()

    def test_cancellation_after_solve_discards_model(self):
        original, completed = np.linalg.lstsq, False

        def finish(*args, **kwargs):
            nonlocal completed
            result = original(*args, **kwargs)
            completed = True
            return result

        with patch.object(rational.np.linalg, "lstsq", side_effect=finish):
            with self.assertRaises(rational.SParameterRationalError) as caught:
                rational.fit_sparameter_rational(request(), cancel_check=lambda: completed)
            self.assertEqual(caught.exception.code, "SPARAMETER_RATIONAL_CANCELLED")
        self.assertTrue(completed)


if __name__ == "__main__":
    unittest.main()
