# SPDX-License-Identifier: Apache-2.0
"""Independent loading oracles and fail-closed finite-population checks."""
from copy import deepcopy
import cmath
import json
import math
import unittest
from unittest.mock import patch

from python.spike_core import si_candidate_study as study


def request():
    cases = []
    for candidate, length in (("short", .02), ("long", .12)):
        for corner, resistance in (("matched", 50.), ("mismatched", 125.)):
            cases.append({"id": candidate + "_" + corner, "candidate_id": candidate, "corner_id": corner,
                "request": {"contract": "spike/si-workflow-request/v1", "run_time_domain": False,
                    "channel": {"kind": "rlgc", "coupled": False, "length_m": length,
                        "resistance_ohm_per_m": 0., "inductance_h_per_m": 250e-9,
                        "capacitance_f_per_m": 100e-12, "loss_tangent": 0.,
                        "frequency_stop_hz": 2e9, "frequency_points": 65, "reference_impedance_ohm": 50.},
                    "sources": [{"port": 0, "resistance_ohm": 50. if corner == "matched" else 100.}],
                    "receivers": [{"port": 1, "resistance_ohm": resistance, "capacitance_f": 0.}]}})
    return {"contract": study.REQUEST, "candidate_ids": ["short", "long"],
        "corner_ids": ["matched", "mismatched"], "cases": cases,
        "limits": [{"id": "floor", "metric": "min_gain", "frequency_band_hz": [0., 2e9], "bound": .40},
                   {"id": "ceiling", "metric": "max_gain", "frequency_band_hz": [0., 2e9], "bound": .75}]}


def oracle(child, frequency):
    c = child["channel"]
    rs, rl = child["sources"][0]["resistance_ohm"], child["receivers"][0]["resistance_ohm"]
    if frequency == 0:
        return complex(rl / (rs + c["resistance_ohm_per_m"]*c["length_m"] + rl))
    assert c["resistance_ohm_per_m"] == c["loss_tangent"] == 0
    z0 = math.sqrt(c["inductance_h_per_m"]/c["capacitance_f_per_m"])
    theta = 2*math.pi*frequency*math.sqrt(c["inductance_h_per_m"]*c["capacitance_f_per_m"])*c["length_m"]
    a = math.cos(theta)
    b = 1j*z0*math.sin(theta)
    cc = 1j*math.sin(theta)/z0
    return 1/(a + b/rl + rs*cc + rs*a/rl)


def receiver_trace(result):
    return next(row["trace"] for row in result["loaded_transfers"]
                if row["source_port"] == 0 and row["observed_port"] == 1)


class CandidateStudyTests(unittest.TestCase):
    def test_real_solver_against_independent_lossless_abcd(self):
        raw = request()
        original = deepcopy(raw)
        result = study.run_si_candidate_study(raw)
        self.assertEqual(raw, original)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["assessment_status"], "passed")
        self.assertEqual(result["feasible_candidate_ids"], ["short", "long"])
        for case in result["cases"]:
            supplied = next(c["request"] for c in raw["cases"] if c["id"] == case["id"])
            trace = receiver_trace(case["result"])
            self.assertEqual(len(trace), 65)
            for point in trace:
                actual = complex(point["real"], point["imag"])
                expected = oracle(supplied, point["frequency_hz"])
                self.assertLessEqual(abs(actual-expected), 2e-11 + 2e-9*abs(expected))
                if case["corner_id"] == "matched":
                    c = supplied["channel"]
                    phase = 2*math.pi*point["frequency_hz"]*math.sqrt(c["inductance_h_per_m"]*c["capacitance_f_per_m"])*c["length_m"]
                    self.assertLessEqual(abs(actual-.5*cmath.exp(-1j*phase)), 2e-11)
        self.assertFalse(result["production_qualified"])
        self.assertEqual(result["source_request"], raw)
        json.dumps(result, allow_nan=False)

    def test_lossy_dc_voltage_divider(self):
        raw = request()
        for index, case in enumerate(raw["cases"]):
            case["request"]["channel"]["resistance_ohm_per_m"] = 20*(index+1)
        result = study.run_si_candidate_study(raw)
        for case, supplied in zip(result["cases"], raw["cases"]):
            actual = receiver_trace(case["result"])[0]
            expected = oracle(supplied["request"], 0)
            self.assertLessEqual(abs(complex(actual["real"], actual["imag"])-expected), 2e-12 + 2e-10*abs(expected))

    def test_supplied_resistor_temperature_corner_matches_dc_reference(self):
        raw = request()
        for case in raw["cases"]:
            child = case["request"]
            child["temperature_c"] = 85 if case["corner_id"] == "mismatched" else 25
            child["passives"] = [{"id": "thermal_R", "port": 1, "connection": "shunt",
                "model": {"kind": "resistor", "resistance_ohm": 1000, "temperature_c": child["temperature_c"],
                          "tcr_ppm_per_c": 100, "tolerance_fraction": 0, "inductance_h": 0, "capacitance_f": 0}}]
        result = study.run_si_candidate_study(raw)
        for case, supplied in zip(result["cases"], raw["cases"]):
            child = supplied["request"]; temperature = child["temperature_c"]
            rshunt = 1000*(1+100e-6*(temperature-25))
            rl = 1/(1/child["receivers"][0]["resistance_ohm"]+1/rshunt)
            expected = rl/(child["sources"][0]["resistance_ohm"]+rl)
            point = receiver_trace(case["result"])[0]
            self.assertAlmostEqual(point["real"], expected, delta=2e-12)
            self.assertEqual(case["result"]["request"]["temperature_c"], temperature)
            self.assertEqual(case["result"]["passives"][0]["model"]["temperature_c"], temperature)

    def test_extrema_witnesses_and_case_permutation(self):
        raw = request()
        raw["limits"][0]["bound"] = .6
        result = study.run_si_candidate_study(raw)
        self.assertEqual(result["assessment_status"], "failed")
        self.assertEqual(result["feasible_candidate_ids"], [])
        for candidate in result["candidates"]:
            for limit in candidate["limits"]:
                # Independently enumerate all raw child samples, without helper use.
                samples = []
                for case in result["cases"]:
                    if case["candidate_id"] == candidate["candidate_id"]:
                        for point in receiver_trace(case["result"]):
                            samples.append((math.hypot(point["real"], point["imag"]), point["frequency_hz"], case["id"]))
                expected = min(samples) if limit["metric"] == "min_gain" else min(samples, key=lambda v: (-v[0], v[1], v[2]))
                witness = limit["worst"]
                self.assertEqual((witness["gain"], witness["frequency_hz"], witness["case_id"]), expected)
        raw["cases"].reverse()
        reordered = study.run_si_candidate_study(raw)
        self.assertEqual(reordered["candidates"], result["candidates"])
        self.assertNotEqual(reordered["input_digest"], result["input_digest"])

    def test_equal_bound_is_inclusive(self):
        raw = request()
        raw["candidate_ids"] = ["short"]
        raw["cases"] = raw["cases"][:2]
        observed = study.run_si_candidate_study(raw)
        # Exact equality uses the binary64 witness, without rounding the bound.
        bound = observed["candidates"][0]["limits"][0]["minimum"]["gain"]
        raw["limits"] = [{"id": "equal", "metric": "min_gain", "frequency_band_hz": [0, 2e9], "bound": bound}]
        result = study.run_si_candidate_study(raw)
        self.assertEqual(result["assessment_status"], "passed")
        self.assertEqual(result["candidates"][0]["limits"][0]["margin"], 0)

    def test_real_child_failure_is_retained_and_cannot_pass(self):
        raw = request()
        raw["cases"][1]["request"]["sources"][0]["resistance_ohm"] = -1
        result = study.run_si_candidate_study(raw)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["assessment_status"], "incomplete")
        self.assertEqual(result["cases"][1]["status"], "failed")
        self.assertTrue(result["cases"][1]["issue"]["message"])
        self.assertEqual(result["candidates"][0]["status"], "incomplete")
        self.assertEqual(result["candidates"][1]["status"], "passed")
        self.assertEqual(result["feasible_candidate_ids"], ["long"])
        self.assertEqual(result["candidates"][0]["limits"][0]["evaluated_case_ids"], ["short_matched"])

    def test_preflight_rejects_missing_duplicate_and_unknown_cells(self):
        for change in (lambda r: r["cases"].pop(),
                       lambda r: r["cases"].__setitem__(1, deepcopy(r["cases"][0])),
                       lambda r: r["cases"][0].__setitem__("corner_id", "unknown")):
            raw = request(); change(raw)
            with patch.object(study, "run_si_workflow") as child:
                with self.assertRaises(study.SiCandidateStudyError):
                    study.run_si_candidate_study(raw)
                child.assert_not_called()

    def test_preflight_rejects_unsupported_scope_and_bad_grid(self):
        for path, value in ((["run_time_domain"], True), (["channel", "coupled"], True),
                (["channel", "frequency_points"], 1025), (["channel", "frequency_points"], True),
                (["channel", "frequency_points"], 3.5), (["channel", "frequency_stop_hz"], float("nan")),
                (["channel", "loss_tangent"], float("inf")), (["channel", "length_m"], True),
                (["edits"], [{"kind": "delay"}])):
            raw = request(); target = raw["cases"][0]["request"]
            for name in path[:-1]: target = target[name]
            target[path[-1]] = value
            with self.subTest(path=path, value=value), patch.object(study, "run_si_workflow") as child:
                with self.assertRaises(study.SiCandidateStudyError): study.run_si_candidate_study(raw)
                child.assert_not_called()

    def test_band_validation_and_common_grid(self):
        for band in ((1, 2), (-1, 0), (0, 3e9), (10, 0), (False, 0)):
            raw = request(); raw["limits"][0]["frequency_band_hz"] = list(band)
            with self.subTest(band=band), self.assertRaises(study.SiCandidateStudyError): study.run_si_candidate_study(raw)
        raw = request(); raw["cases"][0]["request"]["channel"]["frequency_points"] = 33
        with self.assertRaises(study.SiCandidateStudyError): study.run_si_candidate_study(raw)

    def test_cancellation_before_work(self):
        with patch.object(study, "run_si_workflow") as child:
            with self.assertRaises(study.SiCandidateStudyError) as caught:
                study.run_si_candidate_study(request(), poll=lambda: True)
            self.assertEqual(caught.exception.code, "SI_CANDIDATE_STUDY_CANCELLED")
            child.assert_not_called()

    def test_maximum_trace_preserves_every_sample(self):
        raw = request()
        raw["candidate_ids"] = ["short"]; raw["corner_ids"] = ["matched"]
        raw["cases"] = raw["cases"][:1]
        raw["cases"][0]["request"]["channel"]["frequency_points"] = 1024
        result = study.run_si_candidate_study(raw)
        self.assertEqual(len(receiver_trace(result["cases"][0]["result"])), 1024)
        self.assertEqual([p["frequency_hz"] for p in receiver_trace(result["cases"][0]["result"])], result["frequencies_hz"])

    def test_cancellation_after_child_does_not_return_passing_partial(self):
        decisions = iter([False, False, True])
        with patch.object(study, "run_si_workflow", wraps=study.run_si_workflow) as child:
            with self.assertRaises(study.SiCandidateStudyError) as caught:
                study.run_si_candidate_study(request(), poll=lambda: next(decisions))
            self.assertEqual(caught.exception.code, "SI_CANDIDATE_STUDY_CANCELLED")
            self.assertEqual(child.call_count, 1)

    def test_resource_caps_before_solving(self):
        for change in (lambda r: r.__setitem__("candidate_ids", ["c"+str(i) for i in range(9)]),
                       lambda r: r.__setitem__("limits", r["limits"]*9),
                       lambda r: r["cases"][0]["request"].__setitem__("oversized", "x"*(2*1024*1024))):
            raw = request(); change(raw)
            with patch.object(study, "run_si_workflow") as child:
                with self.assertRaises(study.SiCandidateStudyError): study.run_si_candidate_study(raw)
                child.assert_not_called()

    def test_nonfinite_child_cannot_yield_feasible_candidate(self):
        fake = study.run_si_workflow(request()["cases"][0]["request"])
        receiver_trace(fake)[0]["real"] = float("nan")
        with patch.object(study, "run_si_workflow", return_value=fake):
            result = study.run_si_candidate_study(request())
        self.assertEqual(result["assessment_status"], "incomplete")
        self.assertEqual(result["feasible_candidate_ids"], [])
        self.assertTrue(all(row["status"] == "failed" and row["result"] is None for row in result["cases"]))
        json.dumps(result, allow_nan=False)

    def test_forged_child_provenance_cannot_pass(self):
        for mutate in (lambda r: r.__setitem__("contract", "wrong"),
                       lambda r: r.__setitem__("request_sha256", "0"*64),
                       lambda r: r["request"]["channel"].__setitem__("length_m", .99)):
            fake = study.run_si_workflow(request()["cases"][0]["request"])
            mutate(fake)
            with patch.object(study, "run_si_workflow", return_value=fake):
                result = study.run_si_candidate_study(request())
            self.assertEqual(result["feasible_candidate_ids"], [])
            self.assertTrue(all(row["status"] == "failed" for row in result["cases"]))

    def test_aggregate_budget_stops_before_remaining_children(self):
        raw = request(); initial = study.run_si_candidate_study(raw)
        size = lambda v: len(json.dumps(v, ensure_ascii=False, separators=(",", ":")).encode())
        budget = size(raw)+size(initial["frequencies_hz"])+size(initial["cases"][0])+64
        with patch.object(study, "_MAX_RESULT_BYTES", budget), patch.object(study, "run_si_workflow", wraps=study.run_si_workflow) as child:
            with self.assertRaises(study.SiCandidateStudyError) as caught:
                study.run_si_candidate_study(raw)
            self.assertEqual(caught.exception.code, "SI_CANDIDATE_STUDY_RESOURCE_LIMIT")
            self.assertLess(child.call_count, len(raw["cases"]))

    def test_partial_or_incomplete_child_trace_cannot_pass(self):
        real = study.run_si_workflow(request()["cases"][0]["request"])
        for mutate in (lambda r: r.__setitem__("status", "partial"),
                       lambda r: receiver_trace(r).pop()):
            fake = deepcopy(real); mutate(fake)
            with patch.object(study, "run_si_workflow", return_value=fake):
                result = study.run_si_candidate_study(request())
            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["feasible_candidate_ids"], [])


if __name__ == "__main__":
    unittest.main()
