# SPDX-License-Identifier: Apache-2.0
"""Original physical KCL/KVL references; preset voltage tolerance 2e-10+1e-9 rel."""
from copy import deepcopy
from itertools import product
import math
import unittest
from unittest.mock import patch

import numpy as np
from scipy.linalg import expm

from python.spike_core import sparameter_multi_aggressor as multi
from tests.python.test_sparameter_rlc_initial import request as initial_request
from tests.python.test_sparameter_rlc_terminated import term, step_reference
from tests.python.test_sparameter_transient import one_fit


def request(reference=50., time_scale=1., memory=False):
    ports = ["victim", "a", "b", "fixed"]
    n = len(ports); conductance = .02*np.eye(n)-.002*np.ones((n, n))
    common = np.ones(n)/math.sqrt(n)
    inductance_network = 2.*time_scale
    direct = np.linalg.solve(np.eye(n)+reference*conductance, np.eye(n)-reference*conductance)
    pole = reference/(inductance_network*(1+reference*.012)) if memory else 5/time_scale
    residue = -2/(1+reference*.012)*np.outer(common, common) if memory else np.zeros((n, n))
    fit = one_fit(pole=pole)
    frequencies = fit["source"]["frequencies_hz"]
    matrices = [direct+residue/(1+2j*math.pi*f/pole) for f in frequencies]
    fit["source"].update(port_names=ports, reference_impedance_ohm=reference,
                         s_parameters=[[[{"real": float(z.real), "imag": float(z.imag)} for z in row] for row in matrix] for matrix in matrices])
    transient = initial_request(); transient["fit_request"] = fit
    r = [12., 10., 20., 15.]; l = [1., 1.5, 2., .8]; c = [.004, .006, .005, .008]
    times = [(0., .2, .6, 1.), (0., .1, .4, .8, 1.), (0., .3, .55, 1.), (0., .15, .7, 1.)]
    values = [(.3, .3, -.1, .2), (0., 3.3, 3.3, 0., .5), (-1., .8, -1.2, .2), (.5, -.4, 1., .7)]
    transient["terminations"] = list(reversed([term(p, r[i], l[i]*time_scale, c[i]*time_scale,
        tuple(t*time_scale for t in times[i]), values[i]) for i, p in enumerate(ports)]))
    transient["output_times_s"] = [t*time_scale for t in (0., .04, .1, .22, .4, .55, .8, 1.)]
    physical_initial = np.r_[[-.2, .4, -.1, .3], [.02, -.01, .03, -.02], -.08 if memory else 0.]
    transient["initial_state"].update(fit_request_digest=multi.sampling._digest(fit),
        fit_state_sqrt_w=[list(.5*math.sqrt(reference)*physical_initial[-1]*common)],
        inductor_current_a_by_port=dict(zip(ports, physical_initial[n:2*n])),
        capacitor_voltage_v_by_port=dict(zip(ports, physical_initial[:n])))
    result = {"contract": multi.REQUEST_CONTRACT, "transient_request": transient, "victim_port": "victim",
              "aggressors": [{"port_name": "b", "reference_voltage_v": -.4}, {"port_name": "a", "reference_voltage_v": 1.65}],
              "lower_limit_v": -.5, "upper_limit_v": .7}
    return result, conductance, physical_initial, inductance_network if memory else None


def physical(req, conductance, initial, network_l=None):
    """Direct physical [V,Isource,Icommon] ODE, no scattering/closure helpers."""
    ports = req["fit_request"]["source"]["port_names"]; n = len(ports)
    terms = {t["port_name"]: t for t in req["terminations"]}
    r, l, c = [np.array([terms[p][key] for p in ports]) for key in ("resistance_ohm", "inductance_h", "capacitance_f")]
    states = 2*n+1; generator = np.zeros((states+2*n, states+2*n))
    generator[:n, :n] = -conductance/c[:, None]; generator[:n, n:2*n] = np.diag(1/c)
    generator[n:2*n, :n] = -np.diag(1/l); generator[n:2*n, n:2*n] = -np.diag(r/l)
    generator[n:2*n, states:states+n] = np.diag(1/l)
    generator[states:states+n, states+n:] = np.eye(n)
    if network_l is not None:
        common = np.ones(n)/math.sqrt(n)
        generator[:n, 2*n] = -common/c; generator[2*n, :n] = common/network_l
    grid = sorted(set(req["output_times_s"]) | {point["time_s"] for t in terms.values() for point in t["voltage_points"]})
    state = np.asarray(initial).copy(); result = {0.: state.copy()}
    for left, right in zip(grid, grid[1:]):
        sources, slopes = [], []
        for port in ports:
            points = terms[port]["voltage_points"]
            j = next(j for j in range(len(points)-1) if points[j]["time_s"] <= left < points[j+1]["time_s"])
            a, b = points[j:j+2]
            slope = (b["voltage_v"]-a["voltage_v"])/(b["time_s"]-a["time_s"])
            sources.append(a["voltage_v"]+slope*(left-a["time_s"])); slopes.append(slope)
        state = (expm((right-left)*generator)@np.r_[state, sources, slopes])[:states]
        result[right] = state.copy()
    return np.array([result[t][0] for t in req["output_times_s"]])


def signed_request(req, signs):
    result = deepcopy(req["transient_request"])
    bias = {item["port_name"]: item["reference_voltage_v"] for item in req["aggressors"]}
    for item in result["terminations"]:
        port = item["port_name"]
        if port in bias:
            for point in item["voltage_points"]:
                point["voltage_v"] = bias[port]+signs[port]*(point["voltage_v"]-bias[port])
    return result


class MultiAggressorTests(unittest.TestCase):
    def assertVoltage(self, actual, expected):
        np.testing.assert_allclose(actual, expected, atol=2e-10, rtol=1e-9)

    def test_coupled_physical_all_patterns_memory_common_initial_and_witnesses(self):
        for memory in (False, True):
            req, g, initial, network_l = request(memory=memory); before = deepcopy(req)
            actual_fit = multi.rlc.rational.fit_sparameter_rational
            with patch.object(multi.rlc.rational, "fit_sparameter_rational", wraps=actual_fit) as fit:
                result = multi.run_multi_aggressor_crosstalk(req)
                self.assertEqual(fit.call_count, 5)
            self.assertEqual(req, before)
            self.assertEqual(result["source_request"], req["transient_request"])
            self.assertEqual(result["aggressor_port_names"], ["a", "b"])
            self.assertEqual([c["port_name"] for c in result["contributions"]], ["a", "b"])
            self.assertEqual(result["baseline_result"]["initial_state"], req["transient_request"]["initial_state"])
            patterns = [physical(signed_request(req, dict(zip(("a", "b"), signs))), g, initial, network_l)
                        for signs in product((-1, 1), repeat=2)]
            self.assertVoltage([e["minimum_voltage_v"] for e in result["envelope"]], np.min(patterns, axis=0))
            self.assertVoltage([e["maximum_voltage_v"] for e in result["envelope"]], np.max(patterns, axis=0))
            baseline_req = signed_request(req, {"a": 0, "b": 0})
            self.assertVoltage([e["baseline_voltage_v"] for e in result["envelope"]], physical(baseline_req, g, initial, network_l))
            for contribution in result["contributions"]:
                basis = deepcopy(req["transient_request"])
                bias = {a["port_name"]: a["reference_voltage_v"] for a in req["aggressors"]}
                for t in basis["terminations"]:
                    for point in t["voltage_points"]:
                        point["voltage_v"] = point["voltage_v"]-bias[t["port_name"]] if t["port_name"] == contribution["port_name"] else 0.
                basis["initial_state"]["fit_state_sqrt_w"] = [[0.]*4]
                for key in ("inductor_current_a_by_port", "capacitor_voltage_v_by_port"):
                    basis["initial_state"][key] = {port: 0. for port in basis["initial_state"][key]}
                self.assertEqual(contribution["input_digest"], multi.sampling._digest(basis))
                self.assertVoltage(contribution["victim_voltage_v"], physical(basis, g, np.zeros_like(initial), network_l))
            for name, field in (("worst_upper_pattern", "maximum_voltage_v"), ("worst_lower_pattern", "minimum_voltage_v")):
                witness = result[name]; direct = signed_request(req, witness["polarity_by_port"])
                # Independent reconstruction uses exact original values for +1,
                # matching the specified source identity without rounding it.
                for t, original in zip(direct["terminations"], req["transient_request"]["terminations"]):
                    if witness["polarity_by_port"].get(t["port_name"]) == 1: t["voltage_points"] = deepcopy(original["voltage_points"])
                self.assertEqual(witness["verified_input_digest"], multi.sampling._digest(direct))
                self.assertVoltage(witness["verified_victim_voltage_v"], physical(direct, g, initial, network_l))
                sample = req["transient_request"]["output_times_s"].index(witness["sample_time_s"])
                self.assertVoltage(witness["verified_victim_voltage_v"][sample], result["envelope"][sample][field])
            self.assertEqual(result["diagnostics"]["solution_count"], 5)
            if memory:
                self.assertGreater(np.linalg.norm(result["baseline_result"]["fit_result"]["model"]["residues"]), .1)

    def test_one_aggressor_independent_analytic_modal_step(self):
        req, _, _, _ = request(); source = req["transient_request"]
        g = np.array([[.02, -.005], [-.005, .02]])
        direct = np.linalg.solve(np.eye(2)+50*g, np.eye(2)-50*g)
        fit = one_fit(direct=0., residue=0.); fit["source"]["port_names"] = ["victim", "a"]
        matrix = [[{"real": float(z), "imag": 0.} for z in row] for row in direct]
        fit["source"]["s_parameters"] = [deepcopy(matrix) for _ in fit["source"]["frequencies_hz"]]
        source["fit_request"] = fit; source["terminations"] = [term("a"), term("victim", values=(0., 0.))]
        source["initial_state"].update(fit_request_digest=multi.sampling._digest(fit), fit_state_sqrt_w=[[0., 0.]],
            inductor_current_a_by_port={"victim": 0., "a": 0.}, capacitor_voltage_v_by_port={"victim": 0., "a": 0.})
        req["aggressors"] = [{"port_name": "a", "reference_voltage_v": 0.}]
        out = multi.run_multi_aggressor_crosstalk(req)
        expected = [.5*(step_reference(t, conductance=.015)[0]-step_reference(t, conductance=.025)[0]) for t in source["output_times_s"]]
        self.assertVoltage(out["contributions"][0]["victim_voltage_v"], expected)
        self.assertVoltage([e["maximum_voltage_v"] for e in out["envelope"]], np.abs(expected))
        self.assertVoltage([e["minimum_voltage_v"] for e in out["envelope"]], -np.abs(expected))

    def test_zero_deviations_exact_ties_source_order_and_observation_only(self):
        req, _, _, _ = request()
        for t in req["transient_request"]["terminations"]:
            for p in t["voltage_points"]: p["voltage_v"] = 0.
        state = req["transient_request"]["initial_state"]
        state["fit_state_sqrt_w"] = [[0.]*4]
        for name in ("inductor_current_a_by_port", "capacitor_voltage_v_by_port"):
            state[name] = {p: 0. for p in state[name]}
        for a in req["aggressors"]: a["reference_voltage_v"] = 0.
        req["transient_request"]["output_times_s"] = [.04, .1]
        out = multi.run_multi_aggressor_crosstalk(req)
        self.assertEqual(len(out["envelope"]), 2)
        self.assertEqual(out["worst_upper_pattern"]["sample_time_s"], .04)
        self.assertEqual(out["worst_lower_pattern"]["sample_time_s"], .04)
        self.assertEqual(out["worst_upper_pattern"]["polarity_by_port"], {"a": 1, "b": 1})
        self.assertEqual(out["worst_lower_pattern"]["polarity_by_port"], {"a": -1, "b": -1})
        self.assertTrue(all(e["minimum_voltage_v"] == e["maximum_voltage_v"] == 0. for e in out["envelope"]))

    def test_reference_and_physical_time_scale_invariance(self):
        base = multi.run_multi_aggressor_crosstalk(request(memory=True)[0])
        for reference, scale in ((1., 1.), (25., .001), (100., 1.), (1000., .001)):
            out = multi.run_multi_aggressor_crosstalk(request(reference, scale, memory=True)[0])
            for key in ("baseline_voltage_v", "minimum_voltage_v", "maximum_voltage_v", "lower_margin_v", "upper_margin_v"):
                self.assertVoltage([e[key] for e in out["envelope"]], [e[key] for e in base["envelope"]])
            for name in ("worst_upper_pattern", "worst_lower_pattern"):
                self.assertEqual(out[name]["polarity_by_port"], base[name]["polarity_by_port"])
                self.assertVoltage(out[name]["verified_victim_voltage_v"], base[name]["verified_victim_voltage_v"])
                self.assertAlmostEqual(out[name]["sample_time_s"], scale*base[name]["sample_time_s"])

    def test_invalid_family_resources_arithmetic_before_fit_and_cancel(self):
        req = request()[0]
        invalid = []
        for port in ("missing", "victim", "b", True):
            candidate = deepcopy(req); candidate["aggressors"][1]["port_name"] = port; invalid.append(candidate)
        for bias in (True, float("inf"), float("nan")):
            candidate = deepcopy(req); candidate["aggressors"][0]["reference_voltage_v"] = bias; invalid.append(candidate)
        candidate = deepcopy(req); candidate["aggressors"] *= 4; invalid.append(candidate)
        candidate = deepcopy(req); candidate["aggressors"] = []; invalid.append(candidate)
        candidate = deepcopy(req); candidate["upper_limit_v"] = candidate["lower_limit_v"]; invalid.append(candidate)
        candidate = deepcopy(req); candidate["victim_port"] = "missing"; invalid.append(candidate)
        candidate = deepcopy(req); candidate["extra"] = 0; invalid.append(candidate)
        candidate = deepcopy(req); candidate["aggressors"][0]["reference_voltage_v"] = 1e308; invalid.append(candidate)
        candidate = deepcopy(req); candidate["transient_request"]["initial_state"]["fit_request_digest"] = "0"*64; invalid.append(candidate)
        for candidate in invalid:
            with patch.object(multi.rlc.rational, "fit_sparameter_rational", side_effect=AssertionError("admission before fit")):
                with self.assertRaises(multi.SParameterMultiAggressorError): multi.run_multi_aggressor_crosstalk(candidate)
        for name in ("_MAX_WORK", "_MAX_RESULT_BYTES"):
            with patch.object(multi, name, 1), patch.object(multi.rlc.rational, "fit_sparameter_rational", side_effect=AssertionError("resource preflight before fit")):
                with self.assertRaisesRegex(multi.SParameterMultiAggressorError, "result|work"):
                    multi.run_multi_aggressor_crosstalk(req)
        calls = []
        multi.run_multi_aggressor_crosstalk(req, cancel_check=lambda: calls.append(1) or False)
        for threshold in (1, len(calls)//2, len(calls)):
            seen = []
            def cancel(): seen.append(1); return len(seen) >= threshold
            with self.assertRaises(multi.SParameterMultiAggressorError) as caught:
                multi.run_multi_aggressor_crosstalk(req, cancel_check=cancel)
            self.assertIn("CANCELLED", caught.exception.code)

    def test_failed_direct_witness_has_no_successful_partial_result(self):
        actual = multi.initialized.run_initialized_rlc_network_transient; calls = []
        def corrupt(request, **kwargs):
            out = actual(request, **kwargs); calls.append(1)
            if len(calls) == 4: out["points"][2]["port_voltage_v_by_port"]["victim"] += .1
            return out
        with patch.object(multi.initialized, "run_initialized_rlc_network_transient", side_effect=corrupt):
            with self.assertRaisesRegex(multi.SParameterMultiAggressorError, "superposition"):
                multi.run_multi_aggressor_crosstalk(request()[0])


if __name__ == "__main__": unittest.main()
