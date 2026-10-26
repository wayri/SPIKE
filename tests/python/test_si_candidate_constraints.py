# SPDX-License-Identifier: Apache-2.0
"""Independent synthetic contracts for the SI01-S02 reviewed export."""
from __future__ import annotations

from copy import deepcopy
import math
import unittest

from python.spike_core.solvers.signal_integrity.networks import si_candidate_constraints as export


def fixture():
    request = {"contract": "spike/si-candidate-study-request/v1", "candidate_ids": ["kept", "other"],
        "corner_ids": ["cold", "hot"], "cases": [],
        "limits": [{"id": "floor", "metric": "min_gain", "frequency_band_hz": [0.0, 2.0], "bound": 0.4}]}
    cases = []
    values = {"kept_cold": [0.5, 0.6], "kept_hot": [0.45, 0.7],
              "other_cold": [0.3, 0.6], "other_hot": [0.2, 0.7]}
    for candidate in ("kept", "other"):
        for corner in ("cold", "hot"):
            identity = f"{candidate}_{corner}"
            child_request = {"contract": "spike/si-workflow-request/v1", "id": identity}
            request["cases"].append({"id": identity, "candidate_id": candidate,
                                     "corner_id": corner, "request": child_request})
            trace = [{"frequency_hz": float(index * 2), "real": value, "imag": 0.0}
                     for index, value in enumerate(values[identity])]
            child = {"loaded_transfers": [{"source_port": 0, "observed_port": 1, "trace": trace}]}
            cases.append({"id": identity, "candidate_id": candidate, "corner_id": corner,
                          "request_digest": export.canonical_sha256(child_request), "result": child,
                          "issue": None, "status": "completed"})

    def assessment(candidate):
        selected = [case for case in cases if case["candidate_id"] == candidate]
        points = [{"case_id": case["id"], "corner_id": case["corner_id"], **point,
                   "gain": math.hypot(point["real"], point["imag"])}
                  for case in selected for point in case["result"]["loaded_transfers"][0]["trace"]]
        minimum = min(points, key=lambda p: (p["gain"], p["frequency_hz"], p["case_id"]))
        maximum = min(points, key=lambda p: (-p["gain"], p["frequency_hz"], p["case_id"]))
        margin = minimum["gain"] - 0.4
        status = "passed" if margin >= 0 else "failed"
        report = {**request["limits"][0], "status": status, "coverage_complete": True,
                  "minimum": minimum, "maximum": maximum, "worst": minimum, "margin": margin,
                  "evaluated_case_ids": [case["id"] for case in selected]}
        return {"candidate_id": candidate, "status": status,
                "case_ids": [case["id"] for case in selected], "limits": [report]}
    result = {"contract": export.SOURCE, "status": "completed", "model_status": "experimental",
              "production_qualified": False, "assessment_status": "failed", "source_request": request,
              "input_digest": export.canonical_sha256(request), "cases": cases,
              "candidates": [assessment("kept"), assessment("other")],
              "limitations": ["Synthetic finite sampled fixture."]}
    return result


def selection(result, candidate="kept", decision="accept_sampled"):
    return {"contract": export.SELECTION, "expected_source_result_sha256": export.canonical_sha256(result),
            "candidate_id": candidate, "decision": decision, "reviewer_id": "reviewer_1",
            "review_basis": "Reviewed the finite supplied cases and original floor.",
            "constraint_ids": ["floor"]}


class CandidateConstraintExportTests(unittest.TestCase):
    def test_accepted_export_preserves_original_limit_and_scope(self):
        source = fixture(); original = deepcopy(source)
        result = export.export_candidate_constraints(source, selection(source))
        self.assertEqual(source, original)
        self.assertTrue(result["applicable"])
        self.assertEqual(result["constraints"][0]["bound"], 0.4)
        self.assertEqual(result["constraints"][0]["worst"]["case_id"], "kept_hot")
        self.assertEqual(result["source_result_sha256"], export.canonical_sha256(source))
        for flag in ("native_layout_applied", "continuous_band_qualified", "physical_qualified",
                     "production_qualified", "family_complete"):
            self.assertFalse(result[flag])
        self.assertEqual([row["status"] for row in result["candidate_statuses"]], ["passed", "failed"])

    def test_hold_and_reject_retain_failed_evidence_without_application(self):
        for decision in ("hold", "reject"):
            source = fixture()
            result = export.export_candidate_constraints(source, selection(source, "other", decision))
            self.assertFalse(result["applicable"])
            self.assertEqual(result["constraints"][0]["status"], "failed")
            self.assertEqual(result["decision"], decision)

    def test_failed_candidate_cannot_be_accepted(self):
        source = fixture()
        with self.assertRaisesRegex(export.SiCandidateConstraintError, "complete passing"):
            export.export_candidate_constraints(source, selection(source, "other"))

    def test_digest_review_and_constraint_selection_fail_closed(self):
        changes = (
            lambda source, pick: pick.__setitem__("expected_source_result_sha256", "0" * 64),
            lambda source, pick: pick.__setitem__("decision", "approved"),
            lambda source, pick: pick.__setitem__("review_basis", ""),
            lambda source, pick: pick.__setitem__("constraint_ids", ["missing"]),
            lambda source, pick: pick.__setitem__("constraint_ids", ["floor", "floor"]),
        )
        for change in changes:
            source = fixture(); pick = selection(source); change(source, pick)
            with self.subTest(pick=pick), self.assertRaises(export.SiCandidateConstraintError):
                export.export_candidate_constraints(source, pick)

    def test_forged_status_coverage_and_witness_fail_closed(self):
        mutations = (
            lambda result: result["candidates"][0].__setitem__("status", "failed"),
            lambda result: result["candidates"][0]["limits"][0].__setitem__("status", "failed"),
            lambda result: result["candidates"][0]["limits"][0].__setitem__("coverage_complete", False),
            lambda result: result["candidates"][0]["limits"][0]["worst"].__setitem__("gain", 0.9),
            lambda result: result["candidates"][0]["limits"][0].__setitem__("bound", 0.45),
            lambda result: result["cases"][0].__setitem__("request_digest", "0" * 64),
        )
        for mutate in mutations:
            source = fixture(); mutate(source); pick = selection(source)
            with self.subTest(mutate=mutate), self.assertRaises(export.SiCandidateConstraintError):
                export.export_candidate_constraints(source, pick)

    def test_nonfinite_trace_and_incomplete_case_fail_accepted_export(self):
        source = fixture(); source["cases"][0]["result"]["loaded_transfers"][0]["trace"][0]["real"] = math.nan
        # Hashing itself is fail closed before any review can bind the result.
        with self.assertRaises(export.SiCandidateConstraintError):
            export.canonical_sha256(source)
        source = fixture(); source["cases"][0]["status"] = "failed"; source["cases"][0]["issue"] = {"code": "X"}
        pick = selection(source)
        with self.assertRaises(export.SiCandidateConstraintError):
            export.export_candidate_constraints(source, pick)


if __name__ == "__main__":
    unittest.main()
