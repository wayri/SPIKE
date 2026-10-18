# SPDX-License-Identifier: Apache-2.0
"""Independent shifted-PWL and finite physical-pattern oracles.

Preset voltage tolerance: 2e-10 V absolute + 1e-9 relative.
"""
from copy import deepcopy
from itertools import product
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core import sparameter_crosstalk_timing as timing
from tests.python.test_sparameter_multi_aggressor import request as source_request, physical, signed_request


def request(reference=50., scale=1., memory=True):
    source, g, initial, network_l = source_request(reference, scale, memory)
    req = {"contract": timing.REQUEST_CONTRACT, "crosstalk_request": source,
           "timing_corners": [{"id": "nominal", "delay_s_by_port": {"b": 0., "a": 0.}},
                              {"id": "a-late", "delay_s_by_port": {"b": 0., "a": .12*scale}},
                              {"id": "b-early", "delay_s_by_port": {"b": -.17*scale, "a": 0.}}]}
    return req, g, initial, network_l


def shifted_source(source, delays):
    """Independent knot construction and numpy scalar PWL interpolation."""
    shifted = deepcopy(source)
    for term in shifted["transient_request"]["terminations"]:
        if term["port_name"] not in delays: continue
        delay = delays[term["port_name"]]
        if delay == 0: continue
        old = term["voltage_points"]
        times = [p["time_s"] for p in old]; values = [p["voltage_v"] for p in old]
        grid = [0.]+[t+delay for t in times if 0 < t+delay < times[-1]]+[times[-1]]
        term["voltage_points"] = [{"time_s": t, "voltage_v": float(np.interp(t-delay, times, values))} for t in grid]
    return shifted


class CrosstalkTimingTests(unittest.TestCase):
    def assertVoltage(self, actual, expected):
        np.testing.assert_allclose(actual, expected, atol=2e-10, rtol=1e-9)

    def test_exact_shift_knots_endpoint_hold_clipping_and_zero_identity(self):
        points = [{"time_s": t, "voltage_v": v} for t, v in ((0, 1), (.2, 3), (.6, -1), (1, 2))]
        self.assertEqual(timing.sampling._json(timing._shift_points(points, 0., 1.)), timing.sampling._json(points))
        late = timing._shift_points(points, .1, 1.)
        self.assertEqual([p["time_s"] for p in late], [0., .1, .2+.1, .6+.1, 1])
        self.assertVoltage([p["voltage_v"] for p in late], [1., 1., 3., -1., 1.25])
        early = timing._shift_points(points, -.3, 1.)
        self.assertEqual([p["time_s"] for p in early], [0., .6-.3, 1.-.3, 1])
        self.assertVoltage([p["voltage_v"] for p in early], [2., -1., 2., 2.])
        for delay in (1., 1e308, -1., -1e308, .1, -.3, .2, -.6):
            shifted = timing._shift_points(points, delay, 1.)
            query = np.linspace(0., 1., 101)
            actual = np.interp(query, [p["time_s"] for p in shifted], [p["voltage_v"] for p in shifted])
            expected = np.interp(query-delay, [p["time_s"] for p in points], [p["voltage_v"] for p in points])
            self.assertVoltage(actual, expected)

    def test_all_finite_corners_and_polarities_independent_physics_with_memory(self):
        req, g, initial, network_l = request(); before = deepcopy(req)
        actual_fit = timing.multi.rlc.rational.fit_sparameter_rational
        with patch.object(timing.multi.rlc.rational, "fit_sparameter_rational", wraps=actual_fit) as fitted:
            out = timing.run_crosstalk_timing_corners(req)
            self.assertEqual(fitted.call_count, 15)
        self.assertEqual(req, before)
        self.assertEqual(out["source_crosstalk_request"], req["crosstalk_request"])
        self.assertEqual(out["corners"][0]["result"]["input_digest"], timing.sampling._digest(req["crosstalk_request"]))
        families = []
        for corner, record in zip(req["timing_corners"], out["corners"]):
            expected_source = shifted_source(req["crosstalk_request"], corner["delay_s_by_port"])
            actual_source = record["result"]["source_request"]
            self.assertEqual(list(record["delay_s_by_port"]), ["a", "b"])
            self.assertEqual(actual_source["initial_state"], req["crosstalk_request"]["transient_request"]["initial_state"])
            original_terms = {t["port_name"]: t for t in req["crosstalk_request"]["transient_request"]["terminations"]}
            for term in actual_source["terminations"]:
                if term["port_name"] not in ("a", "b"):
                    self.assertEqual(term, original_terms[term["port_name"]])
            trajectories = [physical(signed_request(expected_source, dict(zip(("a", "b"), signs))), g, initial, network_l)
                            for signs in product((-1, 1), repeat=2)]
            families.extend(trajectories)
            self.assertVoltage([e["minimum_voltage_v"] for e in record["result"]["envelope"]], np.min(trajectories, axis=0))
            self.assertVoltage([e["maximum_voltage_v"] for e in record["result"]["envelope"]], np.max(trajectories, axis=0))
            self.assertVoltage([e["baseline_voltage_v"] for e in record["result"]["envelope"]][0], initial[0])
        self.assertVoltage([e["minimum_voltage_v"] for e in out["envelope"]], np.min(families, axis=0))
        self.assertVoltage([e["maximum_voltage_v"] for e in out["envelope"]], np.max(families, axis=0))
        for name in ("worst_upper_pattern", "worst_lower_pattern"):
            witness = out[name]; chosen = next(c for c in out["corners"] if c["id"] == witness["corner_id"])
            self.assertEqual({k: v for k, v in witness.items() if k != "corner_id"}, chosen["result"][name])
            corner = next(c for c in req["timing_corners"] if c["id"] == witness["corner_id"])
            expected_source = shifted_source(req["crosstalk_request"], corner["delay_s_by_port"])
            self.assertVoltage(witness["verified_victim_voltage_v"], physical(signed_request(expected_source, witness["polarity_by_port"]), g, initial, network_l))
        self.assertEqual(out["diagnostics"]["solution_count"], 15)
        self.assertEqual(out["diagnostics"]["estimated_work"], sum(c["result"]["diagnostics"]["estimated_work"] for c in out["corners"]))

    def test_observation_refinement_and_finite_corner_enlargement(self):
        req = request()[0]; nominal = deepcopy(req); nominal["timing_corners"] = nominal["timing_corners"][:1]
        base = timing.run_crosstalk_timing_corners(nominal)
        extended = timing.run_crosstalk_timing_corners(req)
        self.assertTrue(all(a["minimum_voltage_v"] <= b["minimum_voltage_v"]+2e-10 for a, b in zip(extended["envelope"], base["envelope"])))
        self.assertTrue(all(a["maximum_voltage_v"] >= b["maximum_voltage_v"]-2e-10 for a, b in zip(extended["envelope"], base["envelope"])))
        refined = deepcopy(req)
        times = refined["crosstalk_request"]["transient_request"]["output_times_s"]
        refined["crosstalk_request"]["transient_request"]["output_times_s"] = sorted(set(times+[.07, .31, .47, .63, .93]))
        fine = timing.run_crosstalk_timing_corners(refined)
        shared = {item["time_s"]: item for item in fine["envelope"]}
        for field in ("minimum_voltage_v", "maximum_voltage_v", "lower_margin_v", "upper_margin_v"):
            self.assertVoltage([shared[e["time_s"]][field] for e in extended["envelope"]], [e[field] for e in extended["envelope"]])
        self.assertGreaterEqual(fine["worst_upper_pattern"]["victim_voltage_v"]+2e-10, extended["worst_upper_pattern"]["victim_voltage_v"])
        self.assertLessEqual(fine["worst_lower_pattern"]["victim_voltage_v"]-2e-10, extended["worst_lower_pattern"]["victim_voltage_v"])

    def test_declared_corner_ties_reference_and_physical_time_units(self):
        req = request()[0]; req["timing_corners"] = [deepcopy(req["timing_corners"][0]) for _ in range(2)]
        req["timing_corners"][0]["id"] = "z-first"; req["timing_corners"][1]["id"] = "a-second"
        tied = timing.run_crosstalk_timing_corners(req)
        self.assertTrue(all(e["minimum_corner_id"] == e["maximum_corner_id"] == "z-first" for e in tied["envelope"]))
        self.assertEqual(tied["worst_upper_pattern"]["corner_id"], "z-first")
        self.assertEqual(tied["worst_lower_pattern"]["corner_id"], "z-first")
        base = timing.run_crosstalk_timing_corners(request()[0])
        for reference, scale in ((1., 1.), (25., .001), (1000., .001)):
            out = timing.run_crosstalk_timing_corners(request(reference, scale)[0])
            for field in ("minimum_voltage_v", "maximum_voltage_v", "lower_margin_v", "upper_margin_v"):
                self.assertVoltage([e[field] for e in out["envelope"]], [e[field] for e in base["envelope"]])
            for name in ("worst_upper_pattern", "worst_lower_pattern"):
                self.assertEqual(out[name]["corner_id"], base[name]["corner_id"])
                self.assertEqual(out[name]["polarity_by_port"], base[name]["polarity_by_port"])
                self.assertAlmostEqual(out[name]["sample_time_s"], scale*base[name]["sample_time_s"])

    def test_invalid_maps_precision_and_aggregate_preflight_before_any_fit(self):
        req = request()[0]; invalid = []
        for delays in ({"a": 0.}, {"a": 0., "b": 0., "victim": 0.}, {"a": True, "b": 0.},
                       {"a": float("inf"), "b": 0.}, {"a": 5e-324, "b": 0.}):
            candidate = deepcopy(req); candidate["timing_corners"][-1]["delay_s_by_port"] = delays; invalid.append(candidate)
        for identifier in ("", " ", "x"*129, "nominal", True):
            candidate = deepcopy(req); candidate["timing_corners"][-1]["id"] = identifier; invalid.append(candidate)
        for corners in ([], req["timing_corners"]*3):
            candidate = deepcopy(req); candidate["timing_corners"] = corners; invalid.append(candidate)
        candidate = deepcopy(req); candidate["extra"] = 1; invalid.append(candidate)
        candidate = deepcopy(req); candidate["crosstalk_request"]["aggressors"][1]["port_name"] = "victim"; invalid.append(candidate)
        for candidate in invalid:
            with patch.object(timing.multi.rlc.rational, "fit_sparameter_rational", side_effect=AssertionError("all corners must preflight")):
                with self.assertRaises(timing.SParameterCrosstalkTimingError): timing.run_crosstalk_timing_corners(candidate)
        frozen, _ = timing.multi.rlc.prescribed._snapshot(req)
        _, _, work, _, estimate = timing._preflight(frozen["crosstalk_request"], lambda: None)
        for name, limit in (("_MAX_WORK", int(1.5*work)), ("_MAX_RESULT_BYTES", 2*estimate+1000000)):
            with patch.object(timing, name, limit), patch.object(timing.multi.rlc.rational, "fit_sparameter_rational", side_effect=AssertionError("aggregate preflight before fit")):
                with self.assertRaises(timing.SParameterCrosstalkTimingError) as caught: timing.run_crosstalk_timing_corners(req)
                self.assertIn("RESOURCE_LIMIT", caught.exception.code)
        points = [{"time_s": t, "voltage_v": v} for t, v in ((0., 0.), (1e-18, 1.), (1., 0.))]
        with self.assertRaisesRegex(timing.SParameterCrosstalkTimingError, "collides"):
            timing._shift_points(points, .5, 1.)

    def test_cancellation_before_between_corners_and_after_final_output(self):
        req = request()[0]; calls = []
        timing.run_crosstalk_timing_corners(req, cancel_check=lambda: calls.append(1) or False)
        for threshold in (1, len(calls)//2, len(calls)):
            seen = []
            def cancel(): seen.append(1); return len(seen) >= threshold
            with self.assertRaises(timing.SParameterCrosstalkTimingError) as caught:
                timing.run_crosstalk_timing_corners(req, cancel_check=cancel)
            self.assertIn("CANCELLED", caught.exception.code)


if __name__ == "__main__": unittest.main()
