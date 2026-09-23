"""Fail-closed contract tests for Wave 1 packaged acceptance composition."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core import wave1_packaged_acceptance as acceptance
from python.spike_core import wave1_packaged_mutation as mutation


ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Wave1PackagedAcceptanceTests(unittest.TestCase):
    def write_json(self, root: Path, name: str, payload: object) -> Path:
        path = root / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def valid_human_evidence(self, root: Path) -> Path:
        artifact = root / "review.txt"
        artifact.write_text("reviewed", encoding="utf-8")
        digest = _sha256(artifact)
        pixel = root / "pixel.png"
        pixel.write_bytes(b"reviewed-pixel")
        pixel_digest = _sha256(pixel)
        environment = {
            "provider": "external-clean-vm", "os": {"name": "Windows 11"},
            "gpu": [{"name": "fixture"}], "webview2_version": "1.0", "display_scale_percent": 100,
            "process_path_entries": 1,
            "pre_install_spike_residue": {"uninstall_products": [], "install_paths": [], "file_association": {"user_progid": None, "registered_progid": None}},
        }
        inputs = root / "inputs.json"
        inputs.write_text(json.dumps({"run_id": "run-1", "runner": {"sha256": ""}}), encoding="utf-8")
        runner = root / "executing-runner.ps1"
        runner.write_text("# staged runner\n", encoding="utf-8")
        inputs.write_text(json.dumps({"run_id": "run-1", "runner": {"sha256": _sha256(runner)}}), encoding="utf-8")
        attestation = root / "environment-attestation.json"
        attestation.write_text(json.dumps({
            "contract": "spike/wave1-environment-attestation/v1", "provider": "external-clean-vm", "run_id": "run-1",
            "inputs_sha256": _sha256(inputs), "attestor": "QA", "issued_at": "2026-08-24T00:00:00Z",
            "environment_id": "clean-vm-1", "isolation_claim": "Prepared isolated VM; subject to human review.",
        }), encoding="utf-8")
        harness_artifacts = []
        for name, content in {
            "after-project.spike": b"changed-project",
            "mechanics.json": b"{}",
            "preflight.json": b"{}",
            "review-required.json": b"{}",
        }.items():
            path = root / name
            path.write_bytes(content)
            harness_artifacts.append({"path": name, "sha256": _sha256(path)})
        for path in (inputs, runner, attestation):
            harness_artifacts.append({"path": path.name, "sha256": _sha256(path)})
        harness = root / "harness-run.json"
        harness.write_text(json.dumps({
            "contract": "spike/wave1-clean-machine-harness/v2", "run_id": "run-1", "provider": "external-clean-vm",
            "eligible_for_human_review": True, "installer_sha256": "a" * 64,
            "before_manifest_payload_sha256": "b" * 64, "after_manifest_payload_sha256": "c" * 64,
            "inputs_sha256": _sha256(inputs), "environment": environment,
            "mechanics": {"staged_hashes_verified": True, "installer_started": True, "installer_exit_code": 0, "installed_product": [{"name": "SPIKE"}], "spike_association": {"command": "SPIKE"}, "launched_process_id": 42, "after_project_supplied": True},
            "environment_attestation": {
                "status": "supplied_for_human_review", "cryptographically_verified": False, "eligible_for_human_review": True,
                "note": "Review input only; not proof.", "contract": "spike/wave1-environment-attestation/v1",
                "provider": "external-clean-vm", "run_id": "run-1", "inputs_sha256": _sha256(inputs),
                "attestor": "QA", "issued_at": "2026-08-24T00:00:00Z", "environment_id": "clean-vm-1",
                "isolation_claim": "Prepared isolated VM; subject to human review.", "artifact": {"path": attestation.name, "sha256": _sha256(attestation)},
            },
            "artifacts": harness_artifacts,
        }), encoding="utf-8")
        harness_digest = _sha256(harness)
        checks = [
            {"id": identifier, "status": "passed", "detail": "reviewed", "artifacts": [{"path": pixel.name, "sha256": pixel_digest}] if identifier == "pixel_views" else [{"path": artifact.name, "sha256": digest}]}
            for identifier in acceptance.REQUIRED_HUMAN_CHECKS
        ]
        checks[0]["artifacts"].append({"path": harness.name, "sha256": harness_digest})
        return self.write_json(root, "human.json", {
            "contract": acceptance.HUMAN_EVIDENCE_CONTRACT,
            "reviewer": "QA",
            "reviewed_at": "2026-08-24T00:00:00Z",
            "environment": environment,
            "installer_sha256": "a" * 64,
            "before_manifest_payload_sha256": "b" * 64,
            "after_manifest_payload_sha256": "c" * 64,
            "checks": checks,
        })

    def signed_candidate_manifest(self, root: Path) -> Path:
        msi = root / "SPIKE_0.2.0_x64_en-US.msi"; msi.write_bytes(b"signed-msi")
        nsis = root / "SPIKE_0.2.0_x64-setup.exe"; nsis.write_bytes(b"signed-nsis")
        signer = "A" * 40; authority = "B" * 40
        def artifact(path: Path, kind: str) -> dict[str, object]:
            return {"file": path.name, "kind": kind, "size": path.stat().st_size, "sha256": _sha256(path), "authenticode": {"status": "Valid", "file_digest_algorithm": "sha256", "signer_thumbprint": signer, "timestamp_protocol": "rfc3161", "timestamp_authority_thumbprint": authority}}
        return self.write_json(root, "signed-installers.json", {
            "contract": "spike/windows-installer-manifest/v2", "product": "SPIKE", "version": "0.2.0", "application_version": "0.2.0-alpha.1",
            "channel": "production-candidate", "release_state": "production-candidate", "license_key_id": "production-test", "production_qualified": False, "generated_at": "2026-08-27T00:00:00Z",
            "signing_policy": {"required": True, "expected_signer_thumbprint": signer, "digest_algorithm": "sha256", "timestamp_required": True, "timestamp_protocol": "rfc3161"},
            "files": [artifact(msi, "msi"), artifact(nsis, "nsis")],
        })

    def test_qualification_cli_requires_an_explicit_extracted_root(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "qualify_wave1_packaged_assembly.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("--extracted-root", completed.stderr)

    def test_installer_manifest_rejects_traversal_digest_mismatch_and_production_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installer = root / "SPIKE-preview.msi"
            installer.write_bytes(b"candidate")
            manifest = self.write_json(root, "installers.json", {
                "contract": "spike/windows-installer-manifest/v1",
                "production_qualified": True,
                "files": [
                    {"file": "../escape.msi", "sha256": "a" * 64, "size": 1, "authenticode": "NotSigned"},
                    {"file": installer.name, "sha256": "0" * 64, "size": installer.stat().st_size, "authenticode": "NotSigned"},
                ],
            })
            checks, _ = acceptance.verify_installer_manifest(manifest, root)

        self.assertEqual([check["id"] for check in checks], ["installer.manifest_contract", "installer.candidate_set", "installer.artifact_0", "installer.artifact_1", "installer.release_identity", "installer.preview_boundary"])
        self.assertTrue(all(check["status"] == "failed" for check in checks[2:]))

    def test_signed_candidate_requires_two_post_sign_artifacts_and_never_claims_qualification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.signed_candidate_manifest(root)
            probe = lambda _path: {"status": "Valid", "signer_thumbprint": "A" * 40, "timestamp_authority_thumbprint": "B" * 40}
            checks, candidate = acceptance.verify_installer_manifest(
                manifest, root, expected_application_version="0.2.0-alpha.1", authenticode_probe=probe,
            )
            self.assertTrue(all(check["status"] == "passed" for check in checks))
            self.assertEqual(candidate["contract"], "spike/windows-installer-manifest/v2")
            self.assertEqual(candidate["manifest_sha256"], _sha256(manifest))
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["files"][0]["authenticode"]["timestamp_protocol"] = "legacy"
            payload["production_qualified"] = True
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            rejected, _ = acceptance.verify_installer_manifest(manifest, root, authenticode_probe=probe)
        self.assertEqual(rejected[-1]["status"], "failed")
        self.assertEqual(rejected[2]["status"], "failed")

    def test_signed_candidate_rejects_manifest_only_signature_claims(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.signed_candidate_manifest(root)
            rejected, _ = acceptance.verify_installer_manifest(
                manifest, root,
                authenticode_probe=lambda _path: {
                    "status": "NotSigned", "signer_thumbprint": "", "timestamp_authority_thumbprint": "",
                },
            )
        self.assertEqual(rejected[2]["status"], "failed")
        self.assertEqual(rejected[3]["status"], "failed")

    def test_worker_manifest_requires_complete_verified_inventory_and_qualification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            member = root / "spike-worker.exe"
            member.write_bytes(b"worker")
            manifest = self.write_json(root, "worker.json", {
                "contract": "spike/packaged-worker-manifest/v2",
                "worker_version": "0.2.0",
                "files": [{"path": member.name, "size": member.stat().st_size, "sha256": _sha256(member)}],
                "benchmark_summary": {"total": 15, "passed": 15, "failed": 0},
                "runtime_qualification": {"status": "passed", "summary": {"total": 8, "passed": 8, "failed": 0}},
                "geometry_arrow_probe": {
                    "contract": "spike/packaged-arrow-probe/v1", "status": "passed",
                    "table_contract": "spike/copper-geometry-arrow/v4", "rows": 4,
                    "artifact_sha256": "a" * 64, "design_id": "fixture-design",
                    "retained_unresolved_occurrences": 1,
                },
            })
            checks, _ = acceptance.verify_packaged_worker_manifest(manifest, root)
            self.assertTrue(all(check["status"] == "passed" for check in checks))

            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["files"][0]["path"] = "../spike-worker.exe"
            payload["runtime_qualification"]["summary"]["passed"] = 7
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            rejected, _ = acceptance.verify_packaged_worker_manifest(manifest, root)

        self.assertEqual(rejected[1]["status"], "failed")
        self.assertEqual(rejected[3]["status"], "failed")

    def test_runtime_report_requires_identical_valid_snapshot_digests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.write_json(root, "runtime.json", {
                "contract": "spike/release-runtime-qualification/v1",
                "status": "passed",
                "summary": {"total": 8, "passed": 8, "failed": 0},
                "source_snapshot_digest": "d" * 64,
                "packaged_snapshot_digest": "e" * 64,
            })
            check, _ = acceptance.verify_runtime_report(report)

        self.assertEqual(check["status"], "failed")

    def test_human_evidence_is_pending_without_input_and_rejects_tampered_artifact(self) -> None:
        pending, metadata = acceptance.validate_human_evidence(None)
        self.assertEqual(metadata["status"], "pending")
        self.assertEqual(len(pending), len(acceptance.REQUIRED_HUMAN_CHECKS))
        self.assertTrue(all(check["status"] == "failed" for check in pending))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.valid_human_evidence(root)
            checks, metadata = acceptance.validate_human_evidence(evidence)
            self.assertEqual(metadata["status"], "passed")
            self.assertTrue(all(check["status"] == "passed" for check in checks))
            (root / "review.txt").write_text("tampered", encoding="utf-8")
            (root / "pixel.png").write_bytes(b"tampered")
            checks, metadata = acceptance.validate_human_evidence(evidence)

        self.assertEqual(metadata["status"], "failed")
        self.assertTrue(all(check["status"] == "failed" for check in checks))

    def test_human_evidence_fails_closed_for_duplicate_or_incomplete_check_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.valid_human_evidence(root)
            payload = json.loads(evidence.read_text(encoding="utf-8"))
            payload["checks"][-1]["id"] = payload["checks"][0]["id"]
            evidence.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(acceptance.Wave1AcceptanceError, "incomplete or duplicated"):
                acceptance.validate_human_evidence(evidence)

    def test_signed_candidate_human_evidence_requires_exact_public_signature_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.valid_human_evidence(root)
            payload = json.loads(evidence.read_text(encoding="utf-8"))
            payload.update({
                "contract": "spike/wave1-human-acceptance-evidence/v2",
                "installer_file": "SPIKE_0.2.0_x64_en-US.msi",
                "installer_manifest_sha256": "d" * 64,
                "authenticode": {"signer_thumbprint": "A" * 40, "timestamp_protocol": "rfc3161", "timestamp_authority_thumbprint": "B" * 40},
            })
            evidence.write_text(json.dumps(payload), encoding="utf-8")
            _, metadata = acceptance.validate_human_evidence(evidence)
            self.assertEqual(metadata["contract"], "spike/wave1-human-acceptance-evidence/v2")
            payload["installer_file"] = "..\\SPIKE.msi"
            evidence.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(acceptance.Wave1AcceptanceError, "missing exact installer"):
                acceptance.validate_human_evidence(evidence)

    def test_human_evidence_rejects_non_isolated_or_mismatched_harness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.valid_human_evidence(root)
            harness = root / "harness-run.json"
            payload = json.loads(harness.read_text(encoding="utf-8"))
            payload["provider"] = "not-isolated"
            harness.write_text(json.dumps(payload), encoding="utf-8")
            human = json.loads(evidence.read_text(encoding="utf-8"))
            human["checks"][0]["artifacts"][-1]["sha256"] = _sha256(harness)
            evidence.write_text(json.dumps(human), encoding="utf-8")
            with self.assertRaisesRegex(acceptance.Wave1AcceptanceError, "not eligible"):
                acceptance.validate_human_evidence(evidence)
            payload["provider"] = "external-clean-vm"
            payload["after_manifest_payload_sha256"] = "d" * 64
            harness.write_text(json.dumps(payload), encoding="utf-8")
            human["checks"][0]["artifacts"][-1]["sha256"] = _sha256(harness)
            evidence.write_text(json.dumps(human), encoding="utf-8")
            with self.assertRaisesRegex(acceptance.Wave1AcceptanceError, "after_manifest_payload_sha256"):
                acceptance.validate_human_evidence(evidence)

    def test_human_evidence_rejects_attestation_summary_copy_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.valid_human_evidence(root)
            harness = root / "harness-run.json"
            payload = json.loads(harness.read_text(encoding="utf-8"))
            payload["environment_attestation"]["attestor"] = "Different reviewer"
            harness.write_text(json.dumps(payload), encoding="utf-8")
            human = json.loads(evidence.read_text(encoding="utf-8"))
            human["checks"][0]["artifacts"][-1]["sha256"] = _sha256(harness)
            evidence.write_text(json.dumps(human), encoding="utf-8")
            with self.assertRaisesRegex(acceptance.Wave1AcceptanceError, "not hash-bound"):
                acceptance.validate_human_evidence(evidence)

    def test_worker_health_requires_ready_json_response(self) -> None:
        class Completed:
            returncode = 0
            stdout = '{"ok": true, "result": {"status": "not-ready"}}'
            stderr = ""

        with tempfile.TemporaryDirectory() as directory, patch.object(acceptance.subprocess, "run", return_value=Completed()):
            root = Path(directory)
            executable = root / "spike-worker.exe"
            executable.write_bytes(b"")
            check, health = acceptance.probe_packaged_worker_health(executable, cwd=root)

        self.assertEqual(check["status"], "failed")
        self.assertEqual(health["status"], "not-ready")

    def test_packaged_fixture_probe_requires_source_models_and_selectors(self) -> None:
        class Completed:
            returncode = 0
            stderr = ""
            stdout = "\n".join(json.dumps(item) for item in [
                {"ok": True, "result": {"project": {"design": {"source_board": "(kicad_pcb)"}}}},
                {"ok": True, "result": {"artifacts": [{"model_id": "model"}]}},
                {"ok": True, "result": {"artifacts": [{"shape_id": "shape"}]}},
            ])

        with tempfile.TemporaryDirectory() as directory, patch.object(acceptance.subprocess, "run", return_value=Completed()):
            root = Path(directory)
            check = acceptance.probe_packaged_worker_fixture(
                root / "spike-worker.exe", cwd=root, fixture=root / "fixture.spike",
                manifest_payload_sha256="a" * 64, model_ids=["model"], shape_ids=["shape"],
            )
        self.assertEqual(check["status"], "passed")

    def test_packaged_mutation_probe_chains_manifests_and_preserves_world_pose(self) -> None:
        from python.spike_core.project_package import read_project
        from python.spike_core.service_project_mcad_placement import (
            reparent_mcad_part_in_project,
            update_mcad_part_in_project,
        )

        calls: list[str] = []

        def invoke(_executable: Path, *, cwd: Path, method: str, params: dict[str, object], timeout: int = 120) -> dict[str, object]:
            del cwd, timeout
            calls.append(method)
            if method == "update_mcad_part_in_project":
                return update_mcad_part_in_project(params, application_version="test")
            if method == "reparent_mcad_part_in_project":
                return reparent_mcad_part_in_project(params, application_version="test")
            opened = read_project(str(params["path"]))
            return {"canonical": opened.payload, "manifest": opened.manifest}

        fixture = ROOT / "artifacts" / "wave1-assembly-acceptance" / "wave1-assembly-acceptance.spike"
        with patch.object(mutation, "_invoke_worker_request", side_effect=invoke):
            check = acceptance.probe_packaged_worker_mutation_roundtrip(
                ROOT / "spike-worker.exe", cwd=ROOT, fixture=fixture,
            )

        self.assertEqual(check["status"], "passed", check)
        self.assertEqual(calls, ["update_mcad_part_in_project", "reparent_mcad_part_in_project", "read_project_package"])
        self.assertTrue(check["evidence"]["manifest_chain_verified"])
        self.assertTrue(check["evidence"]["world_pose_preserved"])
        self.assertTrue(check["evidence"]["artifacts_unchanged"])

    def test_packaged_mutation_probe_fails_closed_on_stale_manifest(self) -> None:
        fixture = ROOT / "artifacts" / "wave1-assembly-acceptance" / "wave1-assembly-acceptance.spike"
        with patch.object(
            mutation, "_invoke_worker_request",
            side_effect=mutation.Wave1MutationAcceptanceError("stale manifest identity"),
        ):
            check = acceptance.probe_packaged_worker_mutation_roundtrip(
                ROOT / "spike-worker.exe", cwd=ROOT, fixture=fixture,
            )
        self.assertEqual(check["status"], "failed")
        self.assertIn("stale manifest identity", check["evidence"]["error"])

    def test_composed_report_stays_pending_until_human_evidence_passes(self) -> None:
        automated = [{"id": "automated", "status": "passed", "detail": "ok", "evidence": {}}]
        human = [{"id": "install_launch", "status": "failed", "detail": "pending", "evidence": {}}]
        report = acceptance.compose_report(
            automated_checks=automated, human_checks=human, candidate={}, worker={}, fixture={},
            runtime={}, human={"status": "pending", "evidence": None},
        )
        self.assertEqual(report["status"], "pending_human")
        self.assertEqual(report["qualification"]["assembly_foundation"], "contract_tested")

    def test_composed_report_rejects_human_evidence_bound_to_another_candidate(self) -> None:
        report = acceptance.compose_report(
            automated_checks=[{"id": "automated", "status": "passed", "detail": "ok", "evidence": {}}],
            human_checks=[{"id": identifier, "status": "passed", "detail": "ok", "evidence": {}} for identifier in acceptance.REQUIRED_HUMAN_CHECKS],
            candidate={"artifacts": [{"sha256": "a" * 64}]}, worker={},
            fixture={"manifest_payload_sha256": "b" * 64}, runtime={},
            human={"status": "passed", "evidence": "human.json", "installer_sha256": "c" * 64, "before_manifest_payload_sha256": "b" * 64},
        )
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["human"]["summary"]["failed"], 1)

    def test_signed_candidate_report_requires_file_manifest_and_signature_identity(self) -> None:
        candidate = {
            "contract": "spike/windows-installer-manifest/v2", "manifest_sha256": "m" * 64,
            "artifacts": [{"file": "SPIKE.msi", "sha256": "a" * 64, "authenticode": {"signer_thumbprint": "A" * 40, "timestamp_protocol": "rfc3161", "timestamp_authority_thumbprint": "B" * 40}}],
        }
        human = {"status": "passed", "evidence": "human.json", "contract": "spike/wave1-human-acceptance-evidence/v2", "installer_file": "SPIKE.msi", "installer_sha256": "a" * 64, "installer_manifest_sha256": "m" * 64, "authenticode": {"signer_thumbprint": "A" * 40, "timestamp_protocol": "rfc3161", "timestamp_authority_thumbprint": "B" * 40}, "before_manifest_payload_sha256": "b" * 64}
        report = acceptance.compose_report(automated_checks=[{"id": "automated", "status": "passed", "detail": "ok", "evidence": {}}], human_checks=[{"id": identifier, "status": "passed", "detail": "ok", "evidence": {}} for identifier in acceptance.REQUIRED_HUMAN_CHECKS], candidate=candidate, worker={}, fixture={"manifest_payload_sha256": "b" * 64}, runtime={}, human=human)
        self.assertEqual(report["contract"], "spike/wave1-packaged-acceptance/v2")
        self.assertEqual(report["status"], "passed")
        human["authenticode"]["signer_thumbprint"] = "C" * 40
        rejected = acceptance.compose_report(automated_checks=[{"id": "automated", "status": "passed", "detail": "ok", "evidence": {}}], human_checks=[{"id": identifier, "status": "passed", "detail": "ok", "evidence": {}} for identifier in acceptance.REQUIRED_HUMAN_CHECKS], candidate=candidate, worker={}, fixture={"manifest_payload_sha256": "b" * 64}, runtime={}, human=human)
        self.assertEqual(rejected["status"], "failed")


if __name__ == "__main__":
    unittest.main()
