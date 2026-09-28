# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.layout_scoring_process import (
    JOB_CONTRACT,
    RESULT_CONTRACT,
    _admit_paths,
    capability_manifest,
    execute_job,
)
from python.spike_core.spikes_layout_adapter import (
    LAYOUT_EVALUATION_CONTRACT,
    design_ir_artifact_identity,
)


class LayoutScoringProcessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidate = DesignIRV2.from_v1(
            DesignIR(design_id="board-1"), source_digest="c" * 64,
        ).to_dict()
        identity = design_ir_artifact_identity(self.candidate)
        self.request = {
            "contract": LAYOUT_EVALUATION_CONTRACT,
            "record_type": "request",
            "evaluation_id": "layout.iteration-1",
            "consumer": {"kind": "autoplacer", "implementation": "custom-placer", "version": "1"},
            "candidate": {
                "path": "candidates/layout-1.json", "sha256": identity["sha256"],
                "bytes": identity["bytes"], "contract": "spike/design-ir/v2",
            },
            "requirements": [{
                "id": "maximum.loss", "evaluator": "native_solver",
                "kind": "objective", "metric_id": "pi.total_loss",
                "result_key": "total_loss_w", "relation": "minimize",
                "dimension": [2, 1, -3, 0, 0, 0, 0], "weight": 2.0,
                "normalization_si": 5.0,
                "scope": {"frame": "board", "entity_ids": []},
            }],
            "physics_evaluations": [{
                "id": "loss.solve-1", "requirement_ids": ["maximum.loss"],
                "model": {
                    "path": "models/layout-1.json", "sha256": "b" * 64,
                    "bytes": 1024, "contract": "spike/physics-model/v1",
                },
                "study": {"type": "stationary"},
                "requested_outputs": ["summary", "issues"],
            }],
            "resources": {
                "max_memory_bytes": 536870912, "max_wall_time_s": 600,
                "ranks": 1, "threads": 1,
            },
            "deterministic": True,
        }
        self.registry = {
            "contract": "spike/layout-metric-registry/v1",
            "registry_id": "test.layout-metrics", "registry_version": "1.0.0",
            "producer": {"implementation": "test-evaluator", "version": "1"},
            "metrics": [{
                "id": "pi.total_loss", "dimension": [2, 1, -3, 0, 0, 0, 0],
                "evaluator": "native_solver", "result_key": "total_loss_w",
                "supported_consumers": ["autorouter", "autoplacer", "joint"],
                "supported_kinds": ["objective"], "supported_relations": ["minimize"],
                "validation_state": "verification_only",
                "evidence": [{
                    "id": "test.loss-evidence", "kind": "conformance_suite",
                    "artifact": {
                        "path": "evidence/loss.json", "sha256": "d" * 64,
                        "bytes": 128, "contract": "spike/validation-evidence/v1",
                    },
                }],
                "batch": {"supported": True, "max_candidates": 16},
                "incremental": {"supported": True, "change_kinds": ["placement", "routing"]},
            }],
        }

    def _prepare_job(self, consumer: str = "autoplacer") -> dict:
        request = copy.deepcopy(self.request)
        request["consumer"]["kind"] = consumer
        return {
            "contract": JOB_CONTRACT, "action": "prepare", "request": request,
            "candidate": self.candidate, "registry": self.registry,
            "batch_size": 1, "incremental": False,
        }

    def _execute(self, job: dict) -> dict:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            request_path = root / "request.json"
            result_path = root / "result.json"
            request_path.write_text(json.dumps(job), encoding="utf-8")
            envelope = execute_job(request_path, result_path)
            self.assertEqual(envelope, json.loads(result_path.read_text(encoding="utf-8")))
            return envelope

    def test_capability_is_narrow_and_exposes_all_layout_consumers(self) -> None:
        capability = capability_manifest()
        self.assertEqual(capability["consumers"], ["autorouter", "autoplacer", "joint"])
        self.assertFalse(capability["routes_or_places"])
        self.assertFalse(capability["meshes_or_solves"])
        self.assertEqual(capability["validation_state"], "experimental")

    def test_prepare_exposes_autoplacer_and_joint_jobs_after_negotiation(self) -> None:
        for consumer in ("autoplacer", "joint"):
            with self.subTest(consumer=consumer):
                envelope = self._execute(self._prepare_job(consumer))
                self.assertEqual(envelope["status"], "completed")
                self.assertEqual(envelope["result"]["consumer_kind"], consumer)
                self.assertEqual(envelope["result"]["preflight"]["consumer_kind"], consumer)
                self.assertEqual(len(envelope["result"]["native_jobs"]), 1)

    def test_score_maps_correlated_result_to_dimensionless_objective(self) -> None:
        prepared = self._execute(self._prepare_job())["result"]["native_jobs"][0]
        score_job = {
            "contract": JOB_CONTRACT, "action": "score", "request": self.request,
            "native_results": {
                prepared["request_id"]: {
                    "contract": "spike/result-bundle/v2",
                    "request_id": prepared["request_id"], "status": "completed",
                    "validation_state": "verification_only",
                    "summary": {"total_loss_w": 4.0},
                },
            },
        }
        result = self._execute(score_job)["result"]
        self.assertEqual(result["objective_score_state"], "available")
        self.assertAlmostEqual(result["objective_score"], 1.6)
        self.assertTrue(result["objective_score_lower_is_better"])

    def test_unknown_fields_duplicate_json_and_unsafe_controls_fail_closed(self) -> None:
        bad = self._prepare_job()
        bad["unknown"] = True
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "request.json"
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown or missing"):
                execute_job(path, Path(raw) / "result.json")

            path.write_text('{"contract":"%s","contract":"%s"}' % (JOB_CONTRACT, JOB_CONTRACT), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                execute_job(path, Path(raw) / "result.json")

        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "job").mkdir()
            (root / "job" / "request.json").write_text("{}", encoding="utf-8")
            try:
                os.chdir(root)
                with self.assertRaisesRegex(ValueError, "normalized"):
                    _admit_paths("job/../request.json", "job/result.json")
                with self.assertRaisesRegex(ValueError, "job directory"):
                    _admit_paths("job/request.json", "result.json")
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
