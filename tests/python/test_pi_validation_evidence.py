import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from python.spike_core.pi_validation_evidence import (
    PiValidationEvidenceError,
    load_bound_pi_workflow_evidence,
    validate_release_qualification_binding,
)


def evidence() -> dict:
    digest = "a" * 64
    return {
        "contract": "spike/pi-workflow-qualification-evidence/v1",
        "evidence_id": "native-linear-mna-reference-2026-01",
        "workflow_id": "circuit.spice_compatible_mna",
        "native_owner": "spike.native.mna",
        "qualification_profile_id": "native-linear-mna-reference-v1",
        "qualification_level": "reference_validated",
        "status": "passed",
        "generated_at": "2026-08-30T00:00:00Z",
        "candidate": {
            "solver_id": "spike.native.mna",
            "solver_version": "0.2.0",
            "worker_version": "0.2.0-alpha.2",
            "worker_executable_sha256": digest,
            "worker_manifest_sha256": digest,
            "runtime_snapshot_digest": digest,
        },
        "summary": {"total": 1, "passed": 1, "failed": 0, "skipped": 0},
        "cases": [{
            "case_id": "mna.reference-corpus",
            "classes": [
                "analytical", "independent_solver", "measurement", "dc", "ac", "transient",
                "dependent_source", "dense_sparse_parity", "timestep_convergence",
            ],
            "status": "passed",
            "input": {"contract": "spike/native-mna-request/v1", "sha256": digest},
            "candidate_result": {"contract": "spike/native-mna-result/v1", "sha256": digest},
            "reference": {
                "kind": "independent_solver", "engine_id": "external.ngspice", "engine_version": "46",
                "input_sha256": digest, "result_sha256": digest,
            },
            "metrics": [{"metric_id": "vout", "candidate": 1.0, "reference": 1.0}],
            "convergence": {"required": True, "levels": [1, 2, 3]},
        }],
        "applicability": {"devices": "linear_only"},
        "limitations": ["Nonlinear devices are excluded."],
    }


class PiValidationEvidenceTests(unittest.TestCase):
    def test_digest_bound_profile_evidence_loads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "pi" / "mna.json"
            artifact.parent.mkdir()
            data = json.dumps(evidence(), sort_keys=True).encode("utf-8")
            artifact.write_bytes(data)
            result = load_bound_pi_workflow_evidence(root, {
                "evidence_id": "native-linear-mna-reference-2026-01",
                "profile_id": "native-linear-mna-reference-v1",
                "artifact_uri": "pi/mna.json",
                "sha256": hashlib.sha256(data).hexdigest(),
            })
            self.assertEqual(result["workflow_id"], "circuit.spice_compatible_mna")

    def test_tamper_missing_class_and_unsafe_uri_fail_closed(self) -> None:
        with self.assertRaisesRegex(PiValidationEvidenceError, "safe relative URI"):
            validate_release_qualification_binding({
                "evidence_id": "mna-evidence", "profile_id": "mna-profile",
                "artifact_uri": "../escape.json", "sha256": "a" * 64,
            })
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "evidence.json"
            value = evidence()
            value["cases"][0]["classes"].remove("measurement")
            data = json.dumps(value).encode("utf-8")
            artifact.write_bytes(data)
            binding = {
                "evidence_id": value["evidence_id"], "profile_id": value["qualification_profile_id"],
                "artifact_uri": "evidence.json", "sha256": hashlib.sha256(data).hexdigest(),
            }
            with self.assertRaisesRegex(PiValidationEvidenceError, "missing required case classes"):
                load_bound_pi_workflow_evidence(root, binding)
            binding["sha256"] = "b" * 64
            with self.assertRaisesRegex(PiValidationEvidenceError, "digest"):
                load_bound_pi_workflow_evidence(root, binding)


if __name__ == "__main__":
    unittest.main()
