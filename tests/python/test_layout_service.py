# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import unittest

from python.spike_core import LAYOUT_EVALUATION_CONTRACT
from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.spikes_layout_adapter import design_ir_artifact_identity
from python.spike_core.service import handle


class LayoutServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidate = DesignIRV2.from_v1(
            DesignIR(design_id="board-1"), source_digest="c" * 64,
        ).to_dict()
        candidate_identity = design_ir_artifact_identity(self.candidate)
        self.request = {
            "contract": LAYOUT_EVALUATION_CONTRACT,
            "record_type": "request",
            "evaluation_id": "route.iteration-1",
            "consumer": {
                "kind": "autorouter",
                "implementation": "custom-router",
                "version": "1",
            },
            "candidate": {
                "path": "candidates/route-1.json",
                "sha256": candidate_identity["sha256"],
                "bytes": candidate_identity["bytes"],
                "contract": "spike/design-ir/v2",
            },
            "requirements": [
                {
                    "id": "maximum.loss",
                    "evaluator": "native_solver",
                    "kind": "hard_constraint",
                    "metric_id": "pi.total_loss",
                    "result_key": "total_loss_w",
                    "relation": "le",
                    "dimension": [2, 1, -3, 0, 0, 0, 0],
                    "upper_si": 5.0,
                    "scope": {"frame": "board", "entity_ids": []},
                }
            ],
            "physics_evaluations": [
                {
                    "id": "loss.solve-1",
                    "requirement_ids": ["maximum.loss"],
                    "model": {
                        "path": "models/route-1.json",
                        "sha256": "b" * 64,
                        "bytes": 1024,
                        "contract": "spike/physics-model/v1",
                    },
                    "study": {"type": "stationary"},
                    "requested_outputs": ["summary", "issues"],
                }
            ],
            "resources": {
                "max_memory_bytes": 536870912,
                "max_wall_time_s": 600,
                "ranks": 1,
                "threads": 1,
            },
            "deterministic": True,
        }
        self.registry = {
            "contract": "spike/layout-metric-registry/v1",
            "registry_id": "test.layout-metrics",
            "registry_version": "1.0.0",
            "producer": {"implementation": "test-evaluator", "version": "1"},
            "metrics": [{
                "id": "pi.total_loss",
                "dimension": [2, 1, -3, 0, 0, 0, 0],
                "evaluator": "native_solver",
                "result_key": "total_loss_w",
                "supported_consumers": ["autorouter"],
                "supported_kinds": ["hard_constraint"],
                "supported_relations": ["le"],
                "validation_state": "verification_only",
                "evidence": [{
                    "id": "test.loss-evidence",
                    "kind": "conformance_suite",
                    "artifact": {
                        "path": "evidence/loss.json", "sha256": "d" * 64,
                        "bytes": 128, "contract": "spike/validation-evidence/v1",
                    },
                }],
                "batch": {"supported": False, "max_candidates": 1},
                "incremental": {"supported": False, "change_kinds": []},
            }],
        }

    def test_validate_and_prepare_methods_expose_bounded_jobs(self) -> None:
        validated = handle({
            "id": "layout-validate-1",
            "method": "validate_layout_evaluation",
            "params": {"request": self.request},
        })
        self.assertTrue(validated["ok"])
        self.assertEqual(validated["result"]["candidate"]["sha256"], self.request["candidate"]["sha256"])

        prepared = handle({
            "id": "layout-prepare-1",
            "method": "prepare_layout_native_jobs",
            "params": {"request": self.request, "candidate": self.candidate, "registry": self.registry},
        })
        self.assertTrue(prepared["ok"])
        self.assertEqual(len(prepared["result"]), 1)
        item = prepared["result"][0]
        self.assertEqual(item["candidate_sha256"], self.request["candidate"]["sha256"])
        self.assertEqual(item["job"]["contract"], "spike/solver-job/v1")
        self.assertNotIn("candidate", item["job"])

    def test_registry_negotiation_and_candidate_preflight_are_worker_methods(self) -> None:
        registry = handle({
            "method": "validate_layout_metric_registry",
            "params": {"registry": self.registry},
        })
        self.assertTrue(registry["ok"])
        self.assertEqual(registry["result"]["registry_id"], "test.layout-metrics")

        negotiated = handle({
            "method": "negotiate_layout_requirements",
            "params": {"request": self.request, "registry": self.registry},
        })
        self.assertTrue(negotiated["ok"])
        self.assertEqual(negotiated["result"]["decisions"][0]["metric_id"], "pi.total_loss")

        preflight = handle({
            "method": "preflight_layout_candidate",
            "params": {"request": self.request, "candidate": self.candidate},
        })
        self.assertTrue(preflight["ok"])
        self.assertEqual(preflight["result"]["candidate_sha256"], self.request["candidate"]["sha256"])

    def test_prepare_rejects_unregistered_metric_before_job_derivation(self) -> None:
        unsupported = copy.deepcopy(self.registry)
        unsupported["metrics"][0]["id"] = "another.metric"
        response = handle({
            "method": "prepare_layout_native_jobs",
            "params": {"request": self.request, "candidate": self.candidate, "registry": unsupported},
        })
        self.assertFalse(response["ok"])
        self.assertEqual(response["layout_error_code"], "SPIKE-LAYOUT-REGISTRY-0005")

    def test_map_method_correlates_the_native_result(self) -> None:
        prepared = handle({
            "method": "prepare_layout_native_jobs",
            "params": {"request": self.request, "candidate": self.candidate, "registry": self.registry},
        })["result"][0]
        request_id = prepared["request_id"]
        mapped = handle({
            "method": "map_layout_evaluation_results",
            "params": {
                "request": self.request,
                "native_results": {
                    request_id: {
                        "contract": "spike/result-bundle/v2",
                        "request_id": request_id,
                        "status": "completed",
                        "validation_state": "verification_only",
                        "summary": {"total_loss_w": 4.0},
                    }
                },
            },
        })
        self.assertTrue(mapped["ok"])
        self.assertTrue(mapped["result"]["feasible"])
        self.assertEqual(mapped["result"]["requirements"][0]["status"], "satisfied")

    def test_layout_contract_code_survives_worker_error_mapping(self) -> None:
        invalid = copy.deepcopy(self.request)
        invalid["candidate"]["path"] = "../escape.json"
        response = handle({
            "id": "layout-invalid-1",
            "method": "validate_layout_evaluation",
            "params": {"request": invalid},
        })
        self.assertFalse(response["ok"])
        self.assertEqual(response["error_code"], "SPIKE-BE-IPC-E-0001")
        self.assertEqual(response["layout_error_code"], "SPIKE-LAYOUT-CONTRACT-0004")
        self.assertEqual(
            response["error_detail"]["context"]["layout_error_code"],
            "SPIKE-LAYOUT-CONTRACT-0004",
        )

    def test_prepare_rejects_missing_or_malformed_candidate_as_worker_error(self) -> None:
        missing = handle({
            "id": "layout-missing-design-1",
            "method": "prepare_layout_native_jobs",
            "params": {"request": self.request},
        })
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["error_code"], "SPIKE-BE-IPC-E-0001")
        self.assertEqual(missing["layout_error_code"], "SPIKE-LAYOUT-REGISTRY-0001")

        malformed = handle({
            "id": "layout-bad-design-1",
            "method": "prepare_layout_native_jobs",
            "params": {"request": self.request, "candidate": {"unknown_field": True}, "registry": self.registry},
        })
        self.assertFalse(malformed["ok"])
        self.assertEqual(malformed["error_code"], "SPIKE-BE-IPC-E-0001")
        self.assertEqual(malformed["type"], "SpikesLayoutAdapterError")
        self.assertEqual(malformed["layout_error_code"], "SPIKE-LAYOUT-PREFLIGHT-0001")


if __name__ == "__main__":
    unittest.main()
