# SPDX-License-Identifier: Apache-2.0
"""Original physical RLC/RL references; no production wave closure in oracles.

Acceptance fixed before runs: V <=2e-11 V, I <=1e-11 A, boundary/derivative
<=2e-10 SI, energy balance <=1e-11 J, trajectory invariance <=2e-11 V.
"""
from copy import deepcopy
import math
import unittest
from unittest.mock import patch

import numpy as np
from scipy.integrate import quad
from scipy.linalg import expm

from python.spike_core import sparameter_inductive_terminated as inductive
from python.spike_core import sparameter_terminated as resistive
from tests.python.test_sparameter_transient import one_fit


def term(port="input", resistance=10., inductance=1., times=(0., 1.), values=(2., 2.)):
    return {"port_name": port, "resistance_ohm": resistance, "inductance_h": inductance,
            "voltage_points": [{"time_s": t, "voltage_v": v} for t, v in zip(times, values)]}


def request(resistance=10., inductance=1.):
    return {"contract": inductive.REQUEST_CONTRACT, "fit_request": one_fit(direct=-1., residue=2.),
            "terminations": [term(resistance=resistance, inductance=inductance)],
            "output_times_s": [0., .01, .05, .2, .5, 1.]}


def step_reference(time, resistance, inductance=1., capacitance=.004, source=2.):
    alpha, omega2 = resistance/(2*inductance), 1/(inductance*capacitance)
    if abs(alpha*alpha-omega2) < 1e-12*omega2:
        voltage = source*(1-math.exp(-alpha*time)*(1+alpha*time))
        current = source*capacitance*omega2*time*math.exp(-alpha*time)
    elif alpha*alpha < omega2:
        omega = math.sqrt(omega2-alpha*alpha)
        voltage = source*(1-math.exp(-alpha*time)*(math.cos(omega*time)+alpha/omega*math.sin(omega*time)))
        current = source*capacitance*omega2/omega*math.exp(-alpha*time)*math.sin(omega*time)
    else:
        delta = math.sqrt(alpha*alpha-omega2); r1, r2 = -alpha+delta, -alpha-delta
        voltage = source*(1+(r2*math.exp(r1*time)-r1*math.exp(r2*time))/(r1-r2))
        current = source*capacitance*r1*r2*(math.exp(r1*time)-math.exp(r2*time))/(r1-r2)
    return voltage, current, (source-voltage-resistance*current)/inductance


def pwl_reference(req, capacitance=.004):
    source = req["terminations"][0]; resistance, inductance = source["resistance_ohm"], source["inductance_h"]
    knots = source["voltage_points"]
    generator = np.array([[0., 1/capacitance, 0., 0.], [-1/inductance, -resistance/inductance, 1/inductance, 0.],
                          [0., 0., 0., 1.], [0., 0., 0., 0.]])
    grid = sorted(set(req["output_times_s"]) | {p["time_s"] for p in knots})
    state, result = np.zeros(2), {0.: np.zeros(2)}
    for left, right in zip(grid, grid[1:]):
        j = next(j for j in range(len(knots)-1) if knots[j]["time_s"] <= left < knots[j+1]["time_s"])
        a, b = knots[j:j+2]
        slope = (b["voltage_v"]-a["voltage_v"])/(b["time_s"]-a["time_s"])
        voltage = a["voltage_v"]+slope*(left-a["time_s"])
        state = (expm((right-left)*generator)@[*state, voltage, slope])[:2]
        result[right] = state.copy()
    return result


class InductiveTests(unittest.TestCase):
    def test_analytic_under_critical_overdamped_rlc_and_termination_energy(self):
        for resistance in (10., 2*math.sqrt(1/.004), 80.):
            req = request(resistance); before = deepcopy(req)
            result = inductive.run_inductive_network_transient(req)
            self.assertEqual(req, before)
            self.assertEqual(result["fit_result"]["source"]["network"], req["fit_request"]["source"])
            for row in result["points"]:
                voltage, current, derivative = step_reference(row["time_s"], resistance)
                self.assertAlmostEqual(row["port_voltage_v_by_port"]["input"], voltage, delta=2e-11)
                self.assertAlmostEqual(row["port_current_a_by_port"]["input"], current, delta=1e-11)
                self.assertAlmostEqual(row["inductor_current_derivative_a_per_s_by_port"]["input"], derivative, delta=2e-10)
                self.assertAlmostEqual(row["termination_resistor_power_w_by_port"]["input"], resistance*current**2, delta=1e-12)
                self.assertAlmostEqual(row["inductor_energy_j_by_port"]["input"], .5*current**2, delta=1e-12)
                self.assertLess(abs(row["boundary_residual_v_by_port"]["input"]), 2e-10)
            last = result["points"][-1]; v = last["port_voltage_v_by_port"]["input"]
            dissipated = quad(lambda t: resistance*step_reference(t, resistance)[1]**2, 0., 1., epsabs=1e-13, epsrel=1e-12)[0]
            stored = .5*.004*v*v+last["inductor_energy_j_by_port"]["input"]
            self.assertAlmostEqual(2*.004*v, stored+dissipated, delta=1e-11)

    def test_pwl_signed_source_physical_state_reference_and_grid_invariance(self):
        req = request(); req["terminations"] = [term(times=(0., .1, .35, 1.), values=(0., 2., 2., -1.))]
        result = inductive.run_inductive_network_transient(req); expected = pwl_reference(req)
        for row in result["points"]:
            voltage, current = expected[row["time_s"]]
            self.assertAlmostEqual(row["port_voltage_v_by_port"]["input"], voltage, delta=2e-11)
            self.assertAlmostEqual(row["inductor_current_a_by_port"]["input"], current, delta=1e-11)
            actual = row["port_voltage_v_by_port"]["input"]+10*row["port_current_a_by_port"]["input"]+row["inductor_current_derivative_a_per_s_by_port"]["input"]
            self.assertAlmostEqual(actual, row["source_voltage_v_by_port"]["input"], delta=2e-10)
        req["output_times_s"] = sorted(set(req["output_times_s"]+[.003, .025, .15, .45, .75]))
        refined = inductive.run_inductive_network_transient(req)
        lookup = {r["time_s"]: r for r in refined["points"]}
        for row in result["points"]:
            self.assertAlmostEqual(row["port_voltage_v_by_port"]["input"], lookup[row["time_s"]]["port_voltage_v_by_port"]["input"], delta=2e-11)

    def test_mixed_coupled_through_ports_and_source_order(self):
        req = request(); source = req["fit_request"]["source"]; source["port_names"] = ["left", "right"]
        through = [[{"real": 0., "imag": 0.}, {"real": 1., "imag": 0.}], [{"real": 1., "imag": 0.}, {"real": 0., "imag": 0.}]]
        source["s_parameters"] = [deepcopy(through) for _ in source["frequencies_hz"]]
        req["terminations"] = [term("right", 50., 0., values=(-1., -1.)), term("left", 10., 2., values=(2., 2.))]
        result = inductive.run_inductive_network_transient(req)
        self.assertEqual(result["port_names"], ["left", "right"])
        self.assertEqual(result["inductive_port_names"], ["left"])
        for row in result["points"]:
            current = 3/60*(-math.expm1(-30*row["time_s"]))
            self.assertAlmostEqual(row["port_current_a_by_port"]["left"], current, delta=1e-11)
            self.assertAlmostEqual(row["port_current_a_by_port"]["right"], -current, delta=1e-11)
            for port in ("left", "right"):
                self.assertAlmostEqual(row["port_voltage_v_by_port"][port], -1+50*current, delta=2e-11)
        # At late time this equals the independently solved all-resistive divider.
        algebraic = deepcopy(req); algebraic["contract"] = resistive.REQUEST_CONTRACT
        for t in algebraic["terminations"]: del t["inductance_h"]
        steady = resistive.run_terminated_network_transient(algebraic)
        self.assertAlmostEqual(result["points"][-1]["port_voltage_v_by_port"]["left"], steady["points"][-1]["port_voltage_v_by_port"]["left"], delta=2e-11)

    def test_rlc_time_units_scaling_and_stable_active_network(self):
        baseline = inductive.run_inductive_network_transient(request())
        req = request(inductance=.001); req["fit_request"] = one_fit(pole=5000., direct=-1., residue=2.)
        req["terminations"][0]["voltage_points"][-1]["time_s"] = .001
        req["output_times_s"] = [t*.001 for t in req["output_times_s"]]
        scaled = inductive.run_inductive_network_transient(req)
        for a, b in zip(baseline["points"], scaled["points"]):
            self.assertAlmostEqual(a["port_voltage_v_by_port"]["input"], b["port_voltage_v_by_port"]["input"], delta=2e-11)
            self.assertAlmostEqual(a["port_current_a_by_port"]["input"], b["port_current_a_by_port"]["input"], delta=1e-11)
            self.assertAlmostEqual(a["inductor_energy_j_by_port"]["input"]*.001, b["inductor_energy_j_by_port"]["input"], delta=1e-13)
        req = request(resistance=100.); req["fit_request"] = one_fit(direct=-1.2, residue=0.)
        result = inductive.run_inductive_network_transient(req)
        self.assertGreater(result["fit_result"]["diagnostics"]["sampled_smax_max"], 1.)
        self.assertGreater(result["diagnostics"]["closed_system_stability_margin_per_s"], 0.)

    def test_physical_rlc_invariant_under_reference_impedance_encoding(self):
        # Same C=.004 F, R=10 ohm, L=1 H and source volts; only the power-wave
        # reference and corresponding capacitor pole/S samples change.
        baseline = inductive.run_inductive_network_transient(request())
        for reference in (1., 25., 100., 1000.):
            req = request()
            req["fit_request"] = one_fit(pole=1/(reference*.004), direct=-1., residue=2.)
            req["fit_request"]["source"]["reference_impedance_ohm"] = reference
            result = inductive.run_inductive_network_transient(req)
            with self.subTest(reference=reference):
                for original, changed in zip(baseline["points"], result["points"]):
                    for field, tolerance in (("port_voltage_v_by_port", 2e-11),
                                             ("port_current_a_by_port", 1e-11),
                                             ("inductor_current_derivative_a_per_s_by_port", 2e-10),
                                             ("termination_resistor_power_w_by_port", 1e-12),
                                             ("inductor_energy_j_by_port", 1e-12)):
                        self.assertAlmostEqual(changed[field]["input"], original[field]["input"], delta=tolerance)
                    # The stored current state is physical despite its internal
                    # q=sqrt(Z0)*I coordinate normalization.
                    self.assertAlmostEqual(changed["inductor_current_a_by_port"]["input"],
                                           original["inductor_current_a_by_port"]["input"], delta=1e-11)

    def test_two_simultaneous_inductors_coupled_capacitance_physical_reference(self):
        capacitance = np.array([[.006, -.002], [-.002, .006]])
        frequencies = [0., .01, .1, 1., 4., 10.]
        samples = []
        for frequency in frequencies:
            admittance = 2j*math.pi*frequency*capacitance
            scattering = np.linalg.solve(np.eye(2)+50*admittance, np.eye(2)-50*admittance)
            samples.append([[{"real": z.real, "imag": z.imag} for z in row] for row in scattering])
        req = request(); req["fit_request"] = {"contract": "spike/sparameter-rational-fit-request/v1",
            "source": {"id": "original-mutual-capacitance", "port_names": ["left", "right"], "reference_impedance_ohm": 50.,
                       "frequencies_hz": frequencies, "s_parameters": samples}, "pole_rates_rad_s": [5., 2.5], "max_absolute_error": 1e-12}
        req["terminations"] = [term("right", 20., 2., values=(-1., -1.)), term("left", 10., 1., values=(2., 2.))]
        result = inductive.run_inductive_network_transient(req)
        # Independent circuit equations C*V'=I, L*I'=Vs-R*I-V.
        inverse_l = np.diag([1., .5]); physical = np.zeros((6, 6))
        physical[:2, 2:4] = np.linalg.solve(capacitance, np.eye(2))
        physical[2:4, :2] = -inverse_l
        physical[2:4, 2:4] = -inverse_l@np.diag([10., 20.])
        physical[2:4, 4:] = inverse_l
        for row in result["points"]:
            expected = expm(row["time_s"]*physical)@[0., 0., 0., 0., 2., -1.]
            for j, port in enumerate(("left", "right")):
                self.assertAlmostEqual(row["port_voltage_v_by_port"][port], expected[j], delta=2e-11)
                self.assertAlmostEqual(row["inductor_current_a_by_port"][port], expected[j+2], delta=1e-11)
        self.assertEqual(result["inductive_port_names"], ["left", "right"])

    def test_singular_unstable_marginal_and_precision_refusals(self):
        for kind in ("singular", "unstable", "lossless", "tiny_l", "huge_l", "tiny_drive"):
            req = request()
            if kind == "singular": req["fit_request"] = one_fit(direct=1., residue=0.)
            elif kind == "unstable": req["fit_request"] = one_fit(direct=2., residue=0.)
            elif kind == "lossless": req["terminations"][0]["resistance_ohm"] = 0.
            elif kind == "tiny_l": req["terminations"][0]["inductance_h"] = 5e-324
            elif kind == "huge_l": req["terminations"][0]["inductance_h"] = 1e308
            else:
                for p in req["terminations"][0]["voltage_points"]: p["voltage_v"] = 1e-200
            with self.subTest(kind=kind), self.assertRaises(inductive.SParameterInductiveError):
                inductive.run_inductive_network_transient(req)

    def test_invalid_preflight_limits_and_cancel(self):
        for kind in ("zero", "negative", "bool", "nonfinite", "field", "port", "horizon", "outputs", "durations", "work", "collapse"):
            req = request()
            if kind == "zero": req["terminations"][0]["inductance_h"] = 0
            elif kind == "negative": req["terminations"][0]["inductance_h"] = -1
            elif kind == "bool": req["terminations"][0]["inductance_h"] = True
            elif kind == "nonfinite": req["terminations"][0]["inductance_h"] = float("inf")
            elif kind == "field": req["terminations"][0]["extra"] = 1
            elif kind == "port": req["terminations"][0]["port_name"] = "missing"
            elif kind == "horizon": req["output_times_s"] = [2.]
            elif kind == "outputs": req["output_times_s"] = list(np.linspace(0, 1, 1025))
            elif kind == "durations": req["output_times_s"] = [i*i/40000 for i in range(201)]
            elif kind == "collapse":
                req["terminations"][0]["voltage_points"] = [{"time_s": t, "voltage_v": 1.} for t in (0, 10**20, 10**20+1)]
                req["output_times_s"] = [0.]
            with self.subTest(kind=kind), patch.object(inductive, "_MAX_WORK", 1 if kind == "work" else 100_000_000):
                with patch.object(inductive.rational, "fit_sparameter_rational", side_effect=AssertionError("must preflight")):
                    with self.assertRaises(inductive.SParameterInductiveError): inductive.run_inductive_network_transient(req)
        for threshold in (1, 10, 20):
            calls = []
            def cancel():
                calls.append(1)
                return len(calls) >= threshold
            with self.subTest(threshold=threshold), self.assertRaises(inductive.SParameterInductiveError) as caught:
                inductive.run_inductive_network_transient(request(), cancel_check=cancel)
            self.assertIn("CANCELLED", caught.exception.code)


if __name__ == "__main__": unittest.main()
