# SPDX-License-Identifier: Apache-2.0
"""Original loaded-RLC and nodal coupled-circuit references, not wave closure.

Preselected tolerances: V/I2e-10 SI, derivatives2e-8 SI, energy1e-9 J.
"""
from copy import deepcopy
import math
import unittest
from unittest.mock import patch

import numpy as np
from scipy.integrate import quad
from scipy.linalg import expm

from python.spike_core import sparameter_rlc_terminated as rlc
from python.spike_core import sparameter_inductive_terminated as inductive
from python.spike_core import sparameter_capacitive_terminated as capacitive
from tests.python.test_sparameter_transient import one_fit


def term(port="input", resistance=10., inductance=1., capacitance=.004, times=(0., 1.), values=(2., 2.)):
    return {"port_name": port, "resistance_ohm": resistance, "inductance_h": inductance, "capacitance_f": capacitance,
            "voltage_points": [{"time_s": t, "voltage_v": v} for t, v in zip(times, values)]}


def request(resistance=10., reference=50., inductance=1., capacitance=.004):
    fit = one_fit(direct=(100-reference)/(100+reference), residue=0.)
    fit["source"]["reference_impedance_ohm"] = reference
    return {"contract": rlc.REQUEST_CONTRACT, "fit_request": fit,
            "terminations": [term(resistance=resistance, inductance=inductance, capacitance=capacitance)],
            "output_times_s": [0., .01, .05, .2, .5, 1.]}


def step_reference(t, resistance=10., inductance=1., capacitance=.004, conductance=.01, source=2.):
    alpha = .5*(resistance/inductance+conductance/capacitance)
    omega2 = (1+resistance*conductance)/(inductance*capacitance)
    steady = source/(1+resistance*conductance)
    if abs(alpha*alpha-omega2) < 1e-12*omega2:
        voltage = steady*(1-math.exp(-alpha*t)*(1+alpha*t))
        derivative = steady*omega2*t*math.exp(-alpha*t)
    elif alpha*alpha < omega2:
        omega = math.sqrt(omega2-alpha*alpha)
        voltage = steady*(1-math.exp(-alpha*t)*(math.cos(omega*t)+alpha/omega*math.sin(omega*t)))
        derivative = steady*omega2/omega*math.exp(-alpha*t)*math.sin(omega*t)
    else:
        delta = math.sqrt(alpha*alpha-omega2); r1, r2 = -alpha+delta, -alpha-delta
        voltage = steady*(1+(r2*math.exp(r1*t)-r1*math.exp(r2*t))/(r1-r2))
        derivative = steady*r1*r2*(math.exp(r1*t)-math.exp(r2*t))/(r1-r2)
    current = conductance*voltage+capacitance*derivative
    return voltage, current, derivative, (source-voltage-resistance*current)/inductance


def physical_pwl(req, conductance):
    """Physical states [V,I], C*V'=I-GV, L*I'=Vs-RI-V."""
    ports = req["fit_request"]["source"]["port_names"]; n = len(ports)
    terms = {t["port_name"]: t for t in req["terminations"]}
    resistance = np.array([terms[p]["resistance_ohm"] for p in ports])
    inductance = np.array([terms[p]["inductance_h"] for p in ports])
    capacitance = np.array([terms[p]["capacitance_f"] for p in ports])
    generator = np.zeros((4*n, 4*n))
    generator[:n, :n] = -conductance/capacitance[:, None]
    generator[:n, n:2*n] = np.diag(1/capacitance)
    generator[n:2*n, :n] = -np.diag(1/inductance)
    generator[n:2*n, n:2*n] = -np.diag(resistance/inductance)
    generator[n:2*n, 2*n:3*n] = np.diag(1/inductance)
    generator[2*n:3*n, 3*n:] = np.eye(n)
    grid = sorted(set(req["output_times_s"]) | {p["time_s"] for term in terms.values() for p in term["voltage_points"]})
    state, result = np.zeros(2*n), {0.: np.zeros(2*n)}
    for left, right in zip(grid, grid[1:]):
        source, slopes = [], []
        for port in ports:
            points = terms[port]["voltage_points"]
            j = next(i for i in range(len(points)-1) if points[i]["time_s"] <= left < points[i+1]["time_s"])
            a, b = points[j:j+2]; slope = (b["voltage_v"]-a["voltage_v"])/(b["time_s"]-a["time_s"])
            source.append(a["voltage_v"]+slope*(left-a["time_s"])); slopes.append(slope)
        state = (expm((right-left)*generator)@np.r_[state, source, slopes])[:2*n]
        result[right] = state.copy()
    return result


class RlcTests(unittest.TestCase):
    def test_loaded_rlc_damping_and_source_work_storage_dissipation(self):
        for resistance in (0., 10., (5+math.sqrt(4000))/2, 80.):
            req = request(resistance); before = deepcopy(req)
            result = rlc.run_rlc_network_transient(req)
            self.assertEqual(req, before)
            for row in result["points"]:
                voltage, current, vdot, idot = step_reference(row["time_s"], resistance)
                for key, expected, tolerance in (("port_voltage_v", voltage, 2e-10), ("source_current_a", current, 2e-10),
                                                 ("port_current_a", voltage/100, 2e-10), ("capacitor_voltage_derivative_v_per_s", vdot, 2e-8),
                                                 ("inductor_current_derivative_a_per_s", idot, 2e-8),
                                                 ("termination_resistor_power_w", resistance*current**2, 1e-9),
                                                 ("inductor_energy_j", .5*current**2, 1e-9), ("capacitor_energy_j", .002*voltage**2, 1e-9)):
                    self.assertAlmostEqual(row[key+"_by_port"]["input"], expected, delta=tolerance)
                self.assertLess(abs(row["boundary_residual_v_by_port"]["input"]), 2e-10)
                self.assertLess(abs(row["boundary_residual_a_by_port"]["input"]), 2e-10)
            source_work = quad(lambda t: 2*step_reference(t, resistance)[1], 0, 1, epsabs=1e-13)[0]
            heat = quad(lambda t: resistance*step_reference(t, resistance)[1]**2+.01*step_reference(t, resistance)[0]**2, 0, 1, epsabs=1e-13)[0]
            last = result["points"][-1]
            self.assertAlmostEqual(source_work, heat+last["inductor_energy_j_by_port"]["input"]+last["capacitor_energy_j_by_port"]["input"], delta=1e-9)

    def test_coupled_two_port_signed_pwl_physical_reference_and_refined_outputs(self):
        conductance = np.array([[.02, -.004], [-.004, .01]])
        scattering = np.linalg.solve(np.eye(2)+50*conductance, np.eye(2)-50*conductance)
        matrix = [[{"real": float(v), "imag": 0.} for v in row] for row in scattering]
        req = request(); source = req["fit_request"]["source"]; source["port_names"] = ["left", "right"]
        source["s_parameters"] = [deepcopy(matrix) for _ in source["frequencies_hz"]]
        req["terminations"] = [term("right", 25., 2., .009, (0., .3, 1.), (-1., 1., -2.)),
                               term("left", 10., 1., .004, (0., .1, .4, 1.), (0., 2., 2., -1.))]
        result = rlc.run_rlc_network_transient(req); expected = physical_pwl(req, conductance)
        self.assertEqual(result["inductive_port_names"], ["left", "right"])
        self.assertEqual(result["capacitive_port_names"], ["left", "right"])
        for row in result["points"]:
            state = expected[row["time_s"]]; network_current = conductance@state[:2]
            for i, port in enumerate(("left", "right")):
                resistance, inductance, capacitance = ((10., 1., .004), (25., 2., .009))[i]
                source_voltage = row["source_voltage_v_by_port"][port]
                voltage_derivative = (state[2+i]-network_current[i])/capacitance
                current_derivative = (source_voltage-resistance*state[2+i]-state[i])/inductance
                self.assertAlmostEqual(row["port_voltage_v_by_port"][port], state[i], delta=2e-10)
                self.assertAlmostEqual(row["source_current_a_by_port"][port], state[2+i], delta=2e-10)
                self.assertAlmostEqual(row["port_current_a_by_port"][port], network_current[i], delta=2e-10)
                self.assertAlmostEqual(row["capacitor_voltage_derivative_v_per_s_by_port"][port], voltage_derivative, delta=2e-8)
                self.assertAlmostEqual(row["inductor_current_derivative_a_per_s_by_port"][port], current_derivative, delta=2e-8)
                self.assertAlmostEqual(row["capacitor_energy_j_by_port"][port], .5*capacitance*state[i]**2, delta=1e-9)
                self.assertAlmostEqual(row["inductor_energy_j_by_port"][port], .5*inductance*state[2+i]**2, delta=1e-9)
                self.assertAlmostEqual(row["termination_resistor_power_w_by_port"][port], resistance*state[2+i]**2, delta=1e-9)
        for i, port in enumerate(("left", "right")):
            self.assertAlmostEqual(result["final_capacitor_voltage_v_by_port"][port], expected[1.][i], delta=2e-10)
            self.assertAlmostEqual(result["final_inductor_current_a_by_port"][port], expected[1.][2+i], delta=2e-10)
        req["output_times_s"] = sorted(set(req["output_times_s"]+[.003, .025, .15, .45, .75]))
        refined = rlc.run_rlc_network_transient(req); lookup = {p["time_s"]: p for p in refined["points"]}
        for row in result["points"]:
            for port in ("left", "right"):
                self.assertAlmostEqual(row["port_voltage_v_by_port"][port], lookup[row["time_s"]]["port_voltage_v_by_port"][port], delta=2e-10)

    def test_true_fitted_memory_parallel_conductance_inductor_network(self):
        # Network Y(s)=G+1/(s*Ln), alongside external series R/Ls and shunt C.
        conductance, network_l, source_l, capacitance, resistance, reference = .01, 2., 1., .004, 10., 50.
        req = request(); pole = reference/(network_l*(1+reference*conductance))
        req["fit_request"]["pole_rates_rad_s"] = [pole]
        source = req["fit_request"]["source"]
        source["id"] = "original-parallel-conductance-inductor"
        source["frequencies_hz"] = [0., .1, 1., 5., 20., 100.]
        samples = []
        for frequency in source["frequencies_hz"]:
            if frequency == 0:
                scattering = complex(-1.)
            else:
                admittance = conductance+1/(2j*math.pi*frequency*network_l)
                scattering = (1-reference*admittance)/(1+reference*admittance)
            samples.append([[{"real": scattering.real, "imag": scattering.imag}]])
        source["s_parameters"] = samples
        actual_fit = rlc.rational.fit_sparameter_rational
        with patch.object(rlc.rational, "fit_sparameter_rational", wraps=actual_fit) as fit:
            result = rlc.run_rlc_network_transient(req)
            self.assertEqual(fit.call_count, 1)
        self.assertAlmostEqual(result["fit_result"]["model"]["residues"][0][0][0], -2/(1+reference*conductance), delta=1e-12)
        # Independently integrate physical [V,Isource,Inetwork_inductor,1].
        generator = np.array([[-conductance/capacitance, 1/capacitance, -1/capacitance, 0.],
                              [-1/source_l, -resistance/source_l, 0., 2/source_l],
                              [1/network_l, 0., 0., 0.], [0., 0., 0., 0.]])
        def physical(time):
            return (expm(time*generator)@[0., 0., 0., 1.])[:3]
        for row in result["points"]:
            voltage, source_current, winding_current = physical(row["time_s"])
            network_current = conductance*voltage+winding_current
            vdot = (source_current-network_current)/capacitance
            idot = (2-resistance*source_current-voltage)/source_l
            for key, expected, tolerance in (("port_voltage_v", voltage, 2e-10), ("port_current_a", network_current, 2e-10),
                                             ("source_current_a", source_current, 2e-10), ("capacitor_voltage_derivative_v_per_s", vdot, 2e-8),
                                             ("inductor_current_derivative_a_per_s", idot, 2e-8),
                                             ("capacitor_energy_j", .5*capacitance*voltage**2, 1e-9),
                                             ("inductor_energy_j", .5*source_l*source_current**2, 1e-9),
                                             ("termination_resistor_power_w", resistance*source_current**2, 1e-9)):
                self.assertAlmostEqual(row[key+"_by_port"]["input"], expected, delta=tolerance)
            self.assertAlmostEqual(row["port_current_a_by_port"]["input"]+capacitance*row["capacitor_voltage_derivative_v_per_s_by_port"]["input"],
                                   row["source_current_a_by_port"]["input"], delta=2e-10)
        source_work = quad(lambda t: 2*physical(t)[1], 0., 1., epsabs=1e-12)[0]
        heat = quad(lambda t: resistance*physical(t)[1]**2+conductance*physical(t)[0]**2, 0., 1., epsabs=1e-12)[0]
        last = result["points"][-1]
        inferred_winding_current = last["port_current_a_by_port"]["input"]-conductance*last["port_voltage_v_by_port"]["input"]
        stored = last["capacitor_energy_j_by_port"]["input"]+last["inductor_energy_j_by_port"]["input"]+.5*network_l*inferred_winding_current**2
        self.assertAlmostEqual(source_work, heat+stored, delta=1e-9)

    def test_mixed_rl_rc_and_pure_r_reductions_against_previous_apis(self):
        req = request(); source = req["fit_request"]["source"]; ports = ["rl", "rc", "r"]
        source["port_names"] = ports
        matrix = [[{"real": 1/3 if i == j else 0., "imag": 0.} for j in range(3)] for i in range(3)]
        source["s_parameters"] = [deepcopy(matrix) for _ in source["frequencies_hz"]]
        req["terminations"] = [term("rc", 20., 0., .004), term("r", 0., 0., 0.), term("rl", 10., 1., 0.)]
        combined = rlc.run_rlc_network_transient(req)
        old_l = request(); old_l["contract"] = inductive.REQUEST_CONTRACT
        del old_l["terminations"][0]["capacitance_f"]
        reference_l = inductive.run_inductive_network_transient(old_l)
        old_c = request(20.); old_c["contract"] = capacitive.REQUEST_CONTRACT
        del old_c["terminations"][0]["inductance_h"]
        reference_c = capacitive.run_capacitive_network_transient(old_c)
        for row, left, right in zip(combined["points"], reference_l["points"], reference_c["points"]):
            for key in ("port_voltage_v_by_port", "port_current_a_by_port"):
                self.assertAlmostEqual(row[key]["rl"], left[key]["input"], delta=2e-10)
                self.assertAlmostEqual(row[key]["rc"], right[key]["input"], delta=2e-10)
            self.assertAlmostEqual(row["port_voltage_v_by_port"]["r"], 2., delta=2e-10)
            self.assertAlmostEqual(row["source_current_a_by_port"]["r"], .02, delta=2e-10)

    def test_reference_impedance_and_time_unit_invariance(self):
        baseline = rlc.run_rlc_network_transient(request())
        for reference in (1., 25., 100., 1000.):
            result = rlc.run_rlc_network_transient(request(reference=reference))
            for a, b in zip(baseline["points"], result["points"]):
                for key, tolerance in (("port_voltage_v", 2e-10), ("source_current_a", 2e-10), ("port_current_a", 2e-10),
                                       ("capacitor_voltage_derivative_v_per_s", 2e-8), ("inductor_current_derivative_a_per_s", 2e-8),
                                       ("termination_resistor_power_w", 1e-9), ("inductor_energy_j", 1e-9), ("capacitor_energy_j", 1e-9)):
                    self.assertAlmostEqual(a[key+"_by_port"]["input"], b[key+"_by_port"]["input"], delta=tolerance)
        req = request(inductance=.001, capacitance=.000004)
        req["terminations"][0]["voltage_points"][-1]["time_s"] = .001
        req["output_times_s"] = [t*.001 for t in req["output_times_s"]]
        result = rlc.run_rlc_network_transient(req)
        for a, b in zip(baseline["points"], result["points"]):
            self.assertAlmostEqual(a["port_voltage_v_by_port"]["input"], b["port_voltage_v_by_port"]["input"], delta=2e-10)
            for key in ("inductor_energy_j_by_port", "capacitor_energy_j_by_port"):
                self.assertAlmostEqual(a[key]["input"]*.001, b[key]["input"], delta=1e-9)

    def test_singular_unstable_marginal_and_precision_rejections(self):
        stable_active = request(); stable_active["fit_request"] = one_fit(direct=2., residue=0.)
        self.assertGreater(rlc.run_rlc_network_transient(stable_active)["fit_result"]["diagnostics"]["sampled_smax_max"], 1.)
        for kind in ("singular", "unstable", "marginal", "tiny_l", "huge_c", "tiny_drive"):
            req = request()
            if kind == "singular": req["fit_request"] = one_fit(direct=-1., residue=0.)
            elif kind == "unstable": req["fit_request"] = one_fit(direct=2., residue=0.); req["terminations"][0]["resistance_ohm"] = 0.
            elif kind == "marginal": req["fit_request"] = one_fit(direct=1., residue=0.); req["terminations"][0]["resistance_ohm"] = 0.
            elif kind == "tiny_l": req["terminations"][0]["inductance_h"] = 5e-324
            elif kind == "huge_c": req["terminations"][0]["capacitance_f"] = 1e308
            else:
                for point in req["terminations"][0]["voltage_points"]: point["voltage_v"] = 1e-200
            with self.subTest(kind=kind), self.assertRaises(rlc.SParameterRlcError): rlc.run_rlc_network_transient(req)

    def test_invalid_and_total_state_preflight_resources_cancel(self):
        for kind in ("no_l", "no_c", "negative", "bool", "unknown", "port", "horizon", "outputs", "durations", "states", "work", "collapse"):
            req = request()
            if kind == "no_l": req["terminations"][0]["inductance_h"] = 0
            elif kind == "no_c": req["terminations"][0]["capacitance_f"] = 0
            elif kind == "negative": req["terminations"][0]["resistance_ohm"] = -1
            elif kind == "bool": req["terminations"][0]["capacitance_f"] = True
            elif kind == "unknown": req["terminations"][0]["extra"] = 1
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
                req["fit_request"]["pole_rates_rad_s"] = [1., 2., 3.]
                # 24 fitted states +8 L+8 C =40; old-only preflight admits24.
                req["terminations"] = [term(p) for p in source["port_names"]]
            with self.subTest(kind=kind), patch.object(rlc, "_MAX_WORK", 1 if kind == "work" else 100_000_000):
                with patch.object(rlc.rational, "fit_sparameter_rational", side_effect=AssertionError("must preflight")):
                    with self.assertRaises(rlc.SParameterRlcError): rlc.run_rlc_network_transient(req)
        for threshold in (1, 10, 20):
            calls = []
            def cancel():
                calls.append(1); return len(calls) >= threshold
            with self.subTest(threshold=threshold), self.assertRaises(rlc.SParameterRlcError) as caught:
                rlc.run_rlc_network_transient(request(), cancel_check=cancel)
            self.assertIn("CANCELLED", caught.exception.code)


if __name__ == "__main__": unittest.main()
