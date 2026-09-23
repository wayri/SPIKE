from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_stage_module():
    spec = importlib.util.spec_from_file_location(
        "stage_windows_release_evidence",
        ROOT / "scripts" / "stage_windows_release_evidence.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WindowsReleaseEvidenceStageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stage = load_stage_module()

    def _fixture(self, root: Path, artifact: Path) -> dict[str, Path]:
        (root / "config").mkdir(parents=True)
        (root / "licenses").mkdir()
        (root / "worker").mkdir()
        notices = root / "THIRD_PARTY_NOTICES.md"
        notices.write_text("# Notices\n\n## fixture-component\nMIT.\n", encoding="utf-8")
        evidence = root / "licenses" / "license-resolution.txt"
        evidence.write_text("Reviewed upstream license metadata.\n", encoding="utf-8")
        inventory = root / "config" / "windows-component-inventory.json"
        identity = "a" * 64
        inventory.write_text(json.dumps({
            "contract": "spike/windows-component-inventory/v1", "platform": "windows-x64",
            "components": [{
                "purl": "pkg:pypi/fixture-component@1.2.3", "name": "fixture-component",
                "version": "1.2.3", "ecosystem": "python", "scope": "bundled",
                "integrity": {"algorithm": "sha256", "value": "b" * 64},
                "declared_license": "LicenseRef-Legacy-Metadata", "identity_sha256": identity,
            }],
        }), encoding="utf-8")
        approvals = root / "licenses" / "windows-component-approvals.json"
        approvals.write_text(json.dumps({
            "contract": "spike/windows-component-approvals/v1", "platform": "windows-x64",
            "inventory_sha256": digest(inventory), "notices_sha256": digest(notices),
            "approvals": [{
                "purl": "pkg:pypi/fixture-component@1.2.3", "identity_sha256": identity,
                "disposition": "approved", "approved_license_expression": "MIT",
                "compliance_approved": True, "redistribution_approved": True,
                "notice": {"status": "included", "file": notices.name,
                           "sha256": digest(notices), "marker": "fixture-component"},
                "review": {"ticket": "LEGAL-1", "reviewer": "Fixture Reviewer",
                           "reviewed_at": "2026-08-27T00:00:00Z"},
                "license_resolution_evidence": {
                    "file": "licenses/license-resolution.txt", "sha256": digest(evidence),
                },
            }],
        }), encoding="utf-8")
        dependencies = root / "dependencies.lock.json"
        dependencies.write_text(json.dumps({
            "manifest": "spike/dependencies/v1",
            "signature": {"required": True, "format": "cms-detached-sha256",
                          "sidecar": "dependencies.lock.json.p7s"},
        }), encoding="utf-8")
        worker_manifest = root / "worker" / "spike-worker.manifest.json"
        worker_manifest.write_text(json.dumps({
            "contract": "spike/packaged-worker-manifest/v2", "files": [
                {"path": "spike-worker.exe", "size": 7, "sha256": "c" * 64},
            ],
        }), encoding="utf-8")
        artifact.mkdir()
        signature = artifact / "dependencies.lock.json.p7s"
        signature.write_bytes(b"public-cms-signature")
        return {
            "dependencies": dependencies, "signature": signature,
            "worker_manifest": worker_manifest, "notices": notices,
            "inventory": inventory, "approvals": approvals, "evidence": evidence,
        }

    def test_stages_exact_public_evidence_without_changing_installer_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            artifact = base / "artifact"
            source.mkdir()
            paths = self._fixture(source, artifact)
            installer = artifact / "SPIKE.msi"
            installer.write_bytes(b"signed-installer")
            before = digest(installer)
            report = self.stage.stage_windows_release_evidence(
                source, artifact,
                dependencies_lock_path=paths["dependencies"],
                dependency_signature_path=paths["signature"],
                worker_manifest_path=paths["worker_manifest"],
                notices_path=paths["notices"], inventory_path=paths["inventory"],
                approvals_path=paths["approvals"],
            )
            self.assertEqual(report["status"], "passed")
            self.assertFalse(report["production_qualified"])
            self.assertEqual(digest(installer), before)
            expected = {
                "dependencies.lock.json", "dependencies.lock.json.p7s",
                "bundled/spike-worker.manifest.json", "THIRD_PARTY_NOTICES.md",
                "config/windows-component-inventory.json",
                "licenses/windows-component-approvals.json",
                "licenses/license-resolution.txt",
            }
            self.assertEqual({item["file"] for item in report["files"]}, expected)
            for item in report["files"]:
                self.assertEqual(digest(artifact / Path(item["file"])), item["sha256"])

    def test_rejects_dependency_sidecar_name_not_bound_by_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            artifact = base / "artifact"
            source.mkdir()
            paths = self._fixture(source, artifact)
            wrong = artifact / "wrong.p7s"
            wrong.write_bytes(b"wrong")
            with self.assertRaisesRegex(ValueError, "filename differs"):
                self.stage.stage_windows_release_evidence(
                    source, artifact,
                    dependencies_lock_path=paths["dependencies"],
                    dependency_signature_path=wrong,
                    worker_manifest_path=paths["worker_manifest"],
                    notices_path=paths["notices"], inventory_path=paths["inventory"],
                    approvals_path=paths["approvals"],
                )


if __name__ == "__main__":
    unittest.main()
