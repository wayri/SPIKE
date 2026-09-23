"""Contract tests for the portable clean-machine evidence harness."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.verify_wave1_clean_machine_harness import verify


ROOT = Path(__file__).resolve().parents[2]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CleanMachineHarnessTests(unittest.TestCase):
    def test_prepare_stages_only_a_manifest_bound_installer_and_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact_dir = root / "artifacts"
            artifact_dir.mkdir()
            installer = artifact_dir / "SPIKE.msi"
            installer.write_bytes(b"installer")
            alternate = artifact_dir / "SPIKE.exe"
            alternate.write_bytes(b"alternate")
            manifest = root / "installers.json"
            manifest.write_text(json.dumps({
                "contract": "spike/windows-installer-manifest/v1",
                "product": "SPIKE", "version": "0.2.0", "application_version": "0.2.0-alpha.1",
                "channel": "engineering-preview", "production_qualified": False,
                "files": [
                    {"file": installer.name, "sha256": sha(installer), "size": installer.stat().st_size, "authenticode": "NotSigned"},
                    {"file": alternate.name, "sha256": sha(alternate), "size": alternate.stat().st_size, "authenticode": "NotSigned"},
                ],
            }), encoding="utf-8")
            fixture = root / "fixture.spike"
            with zipfile.ZipFile(fixture, "w") as archive:
                archive.writestr("manifest.json", json.dumps({"manifest_payload_sha256": "a" * 64}))
            summary = root / "fixture.json"
            summary.write_text(json.dumps({"manifest_payload_sha256": "a" * 64}), encoding="utf-8")
            output = root / "stage"
            completed = subprocess.run([sys.executable, str(ROOT / "scripts/prepare_wave1_clean_machine_harness.py"),
                "--installer-manifest", str(manifest), "--artifact-dir", str(artifact_dir), "--installer", installer.name,
                "--fixture", str(fixture), "--fixture-summary", str(summary), "--output", str(output)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            inputs = json.loads((output / "inputs.json").read_text(encoding="utf-8"))
            self.assertEqual(inputs["installer"]["sha256"], sha(output / "payload/SPIKE.msi"))
            self.assertEqual(inputs["fixture"]["manifest_payload_sha256"], "a" * 64)
            self.assertEqual(inputs["runner"]["sha256"], sha(output / "run_wave1_clean_machine_harness.ps1"))
            self.assertEqual((output / "inputs.sha256").read_text(encoding="ascii").split()[0], sha(output / "inputs.json"))

    def test_prepare_rejects_an_installer_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "installers.json"
            manifest.write_text(json.dumps({
                "contract": "spike/windows-installer-manifest/v1",
                "files": [{"file": "../escape.msi", "sha256": "a" * 64, "size": 1}],
            }), encoding="utf-8")
            completed = subprocess.run([
                sys.executable, str(ROOT / "scripts/prepare_wave1_clean_machine_harness.py"),
                "--installer-manifest", str(manifest), "--artifact-dir", str(root),
                "--installer", "../escape.msi", "--output", str(root / "stage"),
            ], capture_output=True, text=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("safe MSI or EXE basename", completed.stderr)

    def test_verifier_rejects_legacy_and_unattested_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "mechanics.json"
            artifact.write_text("{}", encoding="utf-8")
            record = root / "harness-run.json"
            payload = {"contract": "spike/wave1-clean-machine-harness/v1", "run_id": "r", "provider": "not-isolated",
                "eligible_for_human_review": False, "inputs_sha256": "a" * 64, "installer_sha256": "b" * 64,
                "before_manifest_payload_sha256": "c" * 64, "after_manifest_payload_sha256": "d" * 64,
                "environment": {}, "mechanics": {}, "artifacts": [{"path": artifact.name, "sha256": sha(artifact)}]}
            record.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "legacy"):
                verify(record)
            payload.update({
                "contract": "spike/wave1-clean-machine-harness/v2", "provider": "external-clean-vm",
                "eligible_for_human_review": True,
                "environment": {"provider": "external-clean-vm", "os": {"name": "Windows"}, "gpu": [{"name": "GPU"}], "webview2_version": "1", "display_scale_percent": 100, "process_path_entries": 1, "pre_install_spike_residue": {"uninstall_products": [], "install_paths": [], "file_association": {"user_progid": None}}},
                "mechanics": {"staged_hashes_verified": True, "installer_started": True, "installer_exit_code": 0, "installed_product": [], "spike_association": {}, "launched_process_id": None, "after_project_supplied": False},
                "environment_attestation": {"status": "unattested", "cryptographically_verified": False, "eligible_for_human_review": False, "note": "No attestation."},
            })
            record.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "attestation"):
                verify(record)


if __name__ == "__main__":
    unittest.main()
