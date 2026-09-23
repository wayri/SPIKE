# SPDX-License-Identifier: MIT
"""Run the complete bounded layout-scoring process example set.

The worker prepares immutable native jobs or maps already-correlated results to
dimensionless scores.  It deliberately does not route, place, mesh, or solve.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile


REPOSITORY = Path(__file__).resolve().parents[2]
ENTRY = REPOSITORY / "scripts" / "spike_layout_scoring_worker_entry.py"
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.layout_scoring_process import JOB_CONTRACT
from python.spike_core.spikes_layout_adapter import (
    LAYOUT_EVALUATION_CONTRACT,
    design_ir_artifact_identity,
)


def _candidate() -> dict:
    return DesignIRV2.from_v1(
        DesignIR(design_id="layout-example"), source_digest="1" * 64,
    ).to_dict()


def _request(candidate: dict, consumer: str) -> dict:
    identity = design_ir_artifact_identity(candidate)
    return {
        "contract": LAYOUT_EVALUATION_CONTRACT,
        "record_type": "request",
        "evaluation_id": f"{consumer}.iteration-1",
        "consumer": {
            "kind": consumer,
            "implementation": "spike-example-consumer",
            "version": "1",
        },
        "candidate": {
            "path": "candidates/layout.json",
            "sha256": identity["sha256"],
            "bytes": identity["bytes"],
            "contract": "spike/design-ir/v2",
        },
        "requirements": [{
            "id": "minimum.total-loss",
            "evaluator": "native_solver",
            "kind": "objective",
            "metric_id": "pi.total_loss",
            "result_key": "total_loss_w",
            "relation": "minimize",
            "dimension": [2, 1, -3, 0, 0, 0, 0],
            "weight": 2.0,
            "normalization_si": 5.0,
            "scope": {"frame": "board", "entity_ids": []},
        }],
        "physics_evaluations": [{
            "id": "loss.solve-1",
            "requirement_ids": ["minimum.total-loss"],
            "model": {
                "path": "models/layout.json",
                "sha256": "2" * 64,
                "bytes": 1024,
                "contract": "spike/physics-model/v1",
            },
            "study": {"type": "stationary"},
            "requested_outputs": ["summary", "issues"],
        }],
        "resources": {
            "max_memory_bytes": 536870912,
            "max_wall_time_s": 600,
            "ranks": 1,
            "threads": 1,
        },
        "deterministic": True,
    }


def _registry() -> dict:
    return {
        "contract": "spike/layout-metric-registry/v1",
        "registry_id": "examples.layout-metrics",
        "registry_version": "1.0.0",
        "producer": {"implementation": "spike-examples", "version": "1"},
        "metrics": [{
            "id": "pi.total_loss",
            "dimension": [2, 1, -3, 0, 0, 0, 0],
            "evaluator": "native_solver",
            "result_key": "total_loss_w",
            "supported_consumers": ["autorouter", "autoplacer", "joint"],
            "supported_kinds": ["objective"],
            "supported_relations": ["minimize"],
            "validation_state": "verification_only",
            "evidence": [{
                "id": "examples.loss-verification",
                "kind": "conformance_suite",
                "artifact": {
                    "path": "evidence/loss.json",
                    "sha256": "3" * 64,
                    "bytes": 128,
                    "contract": "spike/validation-evidence/v1",
                },
            }],
            "batch": {"supported": True, "max_candidates": 16},
            "incremental": {
                "supported": True,
                "change_kinds": ["placement", "routing"],
            },
        }],
    }


def _invoke(root: Path, name: str, job: dict) -> tuple[int, dict | None]:
    job_dir = root / name
    job_dir.mkdir()
    (job_dir / "request.json").write_text(
        json.dumps(job, indent=2, sort_keys=True), encoding="utf-8",
    )
    process = subprocess.run(
        [
            sys.executable,
            str(ENTRY),
            "--request",
            f"{name}/request.json",
            "--result",
            f"{name}/result.json",
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    result_path = job_dir / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else None
    return process.returncode, result


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    cases = 0
    capability = subprocess.run(
        [sys.executable, str(ENTRY), "--capabilities"],
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    )
    advertised = json.loads(capability.stdout)
    _require(advertised["consumers"] == ["autorouter", "autoplacer", "joint"], "capability mismatch")
    _require(not advertised["routes_or_places"] and not advertised["meshes_or_solves"], "unsafe claim")
    cases += 1

    candidate = _candidate()
    with tempfile.TemporaryDirectory(prefix="spike-layout-examples-", dir=REPOSITORY) as raw:
        root = Path(raw)
        for consumer in ("autorouter", "autoplacer", "joint"):
            request = _request(candidate, consumer)
            prepare = {
                "contract": JOB_CONTRACT,
                "action": "prepare",
                "request": request,
                "candidate": candidate,
                "registry": _registry(),
                "batch_size": 1,
                "incremental": False,
            }
            code, envelope = _invoke(root, f"prepare-{consumer}", prepare)
            _require(code == 0 and envelope is not None and envelope["status"] == "completed", f"{consumer} prepare failed")
            native_job = envelope["result"]["native_jobs"][0]
            _require(envelope["result"]["consumer_kind"] == consumer, "consumer correlation failed")
            cases += 1

            score = {
                "contract": JOB_CONTRACT,
                "action": "score",
                "request": request,
                "native_results": {
                    native_job["request_id"]: {
                        "contract": "spike/result-bundle/v2",
                        "request_id": native_job["request_id"],
                        "status": "completed",
                        "validation_state": "verification_only",
                        "summary": {"total_loss_w": 4.0},
                    },
                },
            }
            code, envelope = _invoke(root, f"score-{consumer}", score)
            _require(code == 0 and envelope is not None, f"{consumer} score failed")
            _require(abs(envelope["result"]["objective_score"] - 1.6) < 1.0e-15, "score mismatch")
            cases += 1

        tampered = {
            "contract": JOB_CONTRACT,
            "action": "prepare",
            "request": _request(candidate, "autorouter"),
            "candidate": copy.deepcopy(candidate),
            "registry": _registry(),
        }
        tampered["candidate"]["design_id"] = "digest-tamper"
        code, envelope = _invoke(root, "reject-tampered-candidate", tampered)
        _require(code == 2 and envelope is not None and envelope["status"] == "failed", "digest tamper was accepted")
        cases += 1

        traversal = subprocess.run(
            [
                sys.executable,
                str(ENTRY),
                "--request",
                "prepare-autorouter/../request.json",
                "--result",
                "prepare-autorouter/result.json",
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        _require(traversal.returncode == 2, "path traversal was accepted")
        cases += 1

    print(f"PASS: {cases} layout-scoring examples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
