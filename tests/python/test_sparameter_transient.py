# SPDX-License-Identifier: Apache-2.0
"""Original augmented-state exponential and high-precision PWL references."""
from copy import deepcopy
from decimal import Decimal, localcontext
import math
import unittest
from unittest.mock import patch

import numpy as np
from scipy.linalg import expm

from python.spike_core import sparameter_transient as transient
from tests.python.test_sparameter_rational import request as multi_fit, DIRECT, RESIDUES


def one_fit(pole=5., direct=.1, residue=.7):
    factors = (.1, .5) if pole > 1e306 else (1., 10.)
    frequencies = [0.] + [pole/(2*math.pi)*factor for factor in factors]
    values = [direct + residue/(1+2j*math.pi*f/pole) for f in frequencies]
    return {"contract": "spike/sparameter-rational-fit-request/v1",
            "source": {"id": "single-rc", "port_names": ["input"], "reference_impedance_ohm": 50.,
                       "frequencies_hz": frequencies, "s_parameters": [[[ {"real": z.real, "imag": z.imag} ]] for z in values]},
            "pole_rates_rad_s": [pole], "max_absolute_error": 1e-12}


def wave(port, times, values):
    return {"port_name": port, "points": [{"time_s": t, "value_sqrt_w": a} for t, a in zip(times, values)]}


def request():
    return {"contract": transient.REQUEST_CONTRACT, "fit_request": one_fit(),
            "incident_waves": [wave("input", [0., .2, .6, 1.], [0., 1., 1., 0.])],
            "output_times_s": [0., .05, .2, .31, .6, .85, 1.]}


def reference_states(req):
    """Integrate augmented [x,a,slope] by a generic matrix exponential.

    x'=-p*x+p*a, a'=slope, slope'=0. No exponential endpoint weights or
    production helper appear in this oracle. Every knot/output is visited.
    """
    ports = req["fit_request"]["source"]["port_names"]
    poles = req["fit_request"]["pole_rates_rad_s"]
    waveforms = {w["port_name"]: w["points"] for w in req["incident_waves"]}
    grid = sorted(set(req["output_times_s"]) | {p["time_s"] for w in req["incident_waves"] for p in w["points"]})
    state = np.zeros((len(poles), len(ports)))
    states = {0.: state.copy()}
    for start, end in zip(grid, grid[1:]):
        for j, port in enumerate(ports):
            points = waveforms[port]
            index = next(i for i in range(len(points)-1) if points[i]["time_s"] <= start < points[i+1]["time_s"])
            p0, p1 = points[index:index+2]
            slope = (p1["value_sqrt_w"]-p0["value_sqrt_w"])/(p1["time_s"]-p0["time_s"])
            a0 = p0["value_sqrt_w"] + slope*(start-p0["time_s"])
            for k, pole in enumerate(poles):
                generator = np.array([[-pole, pole, 0.], [0., 0., 1.], [0., 0., 0.]])
                state[k, j] = (expm(generator*(end-start)) @ [state[k, j], a0, slope])[0]
        states[end] = state.copy()
    return states


class RationalNetworkTransientTests(unittest.TestCase):
    def test_one_pole_ramp_hold_against_augmented_matrix_exponential(self):
        req = request(); original = deepcopy(req)
        out = transient.run_rational_network_transient(req)
        states = reference_states(req)
        for point in out["points"]:
            time = point["time_s"]
            a = point["incident_wave_sqrt_w_by_port"]["input"]
            expected = .1*a + .7*states[time][0, 0]
            self.assertAlmostEqual(point["outgoing_wave_sqrt_w_by_port"]["input"], expected, delta=2e-15)
        np.testing.assert_allclose(out["final_state_sqrt_w"], states[1.], rtol=0, atol=1e-15)
        self.assertEqual(req, original)
        self.assertEqual(out["fit_result"]["input_digest"], transient.rational.sampling._digest(req["fit_request"]))
        self.assertEqual(out["input_digest"], transient.rational.sampling._digest(original))
        self.assertEqual(out["diagnostics"]["integration_method"], "exact_piecewise_linear_exponential")
        self.assertEqual(out["diagnostics"]["interval_count"], 6)
        self.assertFalse(out["production_qualified"])

    def test_multiport_asynchronous_inputs_superposition_and_voltage_current_identity(self):
        req = {"contract": transient.REQUEST_CONTRACT, "fit_request": multi_fit(),
               "incident_waves": [wave("right", [0., .00017, .0006, .001], [-.2, .8, -.3, .1]),
                                  wave("left", [0., .0001, .00035, .001], [.3, 1., .4, -.1])],
               "output_times_s": [0., .00005, .0001, .00017, .00035, .0006, .0008, .001]}
        out = transient.run_rational_network_transient(req)
        self.assertEqual(out["port_names"], ["left", "right"])
        self.assertEqual(out["incident_waves"], req["incident_waves"])
        reference = reference_states(req)
        for point in out["points"]:
            a = np.array([point["incident_wave_sqrt_w_by_port"][p] for p in out["port_names"]])
            expected = DIRECT @ a + np.einsum("kij,kj->i", RESIDUES, reference[point["time_s"]])
            b = np.array([point["outgoing_wave_sqrt_w_by_port"][p] for p in out["port_names"]])
            np.testing.assert_allclose(b, expected, rtol=0, atol=2e-15)
            for port in out["port_names"]:
                incident = point["incident_wave_sqrt_w_by_port"][port]
                outgoing = point["outgoing_wave_sqrt_w_by_port"][port]
                voltage, current = point["port_voltage_v_by_port"][port], point["port_current_a_by_port"][port]
                self.assertAlmostEqual(voltage, math.sqrt(50.)*(incident+outgoing), delta=1e-14)
                self.assertAlmostEqual(current, (incident-outgoing)/math.sqrt(50.), delta=1e-15)
                self.assertAlmostEqual(voltage*current, incident**2-outgoing**2, delta=1e-15)
        components = []
        for zero_port in ("left", "right"):
            component = deepcopy(req)
            for raw in component["incident_waves"]:
                if raw["port_name"] == zero_port:
                    for point in raw["points"]: point["value_sqrt_w"] = 0.
            components.append(transient.run_rational_network_transient(component))
        for index, point in enumerate(out["points"]):
            for port in out["port_names"]:
                total = sum(part["points"][index]["outgoing_wave_sqrt_w_by_port"][port] for part in components)
                self.assertAlmostEqual(point["outgoing_wave_sqrt_w_by_port"][port], total, delta=2e-16)

    def test_nonzero_initial_step_feedthrough_and_exact_relaxation(self):
        req = request()
        req["incident_waves"] = [wave("input", [0., 1.], [2., 2.])]
        out = transient.run_rational_network_transient(req)
        for point in out["points"]:
            expected = .2 + 1.4*(-math.expm1(-5*point["time_s"]))
            self.assertAlmostEqual(point["outgoing_wave_sqrt_w_by_port"]["input"], expected, delta=2e-15)
        self.assertAlmostEqual(out["points"][0]["outgoing_wave_sqrt_w_by_port"]["input"], .2, delta=1e-15)

    def test_small_large_and_overflowed_rate_time_products(self):
        for z in (1e-12, 1e-7, .001, .1, 100.):
            duration = z/5.
            start, end = (0., 1.) if z < 1 else (1e200, 0.)
            req = request(); req["incident_waves"] = [wave("input", [0., duration], [start, end])]
            req["output_times_s"] = [duration]
            out = transient.run_rational_network_transient(req)
            with localcontext() as ctx:
                ctx.prec = 80
                zd = Decimal.from_float(5.)*Decimal.from_float(duration)
                q = (-zd).exp(); w = 1-q
                expected = float((w/zd-q)*Decimal.from_float(start) + (1-w/zd)*Decimal.from_float(end))
            self.assertAlmostEqual(out["final_state_sqrt_w"][0][0]/expected, 1., delta=4e-15)
        for pole, duration, amplitude in ((5., 1e308, 1e308), (1e308, 1e308, 1e308)):
            req = request(); req["fit_request"] = one_fit(pole)
            req["incident_waves"] = [wave("input", [0., duration], [amplitude, 0.])]
            req["output_times_s"] = [duration]
            out = transient.run_rational_network_transient(req)
            # exp(-p*h) is far below float range; Decimal retains a0/(p*h)
            # even when the floating-point product overflows or inverse is0.
            with localcontext() as ctx:
                ctx.prec = 80
                expected = float(Decimal.from_float(amplitude)/(Decimal.from_float(pole)*Decimal.from_float(duration)))
            self.assertAlmostEqual(out["final_state_sqrt_w"][0][0]/expected, 1., delta=4e-15)

    def test_output_grid_invariance_and_final_horizon_without_final_output(self):
        req = request()
        coarse = transient.run_rational_network_transient(req)
        refined = deepcopy(req)
        refined["output_times_s"] = sorted(set(req["output_times_s"]) | {i/100 for i in range(101)})
        fine = transient.run_rational_network_transient(refined)
        by_time = {point["time_s"]: point for point in fine["points"]}
        for point in coarse["points"]:
            self.assertAlmostEqual(point["outgoing_wave_sqrt_w_by_port"]["input"],
                                   by_time[point["time_s"]]["outgoing_wave_sqrt_w_by_port"]["input"], delta=2e-15)
        np.testing.assert_allclose(coarse["final_state_sqrt_w"], fine["final_state_sqrt_w"], rtol=0, atol=1e-15)
        req["output_times_s"] = [0.]
        only_initial = transient.run_rational_network_transient(req)
        np.testing.assert_allclose(only_initial["final_state_sqrt_w"], coarse["final_state_sqrt_w"], rtol=0, atol=1e-15)
        self.assertEqual(len(only_initial["points"]), 1)

    def test_strict_waveform_coverage_horizon_times_and_resources_before_fit(self):
        mutations = [lambda r: r.update(extra=True), lambda r: r.update(incident_waves=[]),
            lambda r: r["incident_waves"][0].update(port_name="unknown"),
            lambda r: r["incident_waves"][0]["points"][0].update(time_s=.01),
            lambda r: r["incident_waves"][0]["points"][1].update(time_s=0.),
            lambda r: r["incident_waves"][0]["points"][1].update(value_sqrt_w=True),
            lambda r: r["incident_waves"][0]["points"][1].update(value_sqrt_w=float("inf")),
            lambda r: r.update(output_times_s=[-.01]), lambda r: r.update(output_times_s=[2.]),
            lambda r: r.update(output_times_s=[0., 0.]), lambda r: r.update(output_times_s=[True])]
        for i, mutate in enumerate(mutations):
            req = request(); mutate(req)
            with self.subTest(case=i), patch.object(transient.rational, "fit_sparameter_rational") as solve:
                with self.assertRaises(transient.SParameterTransientError):
                    transient.run_rational_network_transient(req)
                solve.assert_not_called()
        req = request(); req["fit_request"] = multi_fit()
        req["incident_waves"] = [wave("left", [0., 1.], [0., 1.]), wave("right", [0., .9], [0., 1.])]
        with self.assertRaisesRegex(transient.SParameterTransientError, "common final time"):
            transient.run_rational_network_transient(req)
        for constant in ("_MAX_REQUEST_BYTES", "_MAX_RESULT_BYTES", "_MAX_INTERVALS", "_MAX_WORK"):
            with patch.object(transient, constant, 1), patch.object(transient.rational, "fit_sparameter_rational") as solve:
                with self.assertRaises(transient.SParameterTransientError) as caught:
                    transient.run_rational_network_transient(request())
                self.assertEqual(caught.exception.code, "SPARAMETER_TRANSIENT_RESOURCE_LIMIT")
                solve.assert_not_called()

    def test_union_precision_collapse_fraction_collapse_and_rate_time_underflow(self):
        req = request()
        req["incident_waves"] = [wave("input", [0, 10**20, 10**20+100000], [0., 1., 0.])]
        req["output_times_s"] = [10**20+1]
        with patch.object(transient.rational, "fit_sparameter_rational") as solve:
            with self.assertRaisesRegex(transient.SParameterTransientError, "union.*collapses"):
                transient.run_rational_network_transient(req)
            solve.assert_not_called()
        req = request(); req["incident_waves"] = [wave("input", [0., 1e300], [0., 1.])]
        req["output_times_s"] = [1e-300]
        with self.assertRaisesRegex(transient.SParameterTransientError, "waveform fraction"):
            transient.run_rational_network_transient(req)
        req = request(); req["fit_request"] = one_fit(1e-200)
        req["incident_waves"] = [wave("input", [0., 1e-200], [0., 1.])]
        req["output_times_s"] = [1e-200]
        with self.assertRaisesRegex(transient.SParameterTransientError, "product underflows"):
            transient.run_rational_network_transient(req)

    def test_cancellation_and_corrupt_fitted_identity_discard_trajectory(self):
        original, completed = transient._advance, 0

        def finish(*args):
            nonlocal completed
            result = original(*args)
            completed += 1
            return result

        with patch.object(transient, "_advance", side_effect=finish):
            with self.assertRaises(transient.SParameterTransientError) as caught:
                transient.run_rational_network_transient(request(), cancel_check=lambda: completed >= 2)
            self.assertEqual(caught.exception.code, "SPARAMETER_TRANSIENT_CANCELLED")
        self.assertEqual(completed, 2)
        with patch.object(transient.rational, "fit_sparameter_rational", return_value={}) as solve:
            with self.assertRaisesRegex(transient.SParameterTransientError, "identity mismatch"):
                transient.run_rational_network_transient(request())
            solve.assert_called_once()


if __name__ == "__main__":
    unittest.main()
