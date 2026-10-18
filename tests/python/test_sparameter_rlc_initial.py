# SPDX-License-Identifier: Apache-2.0
"""Original physical initial-value and local-time continuation references.

Acceptance: voltage/current2e-10 SI, derivatives2e-8 SI, energy1e-9 J.
"""
from copy import deepcopy
import math
import unittest
from unittest.mock import patch

import numpy as np
from scipy.integrate import quad
from scipy.linalg import expm

from python.spike_core import sparameter_rlc_initial as initial
from tests.python.test_sparameter_rlc_terminated import request as zero_request, term


def request(resistance=10., reference=50., voltage=-.7, current=.12):
    req = zero_request(resistance=resistance, reference=reference)
    req["contract"] = initial.REQUEST_CONTRACT
    req["initial_state"] = {"contract": initial.STATE_CONTRACT,
                            "fit_request_digest": initial.rlc.rational.sampling._digest(req["fit_request"]),
                            "fit_state_sqrt_w": [[0.]], "inductor_current_a_by_port": {"input": current},
                            "capacitor_voltage_v_by_port": {"input": voltage}}
    return req


def analytic_loaded(t, resistance, voltage=-.7, current=.12, source=2., capacitance=.004, inductance=1.):
    g = .01; alpha = .5*(resistance/inductance+g/capacitance)
    omega2 = (1+resistance*g)/(inductance*capacitance); steady = source/(1+resistance*g)
    a, d0 = voltage-steady, (current-g*voltage)/capacitance
    if abs(alpha*alpha-omega2) < 1e-12*omega2:
        b = d0+alpha*a; transient = math.exp(-alpha*t)*(a+b*t)
        derivative = math.exp(-alpha*t)*(b-alpha*(a+b*t))
    elif alpha*alpha < omega2:
        omega = math.sqrt(omega2-alpha*alpha); b = (d0+alpha*a)/omega
        transient = math.exp(-alpha*t)*(a*math.cos(omega*t)+b*math.sin(omega*t))
        derivative = math.exp(-alpha*t)*((-alpha*a+omega*b)*math.cos(omega*t)+(-alpha*b-omega*a)*math.sin(omega*t))
    else:
        delta = math.sqrt(alpha*alpha-omega2); r1, r2 = -alpha+delta, -alpha-delta
        c1, c2 = (d0-r2*a)/(r1-r2), (r1*a-d0)/(r1-r2)
        transient = c1*math.exp(r1*t)+c2*math.exp(r2*t)
        derivative = r1*c1*math.exp(r1*t)+r2*c2*math.exp(r2*t)
    v = steady+transient; i = g*v+capacitance*derivative
    return v, i, derivative, (source-v-resistance*i)/inductance


def memory_request(reference=50.):
    req = request(reference=reference); fit = req["fit_request"]; source = fit["source"]
    fit["pole_rates_rad_s"] = [reference/(2*(1+reference*.01))]
    source["frequencies_hz"] = [0., .1, 1., 5., 20., 100.]
    samples = []
    for f in source["frequencies_hz"]:
        if f == 0: scattering = complex(-1.)
        else:
            y = .01+1/(2j*math.pi*f*2.)
            scattering = (1-reference*y)/(1+reference*y)
        samples.append([[{"real": scattering.real, "imag": scattering.imag}]])
    source["s_parameters"] = samples
    req["initial_state"]["fit_request_digest"] = initial.rlc.rational.sampling._digest(fit)
    # Inet=G*V+2*x/sqrt(Z0), so x0=.5*sqrt(Z0)*In0.
    req["initial_state"]["fit_state_sqrt_w"] = [[.5*math.sqrt(reference)*(-.08)]]
    return req


def reslice(req, left, right):
    result = deepcopy(req)
    for source in result["terminations"]:
        original = source["voltage_points"]
        times = [p["time_s"] for p in original]; values = [p["voltage_v"] for p in original]
        retained = [left]+[t for t in times if left < t < right]+[right]
        source["voltage_points"] = [{"time_s": t-left, "voltage_v": float(np.interp(t, times, values))} for t in retained]
    result["output_times_s"] = [0.]+[t-left for t in req["output_times_s"] if left < t < right]+[right-left]
    return result


class InitialRlcTests(unittest.TestCase):
    def test_charged_energized_loaded_rlc_analytic_free_and_forced_damping(self):
        for resistance in (10., (5+math.sqrt(4000))/2, 80.):
            for source in (0., 2.):
                req = request(resistance); before = deepcopy(req)
                for point in req["terminations"][0]["voltage_points"]: point["voltage_v"] = source
                before = deepcopy(req); result = initial.run_initialized_rlc_network_transient(req)
                self.assertEqual(req, before); self.assertEqual(result["initial_state"], req["initial_state"])
                for row in result["points"]:
                    v, i, vd, ider = analytic_loaded(row["time_s"], resistance, source=source)
                    for field, value, tolerance in (("port_voltage_v", v, 2e-10), ("source_current_a", i, 2e-10),
                                                    ("capacitor_voltage_derivative_v_per_s", vd, 2e-8), ("inductor_current_derivative_a_per_s", ider, 2e-8)):
                        self.assertAlmostEqual(row[field+"_by_port"]["input"], value, delta=tolerance)

    def test_nonzero_fit_memory_physical_initial_value_and_energy(self):
        req = memory_request()
        result = initial.run_initialized_rlc_network_transient(req)
        self.assertGreater(abs(result["fit_result"]["model"]["residues"][0][0][0]), 1.)
        generator = np.array([[-2.5, 250., -250., 0.], [-1., -10., 0., 2.], [.5, 0., 0., 0.], [0., 0., 0., 0.]])
        def physical(t): return (expm(t*generator)@[-.7, .12, -.08, 1.])[:3]
        for row in result["points"]:
            v, i, winding = physical(row["time_s"]); net = .01*v+winding
            expected = {"port_voltage_v": v, "source_current_a": i, "port_current_a": net,
                        "capacitor_voltage_derivative_v_per_s": (i-net)/.004, "inductor_current_derivative_a_per_s": 2-v-10*i}
            for field, value in expected.items():
                self.assertAlmostEqual(row[field+"_by_port"]["input"], value, delta=2e-8 if "derivative" in field else 2e-10)
        work = quad(lambda t: 2*physical(t)[1], 0., 1., epsabs=1e-12)[0]
        heat = quad(lambda t: 10*physical(t)[1]**2+.01*physical(t)[0]**2, 0., 1., epsabs=1e-12)[0]
        initial_energy = .5*.004*.7**2+.5*.12**2+(-.08)**2
        last = result["points"][-1]
        winding = last["port_current_a_by_port"]["input"]-.01*last["port_voltage_v_by_port"]["input"]
        final = last["capacitor_energy_j_by_port"]["input"]+last["inductor_energy_j_by_port"]["input"]+winding**2
        self.assertAlmostEqual(initial_energy+work, heat+final, delta=1e-9)

    def test_pwl_restart_at_knot_and_inside_ramp_and_actual_horizon(self):
        req = memory_request(); req["terminations"] = [term(times=(0., .1, .35, .7, 1.), values=(0., 2., 2., -1., .5))]
        req["output_times_s"] = [0., .05, .1, .23, .35, .5, .7, .9, 1.]
        full = initial.run_initialized_rlc_network_transient(req)
        for split in (.35, .5, .47):
            first = initial.run_initialized_rlc_network_transient(reslice(req, 0., split))
            second_req = reslice(req, split, 1.); second_req["initial_state"] = first["restart_state"]
            second = initial.run_initialized_rlc_network_transient(second_req)
            self.assertAlmostEqual(second["points"][0]["port_voltage_v_by_port"]["input"], first["restart_state"]["capacitor_voltage_v_by_port"]["input"], delta=2e-10)
            self.assertAlmostEqual(second["points"][0]["source_current_a_by_port"]["input"], first["restart_state"]["inductor_current_a_by_port"]["input"], delta=2e-10)
            for row in second["points"]:
                time = row["time_s"]+split
                # .47 is deliberately absent from the original observation grid;
                # its initial value is checked against the supplied state above.
                if row["time_s"] == 0. and split == .47:
                    continue
                original = min(full["points"], key=lambda p: abs(p["time_s"]-time))
                self.assertAlmostEqual(original["time_s"], time, delta=1e-14)
                for field in ("port_voltage_v", "port_current_a", "source_current_a"):
                    self.assertAlmostEqual(row[field+"_by_port"]["input"], original[field+"_by_port"]["input"], delta=2e-10)
            np.testing.assert_allclose(second["restart_state"]["fit_state_sqrt_w"], full["restart_state"]["fit_state_sqrt_w"], rtol=1e-11, atol=2e-12)
            for field in ("inductor_current_a_by_port", "capacitor_voltage_v_by_port"):
                self.assertAlmostEqual(second["restart_state"][field]["input"], full["restart_state"][field]["input"], delta=2e-10)
        short_observations = deepcopy(req); short_observations["output_times_s"] = [0., .1]
        horizon = initial.run_initialized_rlc_network_transient(short_observations)
        self.assertAlmostEqual(horizon["restart_state"]["capacitor_voltage_v_by_port"]["input"], full["restart_state"]["capacitor_voltage_v_by_port"]["input"], delta=2e-10)
        self.assertGreater(abs(horizon["restart_state"]["capacitor_voltage_v_by_port"]["input"]-horizon["points"][-1]["port_voltage_v_by_port"]["input"]), .01)

    def test_multiple_state_port_order_with_coupled_physical_reference(self):
        req = request(); conductance = np.array([[.02, -.004], [-.004, .01]])
        s = np.linalg.solve(np.eye(2)+50*conductance, np.eye(2)-50*conductance)
        source = req["fit_request"]["source"]; source["port_names"] = ["left", "right"]
        matrix = [[{"real": float(v), "imag": 0.} for v in row] for row in s]
        source["s_parameters"] = [deepcopy(matrix) for _ in source["frequencies_hz"]]
        req["terminations"] = [term("right", 25., 2., .009, values=(-1., -1.)), term("left", 10., 1., .004)]
        req["initial_state"].update(fit_request_digest=initial.rlc.rational.sampling._digest(req["fit_request"]), fit_state_sqrt_w=[[0., 0.]],
                                     inductor_current_a_by_port={"right": .13, "left": -.1}, capacitor_voltage_v_by_port={"right": -.4, "left": .7})
        result = initial.run_initialized_rlc_network_transient(req)
        generator = np.zeros((6, 6)); capacitance = np.array([.004, .009]); inductance = np.array([1., 2.])
        generator[:2, :2] = -conductance/capacitance[:, None]; generator[:2, 2:4] = np.diag(1/capacitance)
        generator[2:4, :2] = -np.diag(1/inductance); generator[2:4, 2:4] = -np.diag(np.array([10., 25.])/inductance)
        generator[2:4, 4:] = np.diag(1/inductance)
        for row in result["points"]:
            expected = expm(row["time_s"]*generator)@[.7, -.4, -.1, .13, 2., -1.]
            for j, port in enumerate(("left", "right")):
                self.assertAlmostEqual(row["port_voltage_v_by_port"][port], expected[j], delta=2e-10)
                self.assertAlmostEqual(row["source_current_a_by_port"][port], expected[2+j], delta=2e-10)
        self.assertEqual(list(result["restart_state"]["inductor_current_a_by_port"]), ["left", "right"])
        self.assertEqual(list(result["restart_state"]["capacitor_voltage_v_by_port"]), ["left", "right"])

    def test_zero_initial_v2_equals_unchanged_v1_and_keyword_is_not_public(self):
        old = zero_request(); baseline = initial.rlc.run_rlc_network_transient(old)
        req = request(voltage=0., current=0.); result = initial.run_initialized_rlc_network_transient(req)
        for key in baseline:
            if key not in ("contract", "input_digest", "limitations"):
                self.assertEqual(result[key], baseline[key])
        self.assertIn("Zero initial", baseline["limitations"][0])
        self.assertNotIn("Zero initial", result["limitations"][0])
        with self.assertRaises(TypeError): initial.rlc.run_rlc_network_transient(old, initial_state=[0., 0., 0.])

    def test_reference_and_physical_time_scaling(self):
        baseline = initial.run_initialized_rlc_network_transient(memory_request())
        for reference in (1., 25., 100., 1000.):
            result = initial.run_initialized_rlc_network_transient(memory_request(reference))
            for a, b in zip(baseline["points"], result["points"]):
                for field in ("port_voltage_v", "source_current_a", "port_current_a"):
                    self.assertAlmostEqual(a[field+"_by_port"]["input"], b[field+"_by_port"]["input"], delta=2e-10)
        baseline = initial.run_initialized_rlc_network_transient(request())
        req = request(); req["terminations"][0]["inductance_h"] *= .001; req["terminations"][0]["capacitance_f"] *= .001
        req["terminations"][0]["voltage_points"][-1]["time_s"] = .001; req["output_times_s"] = [t*.001 for t in req["output_times_s"]]
        result = initial.run_initialized_rlc_network_transient(req)
        for a, b in zip(baseline["points"], result["points"]):
            self.assertAlmostEqual(a["port_voltage_v_by_port"]["input"], b["port_voltage_v_by_port"]["input"], delta=2e-10)
            self.assertAlmostEqual(a["source_current_a_by_port"]["input"], b["source_current_a_by_port"]["input"], delta=2e-10)

    def test_bad_state_binding_maps_dimensions_precision_and_budget_before_fit(self):
        for kind in ("digest", "fit_changed", "extra", "missing", "bool", "shape", "nonfinite", "overflow", "underflow", "contract", "states"):
            req = request(); state = req["initial_state"]
            if kind == "digest": state["fit_request_digest"] = "0"*64
            elif kind == "fit_changed": req["fit_request"]["max_absolute_error"] *= 2
            elif kind == "extra": state["capacitor_voltage_v_by_port"]["other"] = 1
            elif kind == "missing": state["inductor_current_a_by_port"] = {}
            elif kind == "bool": state["fit_state_sqrt_w"] = [[True]]
            elif kind == "shape": state["fit_state_sqrt_w"] = [[0., 0.]]
            elif kind == "nonfinite": state["fit_state_sqrt_w"] = [[float("nan")]]
            elif kind == "overflow": state["inductor_current_a_by_port"]["input"] = 1e308
            elif kind == "underflow": state["capacitor_voltage_v_by_port"]["input"] = 5e-324
            elif kind == "contract": state["contract"] = "wrong"
            else:
                source = req["fit_request"]["source"]; source["port_names"] = [f"p{i}" for i in range(8)]
                matrix = [[{"real": 0., "imag": 0.} for _ in range(8)] for _ in range(8)]
                source["s_parameters"] = [deepcopy(matrix) for _ in source["frequencies_hz"]]
                req["fit_request"]["pole_rates_rad_s"] = [1., 2., 3.]
                req["terminations"] = [term(p) for p in source["port_names"]]
            with self.subTest(kind=kind), patch.object(initial.rlc.rational, "fit_sparameter_rational", side_effect=AssertionError("must reject before fit")):
                with self.assertRaises(initial.SParameterRlcInitialError): initial.run_initialized_rlc_network_transient(req)

    def test_cancellation_outer_and_shared_propagation(self):
        completed_polls = []
        initial.run_initialized_rlc_network_transient(request(), cancel_check=lambda: completed_polls.append(1) or False)
        self.assertGreater(len(completed_polls), 20)
        for threshold in (1, 8, 20, len(completed_polls)):
            calls = []
            def cancel():
                calls.append(1); return len(calls) >= threshold
            with self.subTest(threshold=threshold), self.assertRaises(initial.SParameterRlcInitialError) as caught:
                initial.run_initialized_rlc_network_transient(request(), cancel_check=cancel)
            self.assertIn("CANCELLED", caught.exception.code)


if __name__ == "__main__": unittest.main()
