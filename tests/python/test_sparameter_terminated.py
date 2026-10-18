# SPDX-License-Identifier: Apache-2.0
"""Original physical RC and nodal-divider references, independent of wave closure."""
from copy import deepcopy
import math
import unittest
from unittest.mock import patch

import numpy as np
from scipy.linalg import expm

from python.spike_core import sparameter_terminated as terminated
from python.spike_core import sparameter_transient as prescribed
from tests.python.test_sparameter_transient import one_fit, wave


def termination(port="input", resistance=25., times=(0., .2, .6, 1.), values=(0., 2., 2., -1.)):
    return {"port_name": port, "resistance_ohm": resistance,
            "voltage_points": [{"time_s": t, "voltage_v": v} for t, v in zip(times, values)]}


def request():
    # Z0=50 and C=.004 F gives p=5/s, S=(p-s)/(p+s).
    return {"contract": terminated.REQUEST_CONTRACT, "fit_request": one_fit(direct=-1., residue=2.),
            "terminations": [termination()], "output_times_s": [0., .05, .2, .31, .6, .85, 1.]}


def physical_rc(req, capacitance=.004):
    """Physical V'= (Vs-V)/(Rs*C), with augmented [V,Vs,slope]."""
    term = req["terminations"][0]
    tau = term["resistance_ohm"]*capacitance
    knots = term["voltage_points"]
    grid = sorted(set(req["output_times_s"]) | {p["time_s"] for p in knots})
    voltage, results = 0., {0.: 0.}
    generator = np.array([[-1/tau, 1/tau, 0.], [0., 0., 1.], [0., 0., 0.]])
    for left, right in zip(grid, grid[1:]):
        index = next(i for i in range(len(knots)-1) if knots[i]["time_s"] <= left < knots[i+1]["time_s"])
        start, end = knots[index:index+2]
        slope = (end["voltage_v"]-start["voltage_v"])/(end["time_s"]-start["time_s"])
        source = start["voltage_v"]+slope*(left-start["time_s"])
        voltage = (expm((right-left)*generator) @ [voltage, source, slope])[0]
        results[right] = voltage
    return results


class TerminatedTests(unittest.TestCase):
    def test_physical_capacitor_ramp_hold_signed_source_and_identity(self):
        req = request(); before = deepcopy(req)
        result = terminated.run_terminated_network_transient(req)
        reference = physical_rc(req)
        self.assertEqual(req, before)
        self.assertEqual(result["fit_result"]["source"]["network"], req["fit_request"]["source"])
        for point in result["points"]:
            voltage = point["port_voltage_v_by_port"]["input"]
            current = point["port_current_a_by_port"]["input"]
            source = point["source_voltage_v_by_port"]["input"]
            self.assertAlmostEqual(voltage, reference[point["time_s"]], delta=3e-13)
            self.assertAlmostEqual(voltage+25*current, source, delta=3e-13)
            a, b = (point[key]["input"] for key in ("incident_wave_sqrt_w_by_port", "outgoing_wave_sqrt_w_by_port"))
            self.assertAlmostEqual(voltage*current, a*a-b*b, delta=1e-14)
        self.assertLess(result["diagnostics"]["maximum_boundary_relative_residual"], 1e-13)

    def test_step_initial_feedthrough_and_matched_equivalence(self):
        req = request(); req["terminations"] = [termination(resistance=50., times=(0., 1.), values=(2., 2.))]
        result = terminated.run_terminated_network_transient(req)
        incident = {"contract": prescribed.REQUEST_CONTRACT, "fit_request": req["fit_request"],
                    "incident_waves": [wave("input", [0., 1.], [1/math.sqrt(50)]*2)], "output_times_s": req["output_times_s"]}
        expected = prescribed.run_rational_network_transient(incident)
        for actual, other in zip(result["points"], expected["points"]):
            self.assertAlmostEqual(actual["port_voltage_v_by_port"]["input"], 2*(-math.expm1(-actual["time_s"]/.2)), delta=1e-13)
            for key in ("incident_wave_sqrt_w_by_port", "outgoing_wave_sqrt_w_by_port", "port_current_a_by_port"):
                self.assertAlmostEqual(actual[key]["input"], other[key]["input"], delta=1e-14)
        active = request(); active["fit_request"] = one_fit(direct=1.2, residue=.3)
        active["terminations"] = [termination(resistance=50., times=(0., 1.), values=(2., 2.))]
        output = terminated.run_terminated_network_transient(active)
        self.assertGreater(output["fit_result"]["diagnostics"]["sampled_smax_max"], 1.)
        self.assertAlmostEqual(output["points"][0]["outgoing_wave_sqrt_w_by_port"]["input"], 1.2/math.sqrt(50), delta=1e-14)

    def test_through_two_port_simultaneous_thevenins_and_order(self):
        req = request(); source = req["fit_request"]["source"]
        source["port_names"] = ["left", "right"]
        matrix = [[{"real": 0., "imag": 0.}, {"real": 1., "imag": 0.}],
                  [{"real": 1., "imag": 0.}, {"real": 0., "imag": 0.}]]
        source["s_parameters"] = [deepcopy(matrix) for _ in source["frequencies_hz"]]
        req["terminations"] = [termination("right", 90., (0., .4, 1.), (1., -2., 0.)),
                               termination("left", 10., (0., .2, 1.), (2., 1., 3.))]
        result = terminated.run_terminated_network_transient(req)
        self.assertEqual(result["port_names"], ["left", "right"])
        for row in result["points"]:
            supplied = row["source_voltage_v_by_port"]
            expected = (supplied["left"]/10+supplied["right"]/90)/(1/10+1/90)
            for port, resistance in (("left", 10), ("right", 90)):
                self.assertAlmostEqual(row["port_voltage_v_by_port"][port], expected, delta=1e-13)
                self.assertAlmostEqual(row["port_current_a_by_port"][port], (supplied[port]-expected)/resistance, delta=1e-14)

    def test_output_grid_invariance(self):
        req = request(); baseline = terminated.run_terminated_network_transient(req)
        req["output_times_s"] = sorted(set(req["output_times_s"]+[.001, .11, .42, .923]))
        refined = terminated.run_terminated_network_transient(req)
        lookup = {p["time_s"]: p for p in refined["points"]}
        for point in baseline["points"]:
            self.assertAlmostEqual(point["port_voltage_v_by_port"]["input"], lookup[point["time_s"]]["port_voltage_v_by_port"]["input"], delta=3e-13)
        np.testing.assert_allclose(baseline["final_state_sqrt_w"], refined["final_state_sqrt_w"], rtol=1e-13, atol=1e-14)

    def test_loop_singular_unstable_marginal_and_unresolved_cancellation(self):
        cases = [(one_fit(direct=-1., residue=2.), 0., "ILL_CONDITIONED"),
                 (one_fit(direct=0., residue=2.), 350., "UNSTABLE_CLOSED_SYSTEM"),
                 (one_fit(direct=0., residue=2.), 150., "UNSTABLE_CLOSED_SYSTEM"),
                 (one_fit(direct=-1., residue=2.), 1e15, "UNSTABLE_CLOSED_SYSTEM")]
        for fit, resistance, code in cases:
            req = request(); req["fit_request"] = fit; req["terminations"][0]["resistance_ohm"] = resistance
            with self.subTest(resistance=resistance), self.assertRaises(terminated.SParameterTerminatedError) as caught:
                terminated.run_terminated_network_transient(req)
            self.assertTrue(caught.exception.code.endswith(code), caught.exception.code)

    def test_malformed_inputs_and_precision_collapse(self):
        for mutation in ("bool", "infinite", "negative", "name", "field", "horizon", "duplicate", "time_collapse", "fraction"):
            req = request(); term = req["terminations"][0]
            if mutation == "bool": term["resistance_ohm"] = True
            elif mutation == "infinite": term["voltage_points"][0]["voltage_v"] = float("inf")
            elif mutation == "negative": term["resistance_ohm"] = -1
            elif mutation == "name": term["port_name"] = "missing"
            elif mutation == "field": term["extra"] = 1
            elif mutation == "horizon": req["output_times_s"] = [2.]
            elif mutation == "duplicate": req["output_times_s"] = [.2, .2]
            elif mutation == "time_collapse":
                term["voltage_points"] = [{"time_s": t, "voltage_v": 1.} for t in (0, 10**20, 10**20+1)]
                req["output_times_s"] = [0]
            else:
                term["voltage_points"] = [{"time_s": t, "voltage_v": 1.} for t in (0, 1e300)]
                req["output_times_s"] = [1e-300]
            with self.subTest(mutation=mutation), self.assertRaises(terminated.SParameterTerminatedError):
                terminated.run_terminated_network_transient(req)

    def test_resource_preflight_generator_limits_and_cancellation(self):
        req = request(); req["output_times_s"] = list(np.linspace(0., 1., 1025))
        with patch.object(terminated.rational, "fit_sparameter_rational", side_effect=AssertionError("fit must not run")):
            with self.assertRaisesRegex(terminated.SParameterTerminatedError, "1024"):
                terminated.run_terminated_network_transient(req)
        req = request(); req["output_times_s"] = [0.]+[i*i/40000 for i in range(1, 201)]
        with self.assertRaisesRegex(terminated.SParameterTerminatedError, "128"):
            terminated.run_terminated_network_transient(req)
        req = request(); req["terminations"] = [termination(times=(0., 1e9), values=(1., 1.))]; req["output_times_s"] = [0., 1e9]
        with self.assertRaisesRegex(terminated.SParameterTerminatedError, "generator"):
            terminated.run_terminated_network_transient(req)
        for cancel_at in (1, 10, 20):
            polls = []
            def cancel():
                polls.append(None)
                return len(polls) >= cancel_at
            with self.subTest(cancel_at=cancel_at), self.assertRaises(terminated.SParameterTerminatedError) as caught:
                terminated.run_terminated_network_transient(request(), cancel_check=cancel)
            self.assertIn("CANCELLED", caught.exception.code)
        with patch.object(terminated, "_MAX_WORK", 1):
            with self.assertRaisesRegex(terminated.SParameterTerminatedError, "Aggregate"):
                terminated.run_terminated_network_transient(request())

    def test_extreme_normalization_forcing_and_interval_underflow_reject(self):
        req = request(); req["fit_request"] = one_fit(pole=1e-300, direct=-1e100, residue=0.)
        req["fit_request"]["max_absolute_error"] = 1e90
        req["terminations"][0]["resistance_ohm"] = 0.
        with self.assertRaisesRegex(terminated.SParameterTerminatedError, "forcing underflows"):
            terminated.run_terminated_network_transient(req)
        req = request(); req["fit_request"] = one_fit(pole=1e-200, direct=-1., residue=2.)
        req["terminations"] = [termination(times=(0., 1e-200), values=(1., 1.))]
        req["output_times_s"] = [0., 1e-200]
        with self.assertRaisesRegex(terminated.SParameterTerminatedError, "coefficients underflow"):
            terminated.run_terminated_network_transient(req)
        req = request(); req["terminations"] = [termination(times=(0., 1.), values=(5e-324, 5e-324))]
        with self.assertRaisesRegex(terminated.SParameterTerminatedError, "normalized source"):
            terminated.run_terminated_network_transient(req)


if __name__ == "__main__":
    unittest.main()
