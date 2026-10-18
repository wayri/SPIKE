# SPDX-License-Identifier: Apache-2.0
"""Physical V/I and wave references; preset 2e-10 SI + 1e-9 relative."""
from copy import deepcopy
import math
import unittest
from unittest.mock import patch

import numpy as np
from scipy.linalg import expm

from python.spike_core import sparameter_reflectometry as reflectometry
from tests.python.test_sparameter_rlc_initial import request as transient_request, memory_request, analytic_loaded
from tests.python.test_sparameter_rlc_terminated import term
from tests.python.test_sparameter_transient import one_fit


def request(transient=None, probe="input"):
    return {"contract": reflectometry.REQUEST_CONTRACT, "transient_request": transient or transient_request(),
            "probe_port": probe, "minimum_incident_voltage_v": 1e-9, "minimum_current_a": 1e-9}


class ReflectometryTests(unittest.TestCase):
    def assertPhysical(self, actual, expected):
        self.assertAlmostEqual(actual, expected, delta=2e-10+1e-9*abs(expected))

    def check_point(self, point, voltage, current, reference):
        plus, minus = .5*(voltage+reference*current), .5*(voltage-reference*current)
        for key, expected in (("network_voltage_v", voltage), ("network_current_a", current),
                              ("incident_voltage_v", plus), ("reflected_voltage_v", minus),
                              ("instantaneous_network_power_w", voltage*current)):
            self.assertPhysical(point[key], expected)
        if point["reflection_status"] == "resolved": self.assertPhysical(point["reflection_coefficient"], minus/plus)
        if point["impedance_status"] == "resolved": self.assertPhysical(point["apparent_impedance_ohm"], voltage/current)

    def test_analytic_resistor_port_uses_network_current_one_fit_and_identity(self):
        req = request(); original = deepcopy(req)
        fit_actual = reflectometry.rlc.rational.fit_sparameter_rational
        with patch.object(reflectometry.rlc.rational, "fit_sparameter_rational", wraps=fit_actual) as fit:
            out = reflectometry.run_network_reflectometry(req)
            self.assertEqual(fit.call_count, 1)
        self.assertEqual(req, original)
        self.assertEqual(out["input_digest"], reflectometry.sampling._digest(req))
        self.assertEqual(out["transient_result"], reflectometry.initialized.run_initialized_rlc_network_transient(req["transient_request"]))
        self.assertGreater(abs(out["transient_result"]["points"][0]["source_current_a_by_port"]["input"]-out["points"][0]["network_current_a"]), .1)
        for point in out["points"]:
            voltage = analytic_loaded(point["time_s"], 10.)[0]
            self.check_point(point, voltage, .01*voltage, 50.)
            self.assertPhysical(point["reflection_coefficient"], 1/3)
            self.assertPhysical(point["apparent_impedance_ohm"], 100.)
        self.assertEqual(out["diagnostics"]["resolved_impedance_count"], len(out["points"]))

    def test_actual_fitted_inductor_memory_against_physical_ode(self):
        req = request(memory_request()); out = reflectometry.run_network_reflectometry(req)
        generator = np.array([[-2.5, 250., -250., 0.], [-1., -10., 0., 2.], [.5, 0., 0., 0.], [0., 0., 0., 0.]])
        for point in out["points"]:
            voltage, _, inductor_current, _ = expm(point["time_s"]*generator)@[-.7, .12, -.08, 1.]
            self.check_point(point, voltage, .01*voltage+inductor_current, 50.)
        impedances = [p["apparent_impedance_ohm"] for p in out["points"] if p["impedance_status"] == "resolved"]
        self.assertGreater(max(impedances)-min(impedances), 1.)
        self.assertGreater(np.linalg.norm(out["transient_result"]["fit_result"]["model"]["residues"]), 1.)

    def test_coupled_driven_ports_and_common_state_physical_reference(self):
        source = transient_request(); g = np.array([[.02, -.004], [-.004, .01]])
        s = np.linalg.solve(np.eye(2)+50*g, np.eye(2)-50*g)
        matrix = [[{"real": float(z), "imag": 0.} for z in row] for row in s]
        fit = source["fit_request"]; fit["source"]["port_names"] = ["left", "right"]
        fit["source"]["s_parameters"] = [deepcopy(matrix) for _ in fit["source"]["frequencies_hz"]]
        source["terminations"] = [term("right", 25., 2., .009, values=(-1., -1.)), term("left")]
        source["initial_state"].update(fit_request_digest=reflectometry.sampling._digest(fit), fit_state_sqrt_w=[[0., 0.]],
            inductor_current_a_by_port={"right": .13, "left": -.1}, capacitor_voltage_v_by_port={"right": -.4, "left": .7})
        c, l = np.array([.004, .009]), np.array([1., 2.])
        generator = np.zeros((6, 6)); generator[:2, :2] = -g/c[:, None]; generator[:2, 2:4] = np.diag(1/c)
        generator[2:4, :2] = -np.diag(1/l); generator[2:4, 2:4] = -np.diag(np.array([10., 25.])/l)
        generator[2:4, 4:] = np.diag(1/l)
        for j, probe in enumerate(("left", "right")):
            out = reflectometry.run_network_reflectometry(request(source, probe))
            for point in out["points"]:
                physical = expm(point["time_s"]*generator)@[.7, -.4, -.1, .13, 2., -1.]
                self.check_point(point, physical[j], (g@physical[:2])[j], 50.)

    def test_floor_equality_nulls_open_current_and_signed_active_response(self):
        req = request(); base = reflectometry.run_network_reflectometry(req); first = base["points"][0]
        req["minimum_incident_voltage_v"] = abs(first["incident_voltage_v"])
        out = reflectometry.run_network_reflectometry(req)
        self.assertEqual(out["points"][0]["reflection_status"], "incident_below_floor")
        self.assertEqual(out["points"][0]["impedance_status"], "incident_below_floor")
        self.assertIsNone(out["points"][0]["reflection_coefficient"]); self.assertIsNone(out["points"][0]["apparent_impedance_ohm"])
        req = request(); req["minimum_current_a"] = abs(first["network_current_a"])
        out = reflectometry.run_network_reflectometry(req)
        self.assertEqual(out["points"][0]["reflection_status"], "resolved")
        self.assertEqual(out["points"][0]["impedance_status"], "current_below_floor")
        self.assertIsNone(out["points"][0]["apparent_impedance_ohm"])
        zero = reflectometry.run_network_reflectometry(request(transient_request(voltage=0., current=0.)))
        self.assertEqual(zero["points"][0]["reflection_status"], "incident_below_floor")
        for direct, impedance in ((1., None), (2., -150.)):
            transient = transient_request(); transient["fit_request"] = one_fit(direct=direct, residue=0.)
            transient["initial_state"]["fit_request_digest"] = reflectometry.sampling._digest(transient["fit_request"])
            out = reflectometry.run_network_reflectometry(request(transient))
            for point in out["points"]:
                self.assertPhysical(point["reflection_coefficient"], direct)
                if impedance is None:
                    self.assertEqual(point["impedance_status"], "current_below_floor")
                    self.assertIsNone(point["apparent_impedance_ohm"])
                    self.assertPhysical(point["network_current_a"], 0.)
                else:
                    self.assertPhysical(point["apparent_impedance_ohm"], impedance)
                    self.assertLess(point["instantaneous_network_power_w"], 0.)

    def test_reference_time_units_and_shared_observation_refinement(self):
        base = reflectometry.run_network_reflectometry(request(memory_request()))
        for reference in (1., 25., 100., 1000.):
            out = reflectometry.run_network_reflectometry(request(memory_request(reference)))
            for point, expected in zip(out["points"], base["points"]):
                for field in ("network_voltage_v", "network_current_a", "instantaneous_network_power_w", "apparent_impedance_ohm"):
                    self.assertPhysical(point[field], expected[field])
                self.check_point(point, expected["network_voltage_v"], expected["network_current_a"], reference)
        base = reflectometry.run_network_reflectometry(request())
        scaled = transient_request()
        for t in scaled["terminations"]:
            t["inductance_h"] *= .001; t["capacitance_f"] *= .001
            for p in t["voltage_points"]: p["time_s"] *= .001
        scaled["output_times_s"] = [t*.001 for t in scaled["output_times_s"]]
        out = reflectometry.run_network_reflectometry(request(scaled))
        for a, b in zip(out["points"], base["points"]):
            for field in ("network_voltage_v", "network_current_a", "reflection_coefficient", "apparent_impedance_ohm"):
                self.assertPhysical(a[field], b[field])
        refined = transient_request(); refined["output_times_s"] = sorted(set(refined["output_times_s"]+[.003, .17, .63]))
        out = reflectometry.run_network_reflectometry(request(refined)); shared = {p["time_s"]: p for p in out["points"]}
        for b in base["points"]:
            for field in ("network_voltage_v", "network_current_a", "reflection_coefficient", "apparent_impedance_ohm"):
                self.assertPhysical(shared[b["time_s"]][field], b[field])

    def test_invalid_resource_precision_corrupted_wave_and_cancellation_fail_closed(self):
        for key, value in (("probe_port", "unknown"), ("probe_port", True), ("minimum_incident_voltage_v", 0.),
                           ("minimum_current_a", -1.), ("minimum_current_a", True), ("minimum_current_a", float("inf")), ("extra", 0)):
            req = request(); req[key] = value
            with patch.object(reflectometry.rlc.rational, "fit_sparameter_rational", side_effect=AssertionError("admit before fit")):
                with self.assertRaises(reflectometry.SParameterReflectometryError): reflectometry.run_network_reflectometry(req)
        for limit in ("_MAX_WORK", "_MAX_RESULT_BYTES"):
            with patch.object(reflectometry, limit, 1), patch.object(reflectometry.rlc.rational, "fit_sparameter_rational", side_effect=AssertionError("resource preflight")):
                with self.assertRaises(reflectometry.SParameterReflectometryError): reflectometry.run_network_reflectometry(request())
        actual = reflectometry.initialized.run_initialized_rlc_network_transient
        for field, value in (("incident_wave_sqrt_w_by_port", .3), ("outgoing_wave_sqrt_w_by_port", 1e308), ("port_current_a_by_port", .1)):
            def corrupt(req, **kwargs):
                out = actual(req, **kwargs); out["points"][0][field]["input"] = value; return out
            with patch.object(reflectometry.initialized, "run_initialized_rlc_network_transient", side_effect=corrupt):
                with self.assertRaises(reflectometry.SParameterReflectometryError): reflectometry.run_network_reflectometry(request())
        with self.assertRaises(reflectometry.SParameterReflectometryError): reflectometry._finite(0., "underflow", True)
        calls = []; reflectometry.run_network_reflectometry(request(), cancel_check=lambda: calls.append(1) or False)
        for threshold in (1, len(calls)//2, len(calls)):
            seen = []
            def cancel(): seen.append(1); return len(seen) >= threshold
            with self.assertRaises(reflectometry.SParameterReflectometryError) as caught:
                reflectometry.run_network_reflectometry(request(), cancel_check=cancel)
            self.assertIn("CANCELLED", caught.exception.code)


if __name__ == "__main__": unittest.main()
