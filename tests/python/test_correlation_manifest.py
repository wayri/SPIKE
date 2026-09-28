# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Focused tests for hash-bound correlation evidence manifests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate_correlation_manifest.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_correlation_manifest", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load correlation manifest validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load_validator()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _quantity(measured: bool = False) -> dict[str, object]:
    return {
        "name": "impedance",
        "unit": "ohm",
        "uncertainty": (
            {"absolute": 0.02, "unit": "ohm", "confidence": 0.95}
            if measured else None
        ),
        "tolerance": {"absolute": 0.1, "relative": 0.01},
    }


def _manifest(payloads: dict[str, bytes]) -> dict[str, object]:
    datasets = []
    for kind in ("analytical", "independent_solver", "measured"):
        path = f"evidence/{kind}.json"
        datasets.append({
            "id": f"fixture-{kind}",
            "kind": kind,
            "status": "qualified",
            "status_reason": None,
            "input": {"path": path, "sha256": _sha(payloads[path])},
            "quantities": [_quantity(measured=kind == "measured")],
            "provenance": {
                "description": f"Synthetic {kind} validator fixture",
                "reference": "tests/python/test_correlation_manifest.py",
            },
            "solver": ({
                "name": "Independent Fixture Solver",
                "version": "1.2.3",
                "provenance": "test package independent-fixture-solver==1.2.3",
                "artifact_sha256": "a" * 64,
            } if kind == "independent_solver" else None),
        })
    return {
        "contract": "spike/correlation-evidence-manifest/v1",
        "manifest_id": "fixture.correlation",
        "subject": "Validator contract fixture; not engineering evidence",
        "datasets": datasets,
    }


class CorrelationManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.payloads = {
            f"evidence/{kind}.json": json.dumps({"kind": kind, "value": index}).encode()
            for index, kind in enumerate(("analytical", "independent_solver", "measured"))
        }
        for relative, payload in self.payloads.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        self.manifest_path = self.root / "manifest.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_manifest(self, manifest: dict[str, object]) -> None:
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_complete_manifest_reports_metadata_complete_and_hash_bound(self) -> None:
        self.write_manifest(_manifest(self.payloads))
        report = VALIDATOR.validate_manifest(self.manifest_path)
        self.assertEqual(report["status"], "metadata_complete")
        self.assertFalse(report["numerical_correlation_performed"])
        self.assertFalse(report["solver_signoff"])
        self.assertEqual(report["issues"], [])
        self.assertEqual(
            {item["kind"] for item in report["datasets"]},
            {"analytical", "independent_solver", "measured"},
        )
        self.assertEqual(report["manifest_sha256"], _sha(self.manifest_path.read_bytes()))

    def test_tampered_dataset_fails_closed(self) -> None:
        self.write_manifest(_manifest(self.payloads))
        (self.root / "evidence" / "measured.json").write_bytes(b"tampered")
        report = VALIDATOR.validate_manifest(self.manifest_path)
        self.assertEqual(report["status"], "invalid")
        self.assertTrue(any(issue.startswith("sha256_mismatch:fixture-measured")
                            for issue in report["issues"]))

    def test_declared_missing_and_unqualified_evidence_are_not_invalid_or_promoted(self) -> None:
        manifest = _manifest(self.payloads)
        analytical, _, measured = manifest["datasets"]
        analytical["status"] = "unqualified"
        analytical["status_reason"] = "Tolerance awaits knowledgeable review"
        measured.update({
            "status": "missing",
            "status_reason": "No measured dataset has been supplied",
            "input": None,
            "provenance": None,
        })
        measured["quantities"][0]["uncertainty"] = None
        self.write_manifest(manifest)

        report = VALIDATOR.validate_manifest(self.manifest_path)
        self.assertEqual(report["status"], "evidence_incomplete")
        self.assertIn("evidence_unqualified:analytical:fixture-analytical", report["issues"])
        self.assertIn("evidence_missing:measured:fixture-measured", report["issues"])

        completed = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.manifest_path)],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["status"], "evidence_incomplete")

    def test_qualified_evidence_requires_tolerance_uncertainty_and_solver_provenance(self) -> None:
        manifest = _manifest(self.payloads)
        manifest["datasets"][0]["quantities"][0]["tolerance"] = None
        manifest["datasets"][1]["solver"] = None
        manifest["datasets"][2]["quantities"][0]["uncertainty"] = None
        self.write_manifest(manifest)
        report = VALIDATOR.validate_manifest(self.manifest_path)
        self.assertEqual(report["status"], "invalid")
        self.assertTrue(any(".tolerance" in issue for issue in report["issues"]))
        self.assertTrue(any(".solver" in issue for issue in report["issues"]))
        self.assertTrue(any(".uncertainty" in issue for issue in report["issues"]))

    def test_claimed_evidence_must_exist_beneath_manifest_directory(self) -> None:
        manifest = _manifest(self.payloads)
        manifest["datasets"][0]["input"]["path"] = "../outside.json"
        manifest["datasets"][1]["input"]["path"] = "evidence/not-present.json"
        self.write_manifest(manifest)
        report = VALIDATOR.validate_manifest(self.manifest_path)
        self.assertEqual(report["status"], "invalid")
        self.assertTrue(any(issue.startswith("unsafe_path:") for issue in report["issues"]))
        self.assertTrue(any(issue.startswith("input_missing:") for issue in report["issues"]))

    def test_noncanonical_and_drive_relative_input_paths_are_rejected(self) -> None:
        for invalid_path in ("evidence//analytical.json", "evidence/./analytical.json", "C:/evidence.json"):
            with self.subTest(path=invalid_path):
                manifest = _manifest(self.payloads)
                manifest["datasets"][0]["input"]["path"] = invalid_path
                self.write_manifest(manifest)
                report = VALIDATOR.validate_manifest(self.manifest_path)
                self.assertEqual(report["status"], "invalid")
                self.assertTrue(any(issue.startswith("unsafe_path:") for issue in report["issues"]))

    def test_oversized_manifest_is_rejected_before_json_parsing(self) -> None:
        self.manifest_path.write_bytes(b" " * (VALIDATOR.MAX_MANIFEST_BYTES + 1))
        report = VALIDATOR.validate_manifest(self.manifest_path)
        self.assertEqual(report["status"], "invalid")
        self.assertIsNone(report["manifest_sha256"])
        self.assertEqual(
            report["issues"],
            [f"manifest_too_large:{VALIDATOR.MAX_MANIFEST_BYTES + 1}:{VALIDATOR.MAX_MANIFEST_BYTES}"],
        )

    def test_duplicate_json_field_is_invalid(self) -> None:
        self.manifest_path.write_text(
            '{"contract":"spike/correlation-evidence-manifest/v1",'
            '"contract":"other","manifest_id":"x","subject":"x","datasets":[]}',
            encoding="utf-8",
        )
        report = VALIDATOR.validate_manifest(self.manifest_path)
        self.assertEqual(report["status"], "invalid")
        self.assertIn("duplicate JSON field", report["issues"][0])

    def test_wrong_field_types_report_invalid_instead_of_crashing(self) -> None:
        manifest = _manifest(self.payloads)
        manifest["datasets"][0]["kind"] = []
        manifest["datasets"][1]["status"] = {}
        self.write_manifest(manifest)
        report = VALIDATOR.validate_manifest(self.manifest_path)
        self.assertEqual(report["status"], "invalid")
        self.assertIn("invalid_value:datasets[0].kind", report["issues"])
        self.assertIn("invalid_value:datasets[1].status", report["issues"])


if __name__ == "__main__":
    unittest.main()
