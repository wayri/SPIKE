# SPDX-License-Identifier: Apache-2.0
import json
import math
import unittest

from python.spike_core.contracts import DesignIR
from python.spike_core.spikes_layout_adapter import (
    SpikesLayoutAdapterError,
    canonical_layout_json,
    map_layout_results,
    prepare_native_jobs,
    validate_layout_request,
)


class SpikesLayoutAdapterTests(unittest.TestCase):
    def setUp(self):
        self.design = DesignIR(design_id="board-1")
        self.request = {
            "contract": "spike/layout-evaluation/v1",
            "record_type": "request",
            "evaluation_id": "route.iteration-1",
            "consumer": {"kind": "autorouter", "implementation": "custom-router", "version": "1"},
            "candidate": {"path": "candidate/design-ir.json", "sha256": "a" * 64, "bytes": 4096, "contract": "spike/design-ir/v2"},
            "requirements": [
                {
                    "id": "max.temperature",
                    "evaluator": "native_solver",
                    "kind": "hard_constraint",
                    "metric_id": "thermal.max_temperature",
                    "result_key": "max_temperature_k",
                    "relation": "le",
                    "dimension": [0, 0, 0, 0, 1, 0, 0],
                    "upper_si": 358.15,
                    "scope": {"frame": "board", "entity_ids": ["track-1"]},
                },
                {
                    "id": "minimum.clearance",
                    "evaluator": "cad_drc",
                    "kind": "hard_constraint",
                    "metric_id": "pcb.minimum_clearance",
                    "relation": "ge",
                    "dimension": [1, 0, 0, 0, 0, 0, 0],
                    "lower_si": 0.0002,
                    "scope": {"frame": "board", "entity_ids": []},
                },
                {
                    "id": "minimize.loss",
                    "evaluator": "native_solver",
                    "kind": "objective",
                    "metric_id": "pi.total_loss",
                    "result_key": "total_loss_w",
                    "relation": "minimize",
                    "dimension": [2, 1, -3, 0, 0, 0, 0],
                    "weight": 1.0,
                    "normalization_si": 2.0,
                    "scope": {"frame": "board", "entity_ids": []},
                },
            ],
            "physics_evaluations": [
                {
                    "id": "field.solve-1",
                    "requirement_ids": ["max.temperature", "minimize.loss"],
                    "model": {"path": "models/candidate-1.json", "sha256": "b" * 64, "bytes": 1024, "contract": "spike/physics-model/v1"},
                    "study": {"type": "stationary"},
                    "requested_outputs": ["summary", "issues"],
                }
            ],
            "resources": {"max_memory_bytes": 536870912, "max_wall_time_s": 600, "ranks": 1, "threads": 1},
            "deterministic": True,
        }

    def test_request_is_strict_and_canonical(self):
        normalized = validate_layout_request(self.request)
        canonical = canonical_layout_json(self.request)
        self.assertEqual(json.loads(canonical), normalized)
        self.assertNotIn(" ", canonical)
        bad = {**self.request, "shell": "anything"}
        with self.assertRaisesRegex(SpikesLayoutAdapterError, "unknown or missing") as caught:
            validate_layout_request(bad)
        self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-CONTRACT-0001")

    def test_native_jobs_are_deterministic_and_do_not_leak_layout_context(self):
        first = prepare_native_jobs(self.request, self.design)
        second = prepare_native_jobs(self.request, self.design)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["candidate_sha256"], "a" * 64)
        self.assertEqual(first[0]["job"]["contract"], "spike/solver-job/v1")
        self.assertEqual(first[0]["job"]["request_id"], first[0]["request_id"])
        self.assertNotIn("candidate", first[0]["job"])
        self.assertNotIn("consumer", first[0]["job"])

    def test_bad_artifacts_dimensions_and_bindings_fail_closed(self):
        bad_path = json.loads(json.dumps(self.request))
        bad_path["candidate"]["path"] = "../board.json"
        with self.assertRaises(SpikesLayoutAdapterError):
            validate_layout_request(bad_path)
        bad_dimension = json.loads(json.dumps(self.request))
        bad_dimension["requirements"][0]["dimension"] = [0] * 6
        with self.assertRaises(SpikesLayoutAdapterError):
            validate_layout_request(bad_dimension)
        bad_binding = json.loads(json.dumps(self.request))
        bad_binding["physics_evaluations"][0]["requirement_ids"] = ["minimum.clearance"]
        with self.assertRaises(SpikesLayoutAdapterError):
            validate_layout_request(bad_binding)
        bad_number = json.loads(json.dumps(self.request))
        bad_number["requirements"][0]["upper_si"] = math.inf
        with self.assertRaises(SpikesLayoutAdapterError):
            validate_layout_request(bad_number)

    def test_result_correlation_and_fail_closed_hard_requirements(self):
        job = prepare_native_jobs(self.request, self.design)[0]
        native = {
            job["request_id"]: {
                "contract": "spike/result-bundle/v2",
                "request_id": job["request_id"],
                "status": "completed",
                "validation_state": "verification_only",
                "summary": {"max_temperature_k": 350.0, "total_loss_w": 2.5},
            }
        }
        incomplete = map_layout_results(self.request, native)
        self.assertFalse(incomplete["feasible"])
        self.assertEqual(incomplete["status"], "partial")
        mapped = map_layout_results(
            self.request,
            native,
            external_results={
                "minimum.clearance": {"status": "satisfied", "value_si": 0.00025, "validation_state": "cad_drc"}
            },
        )
        self.assertTrue(mapped["feasible"])
        self.assertEqual(mapped["status"], "completed")
        self.assertEqual(mapped["candidate_sha256"], "a" * 64)
        self.assertEqual(mapped["objective_score_state"], "available")
        self.assertAlmostEqual(mapped["objective_score"], 1.25)
        self.assertTrue(mapped["objective_score_lower_is_better"])
        self.assertEqual(mapped["objective_terms"], [
            {"requirement_id": "minimize.loss", "dimensionless_term": 1.25}
        ])
        wrong = json.loads(json.dumps(native))
        wrong[job["request_id"]]["request_id"] = "wrong.result"
        with self.assertRaises(SpikesLayoutAdapterError) as caught:
            map_layout_results(self.request, wrong)
        self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-RESULT-0002")
        with self.assertRaises(SpikesLayoutAdapterError):
            map_layout_results(self.request, {"layout.unknown": native[job["request_id"]]})

    def test_constraint_margin_and_violation_are_computed(self):
        job = prepare_native_jobs(self.request, self.design)[0]
        native = {
            job["request_id"]: {
                "contract": "spike/result-bundle/v2", "request_id": job["request_id"],
                "status": "completed", "validation_state": "qualified",
                "summary": {"max_temperature_k": 400.0, "total_loss_w": 3.0},
            }
        }
        mapped = map_layout_results(
            self.request,
            native,
            external_results={
                "minimum.clearance": {"status": "satisfied", "value_si": 0.0003, "validation_state": "cad_drc"}
            },
        )
        thermal = next(item for item in mapped["requirements"] if item["requirement_id"] == "max.temperature")
        self.assertEqual(thermal["status"], "violated")
        self.assertAlmostEqual(thermal["margin_si"], -41.85)
        self.assertFalse(mapped["feasible"])

    def test_unvalidated_hard_result_cannot_make_candidate_feasible(self):
        job = prepare_native_jobs(self.request, self.design)[0]
        native = {
            job["request_id"]: {
                "contract": "spike/result-bundle/v2", "request_id": job["request_id"],
                "status": "completed", "validation_state": "unvalidated",
                "summary": {"max_temperature_k": 350.0, "total_loss_w": 2.0},
            }
        }
        external = {
            "minimum.clearance": {"status": "satisfied", "value_si": 0.0003, "validation_state": "cad_drc"}
        }
        mapped = map_layout_results(self.request, native, external_results=external)
        self.assertEqual(mapped["requirements"][0]["status"], "satisfied")
        self.assertFalse(mapped["feasible"])
        native[job["request_id"]]["status"] = "mystery"
        with self.assertRaises(SpikesLayoutAdapterError) as caught:
            map_layout_results(self.request, native, external_results=external)
        self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-RESULT-0003")

    def test_objective_score_requires_explicit_positive_si_normalization(self):
        missing = json.loads(json.dumps(self.request))
        del missing["requirements"][2]["normalization_si"]
        job = prepare_native_jobs(missing, self.design)[0]
        native = {
            job["request_id"]: {
                "contract": "spike/result-bundle/v2", "request_id": job["request_id"],
                "status": "completed", "validation_state": "qualified",
                "summary": {"max_temperature_k": 350.0, "total_loss_w": 2.0},
            }
        }
        mapped = map_layout_results(missing, native)
        self.assertEqual(mapped["objective_score_state"], "normalization_or_result_missing")
        self.assertNotIn("objective_score", mapped)

        invalid = json.loads(json.dumps(self.request))
        invalid["requirements"][2]["normalization_si"] = 0.0
        with self.assertRaises(SpikesLayoutAdapterError):
            validate_layout_request(invalid)

        non_objective = json.loads(json.dumps(self.request))
        non_objective["requirements"][0]["normalization_si"] = 1.0
        with self.assertRaises(SpikesLayoutAdapterError):
            validate_layout_request(non_objective)


if __name__ == "__main__":
    unittest.main()
