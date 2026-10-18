# SPDX-License-Identifier: Apache-2.0
"""Independent analytic/physical quadrature; energy tolerance1e-10 J+1e-9 rel."""
from copy import deepcopy
import math
import unittest
from unittest.mock import patch

import numpy as np
from scipy.integrate import quad
from scipy.linalg import expm

from python.spike_core import sparameter_rlc_energy as energy
from tests.python.test_sparameter_rlc_initial import request as transient_request, analytic_loaded, memory_request, reslice
from tests.python.test_sparameter_rlc_terminated import term, physical_pwl
from tests.python.test_sparameter_transient import one_fit


def request(transient=None):
    return {"contract": energy.REQUEST_CONTRACT, "transient_request": transient or transient_request(),
            "relative_tolerance": 1e-9, "absolute_tolerance_j": 1e-10}


def coupled_request():
    transient = transient_request(voltage=0., current=0.)
    g = np.array([[.02, -.004], [-.004, .01]])
    s = np.linalg.solve(np.eye(2)+50*g, np.eye(2)-50*g)
    matrix = [[{"real": float(value), "imag": 0.} for value in row] for row in s]
    source = transient["fit_request"]["source"]; source["port_names"] = ["left", "right"]
    source["s_parameters"] = [deepcopy(matrix) for _ in source["frequencies_hz"]]
    transient["terminations"] = [term("right", 25., 2., .009, (0., .3, .8, 1.), (-1., 1., -2., -2.)),
                                 term("left", 10., 1., .004, (0., .1, .35, .7, 1.), (0., 2., 2., -1., .5))]
    transient["output_times_s"] = [0., .05, .1, .23, .35, .5, .7, .9, 1.]
    transient["initial_state"].update(fit_request_digest=energy.rlc.rational.sampling._digest(transient["fit_request"]),
                                      fit_state_sqrt_w=[[0., 0.]], inductor_current_a_by_port={"right": 0., "left": 0.},
                                      capacitor_voltage_v_by_port={"right": 0., "left": 0.})
    return transient, g


class EnergyTests(unittest.TestCase):
    def assertEnergy(self, actual, expected):
        self.assertAlmostEqual(actual, expected, delta=1e-10+1e-9*abs(expected))

    def test_analytic_free_forced_damping_each_integral_and_boundary_storage(self):
        for resistance in (10., (5+math.sqrt(4000))/2, 80.):
            for source in (0., 2.):
                transient = transient_request(resistance)
                for p in transient["terminations"][0]["voltage_points"]: p["voltage_v"] = source
                req = request(transient); before = deepcopy(req)
                out = energy.run_rlc_energy_ledger(req); self.assertEqual(req, before)
                self.assertGreater(out["diagnostics"]["maximum_doubling_count"], 0)
                for interval in out["intervals"]:
                    left, right = interval["start_time_s"], interval["end_time_s"]
                    def state(t): return analytic_loaded(t, resistance, source=source)
                    source_work = quad(lambda t: source*state(t)[1], left, right, epsabs=1e-13)[0]
                    network_work = quad(lambda t: .01*state(t)[0]**2, left, right, epsabs=1e-13)[0]
                    heat = quad(lambda t: resistance*state(t)[1]**2, left, right, epsabs=1e-13)[0]
                    for field, expected in (("source_work_j_by_port", source_work), ("network_work_j_by_port", network_work), ("resistor_heat_j_by_port", heat)):
                        self.assertEnergy(interval[field]["input"], expected)
                    for field, time in (("initial_boundary_storage_j_by_port", left), ("final_boundary_storage_j_by_port", right)):
                        v, i = state(time)[:2]; self.assertEnergy(interval[field]["input"], .002*v*v+.5*i*i)
                for field in energy._MAPS[:3]:
                    self.assertEqual(out["totals"][field]["input"], math.fsum(i[field]["input"] for i in out["intervals"]))
                self.assertEqual(out["totals"][energy._MAPS[3]], out["intervals"][0][energy._MAPS[3]])
                self.assertEqual(out["totals"][energy._MAPS[4]], out["intervals"][-1][energy._MAPS[4]])

    def test_nonzero_fit_memory_work_equals_known_network_heat_and_storage(self):
        req = request(memory_request()); out = energy.run_rlc_energy_ledger(req)
        generator = np.array([[-2.5, 250., -250., 0.], [-1., -10., 0., 2.], [.5, 0., 0., 0.], [0., 0., 0., 0.]])
        def physical(t): return (expm(t*generator)@[-.7, .12, -.08, 1.])[:3]
        source_work = quad(lambda t: 2*physical(t)[1], 0, 1, epsabs=1e-12)[0]
        network_work = quad(lambda t: physical(t)[0]*(.01*physical(t)[0]+physical(t)[2]), 0, 1, epsabs=1e-12)[0]
        network_heat = quad(lambda t: .01*physical(t)[0]**2, 0, 1, epsabs=1e-12)[0]
        self.assertEnergy(out["totals"]["source_work_j_by_port"]["input"], source_work)
        self.assertEnergy(out["totals"]["network_work_j_by_port"]["input"], network_work)
        self.assertEnergy(network_work, network_heat+physical(1)[2]**2-(-.08)**2)

    def test_stiff_interval_scaled_gramian_avoids_unstable_block_overflow(self):
        transient = transient_request()
        transient["terminations"][0]["voltage_points"][-1]["time_s"] = 1000.
        transient["output_times_s"] = [0., 1000.]
        out = energy.run_rlc_energy_ledger(request(transient))
        self.assertGreaterEqual(out["diagnostics"]["maximum_doubling_count"], 15)
        # The physical homogeneous rates span thousands of e-folds here. Split
        # only the independent quadrature to resolve the initial boundary layer.
        functions = (lambda t: 2*analytic_loaded(t, 10.)[1], lambda t: .01*analytic_loaded(t, 10.)[0]**2,
                     lambda t: 10*analytic_loaded(t, 10.)[1]**2)
        for field, function in zip(energy._MAPS[:3], functions):
            expected = math.fsum(quad(function, a, b, epsabs=1e-12)[0] for a, b in ((0., 1.), (1., 10.), (10., 1000.)))
            self.assertEnergy(out["totals"][field]["input"], expected)

    def test_coupled_pwl_physical_quadrature_and_nonzero_ramp_chunk_additivity(self):
        transient, conductance = coupled_request(); req = request(transient)
        out = energy.run_rlc_energy_ledger(req)
        physical_states = physical_pwl(transient, conductance)
        terms = {t["port_name"]: t for t in transient["terminations"]}
        r, l, c = np.array([10., 25.]), np.array([1., 2.]), np.array([.004, .009])
        generator = np.zeros((8, 8)); generator[:2, :2] = -conductance/c[:, None]; generator[:2, 2:4] = np.diag(1/c)
        generator[2:4, :2] = -np.diag(1/l); generator[2:4, 2:4] = -np.diag(r/l)
        generator[2:4, 4:6] = np.diag(1/l); generator[4:6, 6:] = np.eye(2)
        for interval in out["intervals"]:
            left, right = interval["start_time_s"], interval["end_time_s"]
            voltage, slopes = [], []
            for port in ("left", "right"):
                points = terms[port]["voltage_points"]
                j = next(i for i in range(len(points)-1) if points[i]["time_s"] <= left < points[i+1]["time_s"])
                a, b = points[j:j+2]; slope = (b["voltage_v"]-a["voltage_v"])/(b["time_s"]-a["time_s"])
                voltage.append(a["voltage_v"]+slope*(left-a["time_s"])); slopes.append(slope)
            start = np.r_[physical_states[left], voltage, slopes]
            def physical(t): return expm((t-left)*generator)@start
            for j, port in enumerate(("left", "right")):
                source_work = quad(lambda t: physical(t)[4+j]*physical(t)[2+j], left, right, epsabs=1e-12)[0]
                network_work = quad(lambda t: physical(t)[j]*(conductance@physical(t)[:2])[j], left, right, epsabs=1e-12)[0]
                heat = quad(lambda t: r[j]*physical(t)[2+j]**2, left, right, epsabs=1e-12)[0]
                for field, expected in zip(energy._MAPS[:3], (source_work, network_work, heat)):
                    self.assertEnergy(interval[field][port], expected)
        # .47 is strictly inside nonzero source ramps and absent from output grid.
        first = energy.run_rlc_energy_ledger(request(reslice(transient, 0., .47)))
        second_req = reslice(transient, .47, 1.); second_req["initial_state"] = first["transient_result"]["restart_state"]
        second = energy.run_rlc_energy_ledger(request(second_req))
        for port in ("left", "right"):
            for field in energy._MAPS[:3]: self.assertEnergy(out["totals"][field][port], first["totals"][field][port]+second["totals"][field][port])
            self.assertEnergy(out["totals"][energy._MAPS[3]][port], first["totals"][energy._MAPS[3]][port])
            self.assertEnergy(out["totals"][energy._MAPS[4]][port], second["totals"][energy._MAPS[4]][port])
        refined = deepcopy(transient); refined["output_times_s"] = sorted(set(refined["output_times_s"]+[.011, .47, .61]))
        refinement = energy.run_rlc_energy_ledger(request(refined))
        for field in energy._MAPS[:3]:
            for port in ("left", "right"): self.assertEnergy(refinement["totals"][field][port], out["totals"][field][port])

    def test_one_fit_exact_trajectory_preservation_and_private_hook_copies(self):
        transient = memory_request(); baseline = energy.initialized.run_initialized_rlc_network_transient(transient)
        actual_fit = energy.rlc.rational.fit_sparameter_rational
        with patch.object(energy.rlc.rational, "fit_sparameter_rational", wraps=actual_fit) as fitted:
            result = energy.run_rlc_energy_ledger(request(transient))
            self.assertEqual(fitted.call_count, 1)
        self.assertEqual(result["transient_result"], baseline)
        observed = []
        def destructive_observer(context, left, right, *arrays):
            observed.append((left, right))
            for value in context.values():
                if isinstance(value, np.ndarray): value[:] = 0.
            for value in arrays: value[:] = 1e20
        self.assertEqual(energy.initialized._run(transient, interval_observer=destructive_observer), baseline)
        self.assertEqual(len(observed), baseline["diagnostics"]["interval_count"])
        old_request = {key: deepcopy(transient[key]) for key in ("fit_request", "terminations", "output_times_s")}
        old_request["contract"] = energy.rlc.REQUEST_CONTRACT
        old_baseline = energy.rlc.run_rlc_network_transient(old_request)
        self.assertEqual(energy.rlc._run(old_request, interval_observer=destructive_observer), old_baseline)

    def test_mixed_rl_rc_resistive_analytic_integrals_reference_and_time_scaling(self):
        # Independent physical 100-ohm loads. RL: L I' = 2-(R+100)I;
        # RC: C V' = (2-V)/R-V/100. The third port is memoryless.
        # Changing Z0 cannot change physical energy; scaling L,C,t together
        # leaves V/I unchanged and multiplies every work/storage term by tscale.
        ports = ["rl", "rc", "resistive"]
        times = [0., .003, .02, .1, .3]
        for pure_r in (25., 0.):
            baseline = None
            for reference in (1., 25., 100., 1000.):
                for tscale in (1., .001):
                    with self.subTest(resistance=pure_r, reference=reference, time_scale=tscale):
                        transient = transient_request()
                        fit = one_fit(pole=5/tscale, direct=0., residue=0.)
                        scattering = (100-reference)/(100+reference)
                        matrix = [[{"real": scattering if i == j else 0., "imag": 0.}
                                   for j in range(3)] for i in range(3)]
                        fit["source"].update(port_names=ports, reference_impedance_ohm=reference,
                                             s_parameters=[deepcopy(matrix) for _ in fit["source"]["frequencies_hz"]])
                        transient["fit_request"] = fit
                        transient["terminations"] = [
                            term("resistive", pure_r, 0., 0., (0., .3*tscale), (2., 2.)),
                            term("rc", 20., 0., .004*tscale, (0., .3*tscale), (2., 2.)),
                            term("rl", 10., tscale, 0., (0., .3*tscale), (2., 2.))]
                        transient["output_times_s"] = [t*tscale for t in times]
                        transient["initial_state"].update(
                            fit_request_digest=energy.rlc.rational.sampling._digest(fit),
                            fit_state_sqrt_w=[[0., 0., 0.]],
                            inductor_current_a_by_port={"rl": .12},
                            capacitor_voltage_v_by_port={"rc": -.7})
                        out = energy.run_rlc_energy_ledger(request(transient))

                        def physical(t, port):
                            if port == "rl":
                                current = 2/110+(.12-2/110)*math.exp(-110*t)
                                return 100*current, current, current, .5*current**2
                            if port == "rc":
                                voltage = 2*100/120+(-.7-2*100/120)*math.exp(-15*t)
                                return voltage, voltage/100, (2-voltage)/20, .002*voltage**2
                            current = 2/(pure_r+100)
                            return 100*current, current, current, 0.

                        for interval, left, right in zip(out["intervals"], times, times[1:]):
                            for port, resistance in zip(ports, (10., 20., pure_r)):
                                def source_power(t): return 2*physical(t, port)[2]
                                def network_power(t):
                                    voltage, current, _, _ = physical(t, port)
                                    return voltage*current
                                def resistor_power(t): return resistance*physical(t, port)[2]**2
                                for field, function in zip(energy._MAPS[:3], (source_power, network_power, resistor_power)):
                                    expected = tscale*quad(function, left, right, epsabs=1e-13)[0]
                                    self.assertEnergy(interval[field][port], expected)
                                for field, t in ((energy._MAPS[3], left), (energy._MAPS[4], right)):
                                    self.assertEnergy(interval[field][port], tscale*physical(t, port)[3])
                                self.assertEnergy(interval[energy._MAPS[5]][port], 0.)
                        if baseline is None:
                            baseline = out
                        for field in energy._MAPS:
                            for port in ports:
                                self.assertEnergy(out["totals"][field][port], tscale*baseline["totals"][field][port])
                        if pure_r == 0.:
                            self.assertEqual(out["totals"]["resistor_heat_j_by_port"]["resistive"], 0.)

    def test_signed_source_network_work_and_exact_zero_resistance_heat(self):
        transient = transient_request(voltage=3., current=-.2)
        out = energy.run_rlc_energy_ledger(request(transient))
        self.assertLess(out["intervals"][0]["source_work_j_by_port"]["input"], 0.)
        transient = transient_request(voltage=0., current=0.); transient["fit_request"] = one_fit(direct=2., residue=0.)
        transient["initial_state"]["fit_request_digest"] = energy.rlc.rational.sampling._digest(transient["fit_request"])
        out = energy.run_rlc_energy_ledger(request(transient))
        self.assertLess(out["totals"]["network_work_j_by_port"]["input"], 0.)
        transient = transient_request(resistance=0.)
        out = energy.run_rlc_energy_ledger(request(transient))
        self.assertEqual(out["totals"]["resistor_heat_j_by_port"]["input"], 0.)
        self.assertTrue(all(i["resistor_heat_j_by_port"]["input"] == 0. for i in out["intervals"]))

    def test_invalid_precision_work_and_cancellation_admissions(self):
        for key, value in (("relative_tolerance", True), ("relative_tolerance", 0.), ("relative_tolerance", 1e-5),
                           ("absolute_tolerance_j", 0.), ("absolute_tolerance_j", float("inf")), ("extra", 1)):
            req = request(); req[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(energy.SParameterRlcEnergyError): energy.run_rlc_energy_ledger(req)
        with patch.object(energy, "_MAX_WORK", 1), patch.object(energy, "expm", side_effect=AssertionError("ledger preflight must run first")):
            with self.assertRaisesRegex(energy.SParameterRlcEnergyError, "work"): energy.run_rlc_energy_ledger(request())
        req = request(); req["relative_tolerance"] = 1e-30; req["absolute_tolerance_j"] = 1e-30
        with self.assertRaises(energy.SParameterRlcEnergyError): energy.run_rlc_energy_ledger(req)
        with self.assertRaisesRegex(energy.SParameterRlcEnergyError, "underflow"):
            energy._gramian(np.array([[5e-324, 1.], [0., 0.]]), np.array([1., 0.]), 1, lambda: None)
        with self.assertRaisesRegex(energy.SParameterRlcEnergyError, "underflow"):
            energy._product_integral(np.array([1e-200]), np.array([1e-200]), np.eye(1), 1.)
        calls = []
        energy.run_rlc_energy_ledger(request(), cancel_check=lambda: calls.append(1) or False)
        for threshold in (1, 20, len(calls)):
            seen = []
            def cancel(): seen.append(1); return len(seen) >= threshold
            with self.subTest(threshold=threshold), self.assertRaises(energy.SParameterRlcEnergyError) as caught:
                energy.run_rlc_energy_ledger(request(), cancel_check=cancel)
            self.assertIn("CANCELLED", caught.exception.code)


if __name__ == "__main__": unittest.main()
