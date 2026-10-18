# SPDX-License-Identifier: Apache-2.0
"""Original delay/geometric-wave references, not production bounce recursion.

Preset V/I tolerance2e-10 SI+1e-9 relative; density1e-14 J/m+1e-9
relative, and finite-pulse total energy1e-20 J+1e-9 relative.
"""
from copy import deepcopy
from fractions import Fraction
import math
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core import lossless_line_transient as line


def boundary(resistance, points):
    return {"resistance_ohm": resistance, "voltage_points": [{"time_s": t, "voltage_v": v} for t, v in points]}


def request(left_r=25., right_r=100.):
    return {"contract": line.REQUEST_CONTRACT, "length_m": 5., "inductance_h_per_m": 250e-9,
            "capacitance_f_per_m": 100e-12,
            "left_boundary": boundary(left_r, [(0., 0.), (10e-9, 1.), (200e-9, 1.)]),
            "right_boundary": boundary(right_r, [(0., 0.), (200e-9, 0.)]),
            "probes": [{"id": name, "fractional_position": q} for name, q in (("right", 1.), ("interior", .37), ("left", 0.))],
            "output_times_s": [0., 5e-9, 10e-9, 12.5e-9, 25e-9, 30e-9, 35e-9, 50e-9, 75e-9, 100e-9, 150e-9, 200e-9]}


def source_value(time, boundary):
    if time < 0: return 0.
    points = boundary["voltage_points"]
    return float(np.interp(time, [p["time_s"] for p in points], [p["voltage_v"] for p in points]))


def geometric_waves(req, time, position):
    """Separate even/odd round-trip geometric series for both source drives."""
    impedance = math.sqrt(req["inductance_h_per_m"]/req["capacitance_f_per_m"])
    delay = req["length_m"]*math.sqrt(req["inductance_h_per_m"]*req["capacitance_f_per_m"])
    left, right = req["left_boundary"], req["right_boundary"]
    gl = (left["resistance_ohm"]-impedance)/(left["resistance_ohm"]+impedance)
    gr = (right["resistance_ohm"]-impedance)/(right["resistance_ohm"]+impedance)
    al, ar = impedance/(left["resistance_ohm"]+impedance), impedance/(right["resistance_ohm"]+impedance)
    forward_time, backward_time = time-position*delay, time-(1-position)*delay
    forward, backward = [], []
    for m in range(int(time/delay)+2):
        weight = (gl*gr)**m
        forward.append(weight*(al*source_value(forward_time-2*m*delay, left)+gl*ar*source_value(forward_time-(2*m+1)*delay, right)))
        backward.append(weight*(ar*source_value(backward_time-2*m*delay, right)+gr*al*source_value(backward_time-(2*m+1)*delay, left)))
    return math.fsum(forward), math.fsum(backward)


class LosslessLineTests(unittest.TestCase):
    def assertVI(self, actual, expected):
        self.assertAlmostEqual(actual, expected, delta=2e-10+1e-9*abs(expected))

    def assertDensity(self, actual, expected):
        self.assertAlmostEqual(actual, expected, delta=1e-14+1e-9*abs(expected))

    def check_fields(self, req, out):
        impedance = out["characteristic_impedance_ohm"]
        for point in out["points"]:
            for probe in point["probe_values"]:
                f, b = geometric_waves(req, point["time_s"], probe["fractional_position"])
                voltage, current = f+b, (f-b)/impedance
                for key, expected in (("forward_voltage_v", f), ("backward_voltage_v", b), ("voltage_v", voltage),
                                      ("current_left_to_right_a", current), ("transported_power_w", (f*f-b*b)/impedance)):
                    self.assertVI(probe[key], expected)
                self.assertDensity(probe["energy_density_j_per_m"], req["capacitance_f_per_m"]*(f*f+b*b))
            for index, name in enumerate(("left", "right")):
                boundary = point["boundary_values"][name]
                f, b = geometric_waves(req, point["time_s"], index)
                into = (f-b)/impedance*(1 if index == 0 else -1)
                self.assertVI(boundary["voltage_v"], f+b)
                self.assertVI(boundary["current_into_line_a"], into)
                self.assertVI(boundary["source_voltage_v"]-boundary["voltage_v"]-req[name+"_boundary"]["resistance_ohm"]*into, 0.)
                self.assertVI(boundary["resistor_power_w"], req[name+"_boundary"]["resistance_ohm"]*into*into)

    def test_matched_finite_ramp_exact_delays_and_prearrival_zeros(self):
        req = request(50., 50.); original = deepcopy(req)
        out = line.run_lossless_line_transient(req)
        self.assertEqual(req, original); self.assertEqual(out["source_request"], req)
        self.assertEqual(out["input_digest"], line.sampling._digest(req))
        self.assertVI(out["characteristic_impedance_ohm"], 50.)
        self.assertAlmostEqual(out["one_way_delay_s"], 25e-9, delta=1e-22)
        self.assertAlmostEqual(out["propagation_speed_m_per_s"], 2e8, delta=1e-6)
        self.assertEqual([p["id"] for p in out["points"][0]["probe_values"]], ["right", "interior", "left"])
        self.check_fields(req, out)
        for point in out["points"]:
            for probe in point["probe_values"]:
                self.assertEqual(probe["backward_voltage_v"], 0.)
                if point["time_s"] <= probe["fractional_position"]*25e-9:
                    self.assertEqual(probe["voltage_v"], 0.)

    def test_resistive_first_echo_multiple_bounces_and_both_ends_driven(self):
        req = request(); out = line.run_lossless_line_transient(req); self.check_fields(req, out)
        by_time = {p["time_s"]: p for p in out["points"]}
        # Before the first round trip, left launch is2/3; at100ns the
        # first reflected launch has completed while the second begins at0.
        self.assertVI(by_time[35e-9]["probe_values"][2]["forward_voltage_v"], 2/3)
        self.assertVI(by_time[100e-9]["probe_values"][2]["forward_voltage_v"], (2/3)*(1-1/9))
        req["right_boundary"] = boundary(100., [(0., 0.), (7e-9, -.7), (40e-9, .4), (200e-9, -.2)])
        out = line.run_lossless_line_transient(req); self.check_fields(req, out)
        self.assertTrue(any(p["probe_values"][0]["transported_power_w"] < 0 for p in out["points"]))

    def test_ideal_zero_resistance_full_reflections_remain_finite(self):
        req = request(0., 0.)
        req["left_boundary"]["voltage_points"] = [{"time_s": t, "voltage_v": v} for t, v in ((0., 0.), (10e-9, 1.), (60e-9, -.5), (200e-9, .2))]
        out = line.run_lossless_line_transient(req); self.check_fields(req, out)
        self.assertEqual(out["reflection_coefficient_by_boundary"], {"left": -1., "right": -1.})
        for point in out["points"]:
            for name in ("left", "right"):
                self.assertEqual(point["boundary_values"][name]["resistor_power_w"], 0.)
        self.assertGreaterEqual(out["diagnostics"]["maximum_bounce_depth"], 7)

    def test_matched_finite_pulse_spatial_energy_equals_injected_network_work(self):
        req = request(50., 50.)
        req["left_boundary"] = boundary(50., [(0., 0.), (1e-9, 2.), (2e-9, 0.), (20e-9, 0.)])
        req["right_boundary"] = boundary(50., [(0., 0.), (20e-9, 0.)])
        req["output_times_s"] = [10e-9]
        # At10ns the complete pulse occupies1.6..2.0m. Two-point Gaussian
        # integration on each linear-wave segment integrates squared fields
        # exactly; no production energy-integral routine is used.
        positions = [center+sign*.1/math.sqrt(3) for center in (1.7, 1.9) for sign in (-1, 1)]
        req["probes"] = [{"id": str(i), "fractional_position": x/5} for i, x in enumerate(positions)]
        out = line.run_lossless_line_transient(req)
        spatial_energy = .1*sum(p["energy_density_j_per_m"] for p in out["points"][0]["probe_values"])
        # F has a triangular1V pulse of duration2ns: integral F²/Z dt.
        injected_work = 2e-9/(3*50.)
        self.assertAlmostEqual(spatial_energy, injected_work, delta=1e-20+1e-9*injected_work)
        self.check_fields(req, out)

    def test_observation_refinement_and_distributed_parameter_length_time_scaling(self):
        req = request(); base = line.run_lossless_line_transient(req)
        refined = deepcopy(req); refined["output_times_s"] = sorted(set(req["output_times_s"]+[8e-9, 47e-9, 163e-9]))
        out = line.run_lossless_line_transient(refined); shared = {p["time_s"]: p for p in out["points"]}
        for point in base["points"]: self.assertEqual(shared[point["time_s"]], point)
        for impedance_scale, time_scale, length_scale in ((.1, 1., 1.), (10., 1., 1.), (1., 1000., 1.), (1., 1., 2.)):
            scaled = deepcopy(req)
            scaled["inductance_h_per_m"] *= impedance_scale*time_scale
            scaled["capacitance_f_per_m"] *= time_scale/impedance_scale
            scaled["length_m"] *= length_scale
            for key in ("left_boundary", "right_boundary"):
                scaled[key]["resistance_ohm"] *= impedance_scale
                for point in scaled[key]["voltage_points"]: point["time_s"] *= time_scale*length_scale
            scaled["output_times_s"] = [t*time_scale*length_scale for t in req["output_times_s"]]
            out = line.run_lossless_line_transient(scaled)
            for point, expected in zip(out["points"], base["points"]):
                for a, b in zip(point["probe_values"], expected["probe_values"]):
                    self.assertVI(a["voltage_v"], b["voltage_v"])
                    self.assertVI(a["current_left_to_right_a"], b["current_left_to_right_a"]/impedance_scale)
                    self.assertVI(a["transported_power_w"], b["transported_power_w"]/impedance_scale)
                    self.assertDensity(a["energy_density_j_per_m"], b["energy_density_j_per_m"]*time_scale/impedance_scale)

    def test_invalid_fields_times_initial_history_precision_resources(self):
        invalid = []
        for field, value in (("length_m", 0.), ("inductance_h_per_m", True), ("capacitance_f_per_m", float("inf")), ("extra", 1)):
            req = request(); req[field] = value; invalid.append(req)
        for values in ([0., 0.], [0., True], [-1., 1.], [0., 201e-9]):
            req = request(); req["output_times_s"] = values; invalid.append(req)
        req = request(); req["left_boundary"]["voltage_points"][0]["voltage_v"] = 1.; invalid.append(req)
        req = request(); req["right_boundary"]["voltage_points"][-1]["time_s"] = 199e-9; invalid.append(req)
        req = request(); req["left_boundary"]["resistance_ohm"] = -1.; invalid.append(req)
        for probe in ({"id": "right", "fractional_position": .5}, {"id": "bad", "fractional_position": 2.}, {"id": "", "fractional_position": .5}):
            req = request(); req["probes"][1] = probe; invalid.append(req)
        req = request(); req["probes"] *= 11; invalid.append(req)
        req = request(); req["length_m"] = 1e-8; invalid.append(req)
        req = request(); req["inductance_h_per_m"] = req["capacitance_f_per_m"] = 1e-320; invalid.append(req)
        for req in invalid:
            with self.assertRaises(line.LosslessLineTransientError): line.run_lossless_line_transient(req)
        for resource in ("_MAX_WORK", "_MAX_RESULT_BYTES"):
            with patch.object(line, resource, 1), patch.object(line, "_value", side_effect=AssertionError("preflight before waves")):
                with self.assertRaises(line.LosslessLineTransientError): line.run_lossless_line_transient(request())
        with self.assertRaisesRegex(line.LosslessLineTransientError, "fraction"):
            line._value(Fraction(1, 10**400), ([Fraction(0), Fraction(1)], [0., 1.]))
        with self.assertRaisesRegex(line.LosslessLineTransientError, "product"):
            line._product(1e-200, 1e-200)

    def test_cancellation_before_and_during_bounces_and_final_return(self):
        calls = []; line.run_lossless_line_transient(request(), cancel_check=lambda: calls.append(1) or False)
        for threshold in (1, len(calls)//2, len(calls)):
            seen = []
            def cancel(): seen.append(1); return len(seen) >= threshold
            with self.assertRaises(line.LosslessLineTransientError) as caught:
                line.run_lossless_line_transient(request(), cancel_check=cancel)
            self.assertIn("CANCELLED", caught.exception.code)


if __name__ == "__main__": unittest.main()
