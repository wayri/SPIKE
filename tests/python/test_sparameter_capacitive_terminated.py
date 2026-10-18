# SPDX-License-Identifier: Apache-2.0
"""Original physical RC/parallel-RLC oracles, independent of wave closure.

Preselected acceptance: V2e-11 V, I2e-11 A, dV/dt2e-9 V/s, KCL2e-10 A,
energy balance1e-10 J. Synthetic fixtures do not establish measured validity.
"""
from copy import deepcopy
import math
import unittest
from unittest.mock import patch

import numpy as np
from scipy.integrate import quad
from scipy.linalg import expm

from python.spike_core import sparameter_capacitive_terminated as capacitive
from tests.python.test_sparameter_transient import one_fit


def term(port="input", resistance=20., capacitance=.004, times=(0., 1.), values=(2., 2.)):
    return {"port_name": port, "resistance_ohm": resistance, "capacitance_f": capacitance,
            "voltage_points": [{"time_s": t, "voltage_v": v} for t, v in zip(times, values)]}


def request(resistance=20., capacitance=.004, reference=50., inductance=1.):
    fit = one_fit(pole=reference/inductance, direct=1., residue=-2.)
    fit["source"]["reference_impedance_ohm"] = reference
    return {"contract": capacitive.REQUEST_CONTRACT, "fit_request": fit, "terminations": [term(resistance=resistance, capacitance=capacitance)],
            "output_times_s": [0., .01, .05, .2, .5, 1.]}


def step_reference(time, resistance=20., capacitance=.004, inductance=1., source=2.):
    alpha, omega2 = 1/(2*resistance*capacitance), 1/(inductance*capacitance)
    slope = source/(resistance*capacitance)
    if abs(alpha*alpha-omega2) < 1e-12*omega2:
        voltage = slope*time*math.exp(-alpha*time)
        derivative = slope*(1-alpha*time)*math.exp(-alpha*time)
    elif alpha*alpha < omega2:
        omega = math.sqrt(omega2-alpha*alpha)
        voltage = slope/omega*math.exp(-alpha*time)*math.sin(omega*time)
        derivative = slope*math.exp(-alpha*time)*(math.cos(omega*time)-alpha/omega*math.sin(omega*time))
    else:
        delta = math.sqrt(alpha*alpha-omega2); r1, r2 = -alpha+delta, -alpha-delta
        voltage = slope*(math.exp(r1*time)-math.exp(r2*time))/(r1-r2)
        derivative = slope*(r1*math.exp(r1*time)-r2*math.exp(r2*time))/(r1-r2)
    source_current = (source-voltage)/resistance
    network_current = source_current-capacitance*derivative
    return voltage, network_current, derivative, source_current


def pwl_reference(req, inductance=1.):
    term = req["terminations"][0]; r, c = term["resistance_ohm"], term["capacitance_f"]
    generator = np.array([[-1/(r*c), -1/c, 1/(r*c), 0.], [1/inductance, 0., 0., 0.],
                          [0., 0., 0., 1.], [0., 0., 0., 0.]])
    knots = term["voltage_points"]
    grid = sorted(set(req["output_times_s"]) | {p["time_s"] for p in knots})
    state, result = np.zeros(2), {0.: np.zeros(2)}
    for left, right in zip(grid, grid[1:]):
        j = next(j for j in range(len(knots)-1) if knots[j]["time_s"] <= left < knots[j+1]["time_s"])
        a, b = knots[j:j+2]; slope = (b["voltage_v"]-a["voltage_v"])/(b["time_s"]-a["time_s"])
        voltage = a["voltage_v"]+slope*(left-a["time_s"])
        state = (expm((right-left)*generator)@[*state, voltage, slope])[:2]
        result[right] = state.copy()
    return result


class CapacitiveTests(unittest.TestCase):
    def test_analytic_parallel_rlc_damping_current_split_and_energy_balance(self):
        for resistance in (20., math.sqrt(1/.004)/2, 3.):
            req = request(resistance); before = deepcopy(req)
            result = capacitive.run_capacitive_network_transient(req)
            self.assertEqual(req, before)
            self.assertEqual(result["fit_result"]["source"]["network"], req["fit_request"]["source"])
            for row in result["points"]:
                voltage, current, derivative, source_current = step_reference(row["time_s"], resistance)
                self.assertAlmostEqual(row["port_voltage_v_by_port"]["input"], voltage, delta=2e-11)
                self.assertAlmostEqual(row["port_current_a_by_port"]["input"], current, delta=2e-11)
                self.assertAlmostEqual(row["source_current_a_by_port"]["input"], source_current, delta=2e-11)
                self.assertAlmostEqual(row["capacitor_voltage_derivative_v_per_s_by_port"]["input"], derivative, delta=2e-9)
                self.assertAlmostEqual(row["termination_resistor_power_w_by_port"]["input"], resistance*source_current**2, delta=1e-11)
                self.assertAlmostEqual(row["capacitor_energy_j_by_port"]["input"], .5*.004*voltage**2, delta=1e-11)
                self.assertLess(abs(row["boundary_residual_a_by_port"]["input"]), 2e-10)
            source_work = quad(lambda t: 2*step_reference(t, resistance)[3], 0, 1, epsabs=1e-13)[0]
            heat = quad(lambda t: resistance*step_reference(t, resistance)[3]**2, 0, 1, epsabs=1e-13)[0]
            last = result["points"][-1]
            storage = .5*last["port_current_a_by_port"]["input"]**2+last["capacitor_energy_j_by_port"]["input"]
            self.assertAlmostEqual(source_work, heat+storage, delta=1e-10)

    def test_resistor_network_rc_step_and_initial_current_split(self):
        req = request(capacitance=.01)
        scattering = (100-50)/(100+50)
        req["fit_request"] = one_fit(direct=scattering, residue=0.)
        result = capacitive.run_capacitive_network_transient(req)
        tau, final = .01/(1/20+1/100), 2*100/120
        for row in result["points"]:
            voltage = final*(-math.expm1(-row["time_s"]/tau))
            self.assertAlmostEqual(row["port_voltage_v_by_port"]["input"], voltage, delta=2e-11)
            self.assertAlmostEqual(row["port_current_a_by_port"]["input"], voltage/100, delta=2e-11)
            self.assertAlmostEqual(row["source_current_a_by_port"]["input"], (2-voltage)/20, delta=2e-11)
        initial = result["points"][0]
        self.assertAlmostEqual(initial["port_current_a_by_port"]["input"], 0., delta=1e-14)
        self.assertAlmostEqual(initial["source_current_a_by_port"]["input"], .1, delta=1e-14)

    def test_pwl_physical_state_reference_and_output_grid_invariance(self):
        req = request(); req["terminations"] = [term(times=(0., .1, .35, 1.), values=(0., 2., 2., -1.))]
        result = capacitive.run_capacitive_network_transient(req); expected = pwl_reference(req)
        for row in result["points"]:
            voltage, current = expected[row["time_s"]]
            self.assertAlmostEqual(row["port_voltage_v_by_port"]["input"], voltage, delta=2e-11)
            self.assertAlmostEqual(row["port_current_a_by_port"]["input"], current, delta=2e-11)
            self.assertAlmostEqual(row["port_current_a_by_port"]["input"]+.004*row["capacitor_voltage_derivative_v_per_s_by_port"]["input"], row["source_current_a_by_port"]["input"], delta=2e-10)
        req["output_times_s"] = sorted(set(req["output_times_s"]+[.003, .025, .15, .45, .75]))
        refined = capacitive.run_capacitive_network_transient(req)
        lookup = {row["time_s"]: row for row in refined["points"]}
        for row in result["points"]:
            self.assertAlmostEqual(row["port_voltage_v_by_port"]["input"], lookup[row["time_s"]]["port_voltage_v_by_port"]["input"], delta=2e-11)

    def test_mixed_two_port_coupling_source_order_and_ideal_resistor_row(self):
        req = request(); source = req["fit_request"]["source"]; source["port_names"] = ["left", "right"]
        through = [[{"real": 0., "imag": 0.}, {"real": 1., "imag": 0.}], [{"real": 1., "imag": 0.}, {"real": 0., "imag": 0.}]]
        source["s_parameters"] = [deepcopy(through) for _ in source["frequencies_hz"]]
        req["terminations"] = [term("right", 50., 0., values=(-1., -1.)), term("left", 20., .004)]
        result = capacitive.run_capacitive_network_transient(req)
        self.assertEqual(result["capacitive_port_names"], ["left"])
        for row in result["points"]:
            voltage = (2/20-1/50)/(1/20+1/50)*(-math.expm1(-row["time_s"]*(1/20+1/50)/.004))
            for port in ("left", "right"):
                self.assertAlmostEqual(row["port_voltage_v_by_port"][port], voltage, delta=2e-11)
            self.assertAlmostEqual(row["port_current_a_by_port"]["left"], (voltage+1)/50, delta=2e-11)
        # Independent uncoupled port permits a well-posed ideal voltage source.
        diagonal = [[{"real": .2, "imag": 0.}, {"real": 0., "imag": 0.}], [{"real": 0., "imag": 0.}, {"real": .2, "imag": 0.}]]
        source["s_parameters"] = [deepcopy(diagonal) for _ in source["frequencies_hz"]]
        req["terminations"][0]["resistance_ohm"] = 0.
        result = capacitive.run_capacitive_network_transient(req)
        for row in result["points"]:
            self.assertAlmostEqual(row["port_voltage_v_by_port"]["right"], -1., delta=2e-11)
            self.assertAlmostEqual(row["source_current_a_by_port"]["right"], -1/75, delta=2e-11)

    def test_reference_impedance_and_physical_time_scaling(self):
        baseline = capacitive.run_capacitive_network_transient(request())
        for reference in (1., 25., 100., 1000.):
            result = capacitive.run_capacitive_network_transient(request(reference=reference))
            for a, b in zip(baseline["points"], result["points"]):
                for key, tolerance in (("port_voltage_v_by_port", 2e-11), ("port_current_a_by_port", 2e-11),
                                       ("source_current_a_by_port", 2e-11), ("capacitor_voltage_derivative_v_per_s_by_port", 2e-9),
                                       ("termination_resistor_power_w_by_port", 1e-11), ("capacitor_energy_j_by_port", 1e-11)):
                    self.assertAlmostEqual(a[key]["input"], b[key]["input"], delta=tolerance)
        req = request(capacitance=.000004, inductance=.001)
        req["terminations"][0]["voltage_points"][-1]["time_s"] = .001
        req["output_times_s"] = [t*.001 for t in req["output_times_s"]]
        result = capacitive.run_capacitive_network_transient(req)
        for a, b in zip(baseline["points"], result["points"]):
            self.assertAlmostEqual(a["port_voltage_v_by_port"]["input"], b["port_voltage_v_by_port"]["input"], delta=2e-11)
            self.assertAlmostEqual(a["capacitor_energy_j_by_port"]["input"]*.001, b["capacitor_energy_j_by_port"]["input"], delta=1e-11)

    def test_two_shunt_capacitors_coupled_conductance_and_source_order(self):
        conductance = np.array([[.02, -.004], [-.004, .01]])
        resistance, capacitance = np.array([20., 35.]), np.array([.004, .009])
        sources = np.array([2., -1.])
        scattering = np.linalg.solve(np.eye(2)+50*conductance, np.eye(2)-50*conductance)
        matrix = [[{"real": float(value), "imag": 0.} for value in row] for row in scattering]
        req = request(); source = req["fit_request"]["source"]
        source["id"] = "original-coupled-conductance"
        source["port_names"] = ["left", "right"]
        source["s_parameters"] = [deepcopy(matrix) for _ in source["frequencies_hz"]]
        req["terminations"] = [term("right", resistance[1], capacitance[1], values=(-1., -1.)),
                               term("left", resistance[0], capacitance[0])]
        result = capacitive.run_capacitive_network_transient(req)
        self.assertEqual(result["capacitive_port_names"], ["left", "right"])
        # Physical nodal reference Cdiag V'=Rsrc^-1(Vs-V)-G*V.
        operator = -(np.diag(1/resistance)+conductance)/capacitance[:, None]
        forcing = sources/(resistance*capacitance)
        generator = np.zeros((3, 3)); generator[:2, :2] = operator; generator[:2, 2] = forcing
        for row in result["points"]:
            voltage = (expm(row["time_s"]*generator)@[0., 0., 1.])[:2]
            current, source_current = conductance@voltage, (sources-voltage)/resistance
            derivative = (source_current-current)/capacitance
            for i, port in enumerate(("left", "right")):
                self.assertAlmostEqual(row["port_voltage_v_by_port"][port], voltage[i], delta=2e-11)
                self.assertAlmostEqual(row["capacitor_voltage_v_by_port"][port], voltage[i], delta=2e-11)
                self.assertAlmostEqual(row["port_current_a_by_port"][port], current[i], delta=2e-11)
                self.assertAlmostEqual(row["source_current_a_by_port"][port], source_current[i], delta=2e-11)
                self.assertAlmostEqual(row["capacitor_voltage_derivative_v_per_s_by_port"][port], derivative[i], delta=2e-9)
                self.assertAlmostEqual(row["capacitor_energy_j_by_port"][port], .5*capacitance[i]*voltage[i]**2, delta=1e-11)
                self.assertAlmostEqual(row["termination_resistor_power_w_by_port"][port], resistance[i]*source_current[i]**2, delta=1e-11)

    def test_active_stable_singular_unstable_marginal_and_extremes(self):
        req = request(); req["fit_request"] = one_fit(direct=2., residue=0.)
        self.assertGreater(capacitive.run_capacitive_network_transient(req)["fit_result"]["diagnostics"]["sampled_smax_max"], 1.)
        for kind in ("singular", "unstable", "marginal", "tiny_c", "huge_c", "tiny_drive"):
            req = request()
            if kind == "singular": req["fit_request"] = one_fit(direct=-1., residue=0.)
            elif kind == "unstable": req["fit_request"] = one_fit(direct=-2., residue=0.)
            elif kind == "marginal":
                req["fit_request"] = one_fit(direct=2., residue=0.); req["terminations"][0]["resistance_ohm"] = 150.
            elif kind == "tiny_c": req["terminations"][0]["capacitance_f"] = 5e-324
            elif kind == "huge_c": req["terminations"][0]["capacitance_f"] = 1e308
            else:
                for point in req["terminations"][0]["voltage_points"]: point["voltage_v"] = 1e-200
            with self.subTest(kind=kind), self.assertRaises(capacitive.SParameterCapacitiveError):
                capacitive.run_capacitive_network_transient(req)

    def test_invalid_preflight_total_state_limits_and_cancellation(self):
        for kind in ("zero", "negative", "zero_r", "bool", "field", "port", "horizon", "outputs", "durations", "work", "collapse", "states"):
            req = request()
            if kind == "zero": req["terminations"][0]["capacitance_f"] = 0
            elif kind == "negative": req["terminations"][0]["capacitance_f"] = -1
            elif kind == "zero_r": req["terminations"][0]["resistance_ohm"] = 0
            elif kind == "bool": req["terminations"][0]["capacitance_f"] = True
            elif kind == "field": req["terminations"][0]["extra"] = 1
            elif kind == "port": req["terminations"][0]["port_name"] = "missing"
            elif kind == "horizon": req["output_times_s"] = [2.]
            elif kind == "outputs": req["output_times_s"] = list(np.linspace(0, 1, 1025))
            elif kind == "durations": req["output_times_s"] = [i*i/40000 for i in range(201)]
            elif kind == "collapse":
                req["terminations"][0]["voltage_points"] = [{"time_s": t, "voltage_v": 1.} for t in (0, 10**20, 10**20+1)]
                req["output_times_s"] = [0.]
            elif kind == "states":
                source = req["fit_request"]["source"]; source["port_names"] = [f"p{i}" for i in range(8)]
                matrix = [[{"real": 0., "imag": 0.} for _ in range(8)] for _ in range(8)]
                source["s_parameters"] = [deepcopy(matrix) for _ in source["frequencies_hz"]]
                req["fit_request"]["pole_rates_rad_s"] = [1., 2., 3., 4.]
                req["terminations"] = [term(p) for p in source["port_names"]]
            with self.subTest(kind=kind), patch.object(capacitive, "_MAX_WORK", 1 if kind == "work" else 100_000_000):
                with patch.object(capacitive.rational, "fit_sparameter_rational", side_effect=AssertionError("must preflight")):
                    with self.assertRaises(capacitive.SParameterCapacitiveError): capacitive.run_capacitive_network_transient(req)
        for threshold in (1, 10, 20):
            calls = []
            def cancel():
                calls.append(1)
                return len(calls) >= threshold
            with self.subTest(threshold=threshold), self.assertRaises(capacitive.SParameterCapacitiveError) as caught:
                capacitive.run_capacitive_network_transient(request(), cancel_check=cancel)
            self.assertIn("CANCELLED", caught.exception.code)


if __name__ == "__main__": unittest.main()
