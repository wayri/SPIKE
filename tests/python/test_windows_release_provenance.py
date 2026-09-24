"""Fail-closed contracts for deterministic Windows release provenance."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"
SHA256 = "a" * 64


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_schema(name: str) -> dict[str, object]:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def component() -> dict[str, object]:
    return {
        "id": "python-jsonschema",
        "purl": "pkg:pypi/jsonschema@4.23.0",
        "name": "jsonschema",
        "version": "4.23.0",
        "ecosystem": "python",
        "license": "MIT",
        "scope": "bundled",
        "integrity": {"algorithm": "sha256", "value": SHA256},
        "notice": {"status": "included", "file": "THIRD_PARTY_NOTICES.md", "sha256": SHA256},
    }


def sbom() -> dict[str, object]:
    return {
        "contract": "spike/windows-release-sbom/v1",
        "product": "SPIKE",
        "version": "0.2.0",
        "application_version": "0.2.0-alpha.1",
        "channel": "production-candidate",
        "release_state": "production-candidate",
        "production_qualified": False,
        "components": [component()],
    }


def digest_file(name: str) -> dict[str, str]:
    return {"file": name, "sha256": SHA256}


def provenance() -> dict[str, object]:
    return {
        "contract": "spike/windows-release-provenance/v1",
        "product": "SPIKE",
        "version": "0.2.0",
        "application_version": "0.2.0-alpha.1",
        "channel": "production-candidate",
        "release_state": "production-candidate",
        "production_qualified": False,
        "installer_manifest": digest_file("SPIKE-0.2.0-production-candidate-installers.json"),
        "installers": {
            "msi": {"identity": "windows-msi", **digest_file("SPIKE_0.2.0_x64_en-US.msi")},
            "nsis": {"identity": "windows-nsis", **digest_file("SPIKE_0.2.0_x64-setup.exe")},
        },
        "inputs": [digest_file("dependencies.lock.json") | {"id": "dependencies_lock"}],
        "worker_manifest": digest_file("bundled/spike-worker.manifest.json"),
        "sbom": digest_file("SPIKE-0.2.0-production-candidate.sbom.json"),
        "notices": digest_file("THIRD_PARTY_NOTICES.md"),
    }


class WindowsReleaseProvenanceSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sbom_schema = load_schema("windows-release-sbom-v1.schema.json")
        cls.provenance_schema = load_schema("windows-release-provenance-v1.schema.json")
        Draft202012Validator.check_schema(cls.sbom_schema)
        Draft202012Validator.check_schema(cls.provenance_schema)
        cls.sbom_validator = Draft202012Validator(cls.sbom_schema)
        cls.provenance_validator = Draft202012Validator(cls.provenance_schema)

    def test_production_candidate_sbom_has_exact_component_provenance(self) -> None:
        self.sbom_validator.validate(sbom())

    def test_sbom_rejects_non_candidate_component_scope_and_unpinned_integrity(self) -> None:
        for mutate in (
            lambda payload: payload.__setitem__("production_qualified", True),
            lambda payload: payload["components"][0].__setitem__("scope", "runtime"),
            lambda payload: payload["components"][0]["integrity"].__setitem__("value", "unverified"),
            lambda payload: payload["components"][0].__setitem__("purl", "https://example.invalid/component"),
        ):
            with self.subTest(mutate=mutate):
                payload = copy.deepcopy(sbom())
                mutate(payload)
                self.assertFalse(self.sbom_validator.is_valid(payload))

    def test_sbom_accepts_explicit_sri_and_external_component_scope(self) -> None:
        payload = sbom()
        payload["components"][0]["scope"] = "external-not-distributed"
        payload["components"][0]["ecosystem"] = "external"
        payload["components"][0]["integrity"] = {"algorithm": "sha512-sri", "value": "sha512-YWJjZA=="}
        self.sbom_validator.validate(payload)

    def test_provenance_binds_exact_msi_nsis_and_required_digests(self) -> None:
        self.provenance_validator.validate(provenance())

    def test_provenance_rejects_identity_tampering_missing_digests_and_non_candidate_claims(self) -> None:
        mutations = (
            lambda payload: payload["installers"]["msi"].__setitem__("identity", "windows-nsis"),
            lambda payload: payload["installers"]["nsis"].__setitem__("file", "SPIKE.msi"),
            lambda payload: payload.pop("worker_manifest"),
            lambda payload: payload.__setitem__("production_qualified", True),
            lambda payload: payload["inputs"][0].__setitem__("file", "../dependencies.lock.json"),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                payload = copy.deepcopy(provenance())
                mutate(payload)
                self.assertFalse(self.provenance_validator.is_valid(payload))

    def test_release_builder_and_verifier_expose_fail_closed_public_apis(self) -> None:
        # The implementation is intentionally imported by path so these scripts remain usable as CLIs.
        import importlib.util

        build_spec = importlib.util.spec_from_file_location(
            "build_windows_release_provenance", ROOT / "scripts" / "build_windows_release_provenance.py"
        )
        verify_spec = importlib.util.spec_from_file_location(
            "verify_windows_release_provenance", ROOT / "scripts" / "verify_windows_release_provenance.py"
        )
        self.assertIsNotNone(build_spec)
        self.assertIsNotNone(verify_spec)
        self.assertIsNotNone(build_spec.loader)
        self.assertIsNotNone(verify_spec.loader)
        build_module = importlib.util.module_from_spec(build_spec)
        verify_module = importlib.util.module_from_spec(verify_spec)
        build_spec.loader.exec_module(build_module)
        verify_spec.loader.exec_module(verify_module)
        self.assertTrue(callable(getattr(build_module, "build_release_provenance", None)))
        self.assertTrue(callable(getattr(verify_module, "verify_release_provenance", None)))


class WindowsReleaseProvenanceImplementationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = load_script("build_windows_release_provenance")
        self.verifier = load_script("verify_windows_release_provenance")

    def _fixture(self, root: Path) -> tuple[Path, Path, Path, Path, Path, Path]:
        msi = root / "SPIKE_0.2.0_x64_en-US.msi"
        nsis = root / "SPIKE_0.2.0_x64-setup.exe"
        msi.write_bytes(b"signed-msi-fixture")
        nsis.write_bytes(b"signed-nsis-fixture")
        signature = {
            "status": "Valid", "file_digest_algorithm": "sha256",
            "signer_thumbprint": "A" * 40, "signer_subject": "CN=SPIKE Fixture",
            "timestamp_protocol": "rfc3161",
            "timestamp_authority_thumbprint": "B" * 40,
            "timestamp_authority_subject": "CN=Fixture TSA",
        }
        manifest = {
            "contract": "spike/windows-installer-manifest/v2", "product": "SPIKE",
            "version": "0.2.0", "application_version": "0.2.0-alpha.1",
            "channel": "production-candidate", "release_state": "production-candidate",
            "production_qualified": False,
            "generated_at": "2026-08-27T00:00:00Z",
            "signing_policy": {
                "required": True, "expected_signer_thumbprint": "A" * 40,
                "digest_algorithm": "sha256", "timestamp_required": True,
                "timestamp_protocol": "rfc3161",
            },
            "files": [
                {"file": msi.name, "kind": "msi", "size": msi.stat().st_size,
                 "sha256": sha256(msi), "authenticode": signature},
                {"file": nsis.name, "kind": "nsis", "size": nsis.stat().st_size,
                 "sha256": sha256(nsis), "authenticode": signature},
            ],
        }
        manifest_path = root / "SPIKE-0.2.0-production-candidate-installers.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        worker_root = root / "bundled" / "spike-worker"
        worker_root.mkdir(parents=True)
        worker_member = worker_root / "spike-worker.exe"
        worker_member.write_bytes(b"worker-fixture")
        worker_manifest = root / "bundled" / "spike-worker.manifest.json"
        worker_manifest.write_text(json.dumps({
            "contract": "spike/packaged-worker-manifest/v2",
            "files": [{"path": worker_member.name, "size": worker_member.stat().st_size,
                       "sha256": sha256(worker_member)}],
        }), encoding="utf-8")
        notices = root / "THIRD_PARTY_NOTICES.md"
        notices.write_text("# Approved notices\n\n## fixture-component\nMIT license text.\n", encoding="utf-8")
        dependencies = root / "dependencies.lock.json"
        dependencies.write_text(json.dumps({
            "manifest": "spike/dependencies/v1",
            "signature": {"required": True, "format": "cms-detached-sha256", "sidecar": "dependencies.lock.json.p7s"},
            "components": [{
                "id": "fixture-component", "name": "Fixture Component", "version": "1.2.3",
                "ecosystem": "python", "purl": "pkg:pypi/fixture-component@1.2.3",
                "license": "MIT", "scope": "bundled",
                "integrity": {"algorithm": "sha256", "value": "c" * 64},
                "notice": "fixture-component", "redistribution_approved": True,
            }],
        }), encoding="utf-8")
        signature = root / "dependencies.lock.json.p7s"
        signature.write_bytes(b"detached-cms-fixture")
        return manifest_path, worker_manifest, dependencies, notices, root / "sbom.json", root / "provenance.json"

    def _modern_review_fixture(self, root: Path) -> tuple[Path, ...]:
        """Add a digest-bound inventory and human-review overlay to the release fixture."""
        arguments = self._fixture(root)
        identity = "d" * 64
        inventory_path = root / "windows-component-inventory.json"
        inventory_path.write_text(json.dumps({
            "contract": "spike/windows-component-inventory/v1",
            "platform": "windows-x64", "production_qualified": False,
            "sources": [{"id": "python_runtime_lock", "sha256": "e" * 64}],
            "components": [{
                "purl": "pkg:pypi/fixture-component@1.2.3", "name": "fixture-component",
                "version": "1.2.3", "ecosystem": "python", "scope": "bundled",
                "integrity": {"algorithm": "sha256", "value": "c" * 64},
                "declared_license": "MIT",
                "license_evidence": {"kind": "wheel-metadata", "sha256": "f" * 64},
                "identity_sha256": identity,
            }],
        }), encoding="utf-8")
        approvals_path = root / "windows-component-approvals.json"
        approvals_path.write_text(json.dumps({
            "contract": "spike/windows-component-approvals/v1", "platform": "windows-x64",
            "inventory_sha256": sha256(inventory_path), "notices_sha256": sha256(arguments[3]),
            "approvals": [{
                "purl": "pkg:pypi/fixture-component@1.2.3", "identity_sha256": identity,
                "disposition": "approved", "approved_license_expression": "MIT",
                "compliance_approved": True, "redistribution_approved": True,
                "notice": {"status": "included", "file": arguments[3].name,
                           "sha256": sha256(arguments[3]), "marker": "fixture-component"},
                "review": {"ticket": "LEGAL-1", "reviewer": "Fixture Reviewer",
                           "reviewed_at": "2026-08-27T00:00:00Z"},
            }],
        }), encoding="utf-8")
        return (*arguments, inventory_path, approvals_path)

    @staticmethod
    def _refresh_provenance_input(provenance_path: Path, identifier: str, source: Path) -> None:
        payload = json.loads(provenance_path.read_text(encoding="utf-8"))
        next(item for item in payload["inputs"] if item["id"] == identifier)["sha256"] = sha256(source)
        if identifier == "third_party_notices":
            payload["notices"]["sha256"] = sha256(source)
        provenance_path.write_text(json.dumps(payload), encoding="utf-8")

    @staticmethod
    def _cms_probe(content: Path, signature: Path, thumbprint: str) -> dict[str, object]:
        return {
            "contract": "spike/detached-cms-metadata/v1", "status": "Valid",
            "detached": True, "digest_algorithm": "sha256",
            "signer_thumbprint": thumbprint,
            "signature_sha256": sha256(signature),
        }

    def test_builder_and_verifier_bind_all_candidate_bytes_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            arguments = self._fixture(root)
            first = self.builder.build_release_provenance(*arguments[:4], root, *arguments[4:], cms_probe=self._cms_probe)
            first_bytes = (arguments[4].read_bytes(), arguments[5].read_bytes())
            second = self.builder.build_release_provenance(*arguments[:4], root, *arguments[4:], cms_probe=self._cms_probe)
            self.assertEqual(first, second)
            self.assertEqual(first_bytes, (arguments[4].read_bytes(), arguments[5].read_bytes()))
            result = self.verifier.verify_release_provenance(arguments[5], arguments[4], root, cms_probe=self._cms_probe)
            self.assertEqual(result["status"], "passed")
            self.assertFalse(result["production_qualified"])

    def test_verifier_rejects_tampered_installer_and_worker_member(self) -> None:
        for target in ("installer", "worker"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                arguments = self._fixture(root)
                self.builder.build_release_provenance(*arguments[:4], root, *arguments[4:], cms_probe=self._cms_probe)
                path = root / "SPIKE_0.2.0_x64_en-US.msi" if target == "installer" else root / "bundled" / "spike-worker" / "spike-worker.exe"
                path.write_bytes(path.read_bytes() + b"tamper")
                with self.assertRaises(ValueError):
                    self.verifier.verify_release_provenance(arguments[5], arguments[4], root, cms_probe=self._cms_probe)

    def test_worker_inventory_can_be_replayed_without_copying_worker_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            arguments = self._fixture(root)
            worker = json.loads(arguments[1].read_text(encoding="utf-8"))
            staged = root / "evidence" / "bundled" / "spike-worker.manifest.json"
            staged.parent.mkdir(parents=True)
            staged.write_bytes(arguments[1].read_bytes())
            self.builder._verify_worker_inventory(
                worker, staged, root / "bundled" / "spike-worker",
            )
            (root / "bundled" / "spike-worker" / "spike-worker.exe").write_bytes(b"tampered")
            with self.assertRaises(self.builder.ReleaseProvenanceError):
                self.builder._verify_worker_inventory(
                    worker, staged, root / "bundled" / "spike-worker",
                )

    def test_builder_rejects_unapproved_or_mutably_versioned_component(self) -> None:
        for mutation in ("approval", "version"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                arguments = self._fixture(root)
                payload = json.loads(arguments[2].read_text(encoding="utf-8"))
                if mutation == "approval":
                    payload["components"][0].pop("redistribution_approved")
                else:
                    payload["components"][0]["version"] = ">=1.0"
                arguments[2].write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(self.builder.ReleaseProvenanceError):
                    self.builder.build_release_provenance(*arguments[:4], root, *arguments[4:], cms_probe=self._cms_probe)

    def test_modern_reviewed_inventory_builds_and_verifies_all_six_bound_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            arguments = self._modern_review_fixture(root)
            sbom, provenance = self.builder.build_release_provenance(
                *arguments[:4], root, *arguments[4:6], cms_probe=self._cms_probe,
                component_inventory_path=arguments[6], component_approvals_path=arguments[7],
                approval_evidence_root=root,
            )
            self.assertEqual({item["id"] for item in provenance["inputs"]}, {
                "dependencies_lock", "dependencies_signature", "worker_manifest", "third_party_notices",
                "component_inventory", "component_approvals",
            })
            self.assertEqual(sbom["components"][0]["purl"], "pkg:pypi/fixture-component@1.2.3")
            result = self.verifier.verify_release_provenance(arguments[5], arguments[4], root, cms_probe=self._cms_probe)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["component_count"], 1)

    def test_modern_reviewed_inputs_fail_closed_after_digest_rebound_tampering(self) -> None:
        for target in ("inventory", "approvals", "notices"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                arguments = self._modern_review_fixture(root)
                self.builder.build_release_provenance(
                    *arguments[:4], root, *arguments[4:6], cms_probe=self._cms_probe,
                    component_inventory_path=arguments[6], component_approvals_path=arguments[7],
                    approval_evidence_root=root,
                )
                if target == "inventory":
                    payload = json.loads(arguments[6].read_text(encoding="utf-8"))
                    payload["components"][0]["declared_license"] = "BSD-3-Clause"
                    arguments[6].write_text(json.dumps(payload), encoding="utf-8")
                    self._refresh_provenance_input(arguments[5], "component_inventory", arguments[6])
                elif target == "approvals":
                    payload = json.loads(arguments[7].read_text(encoding="utf-8"))
                    payload["approvals"][0]["disposition"] = "pending_review"
                    arguments[7].write_text(json.dumps(payload), encoding="utf-8")
                    self._refresh_provenance_input(arguments[5], "component_approvals", arguments[7])
                else:
                    arguments[3].write_text("# Approved notices\n\n## fixture-component\nChanged notice.\n", encoding="utf-8")
                    self._refresh_provenance_input(arguments[5], "third_party_notices", arguments[3])
                with self.assertRaises(ValueError):
                    self.verifier.verify_release_provenance(arguments[5], arguments[4], root, cms_probe=self._cms_probe)


class WindowsReleaseInputCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.checker = load_script("check_windows_release_inputs")

    def _fixture(self, root: Path) -> tuple[Path, ...]:
        notices = root / "notices.md"
        notices.write_text(
            "# Approved notices\n\n## left-pad\nMIT\n\n## serde\nMIT\n\n## numpy\nBSD-3-Clause\n",
            encoding="utf-8",
        )
        npm_integrity = "sha512-YWJjZA=="
        cargo_digest = "d" * 64
        build_digest = "e" * 64
        runtime_digest = "f" * 64
        package_lock = root / "package-lock.json"
        package_lock.write_text(json.dumps({
            "lockfileVersion": 3,
            "packages": {
                "": {"name": "fixture", "version": "1.0.0"},
                "node_modules/left-pad": {
                    "version": "1.3.0", "integrity": npm_integrity, "license": "MIT"
                },
            },
        }), encoding="utf-8")
        cargo_lock = root / "Cargo.lock"
        cargo_lock.write_text(
            'version = 4\n\n[[package]]\nname = "serde"\nversion = "1.0.228"\n'
            'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
            f'checksum = "{cargo_digest}"\n', encoding="utf-8",
        )
        build_lock = root / "requirements-build.txt"
        build_lock.write_text(f"PyInstaller==6.21.0 --hash=sha256:{build_digest}\n", encoding="utf-8")
        runtime_lock = root / "requirements-runtime.txt"
        runtime_lock.write_text(f"numpy==2.4.2 --hash=sha256:{runtime_digest}\n", encoding="utf-8")
        dependencies = root / "dependencies.lock.json"
        dependencies.write_text(json.dumps({
            "manifest": "spike/dependencies/v1",
            "components": [
                {"id": "npm-left-pad", "name": "left-pad", "version": "1.3.0",
                 "ecosystem": "npm", "purl": "pkg:npm/left-pad@1.3.0", "license": "MIT",
                 "scope": "bundled", "integrity": {"algorithm": "sha512-sri", "value": npm_integrity},
                 "notice": "left-pad", "redistribution_approved": True},
                {"id": "rust-serde", "name": "serde", "version": "1.0.228",
                 "ecosystem": "rust", "purl": "pkg:cargo/serde@1.0.228", "license": "MIT",
                 "scope": "bundled", "integrity": {"algorithm": "cargo-sha256", "value": cargo_digest},
                 "notice": "serde", "redistribution_approved": True},
                {"id": "python-pyinstaller", "name": "PyInstaller", "version": "6.21.0",
                 "ecosystem": "python", "purl": "pkg:pypi/pyinstaller@6.21.0", "license": "GPL-2.0",
                 "scope": "build-only", "integrity": {"algorithm": "sha256", "value": build_digest}},
                {"id": "python-numpy", "name": "numpy", "version": "2.4.2",
                 "ecosystem": "python", "purl": "pkg:pypi/numpy@2.4.2", "license": "BSD-3-Clause",
                 "scope": "bundled", "integrity": {"algorithm": "sha256", "value": runtime_digest},
                 "notice": "numpy", "redistribution_approved": True},
            ],
        }), encoding="utf-8")
        return dependencies, notices, package_lock, cargo_lock, build_lock, runtime_lock

    def test_release_input_check_requires_exact_lock_coverage_and_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self._fixture(Path(directory))
            report = self.checker.check_release_inputs(*paths)
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["components"], 4)
            payload = json.loads(paths[0].read_text(encoding="utf-8"))
            payload["components"][0]["integrity"]["value"] = "sha512-ZGVmZw=="
            paths[0].write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                self.checker.check_release_inputs(*paths)

    def test_repository_release_inputs_remain_honestly_blocked(self) -> None:
        with self.assertRaises(ValueError):
            self.checker.check_release_inputs(
                ROOT / "dependencies.lock.json", ROOT / "THIRD_PARTY_NOTICES.md",
                ROOT / "app" / "package-lock.json", ROOT / "app" / "src-tauri" / "Cargo.lock",
                ROOT / "requirements-build-windows-x64.txt", ROOT / "requirements-runtime-windows-x64.txt",
            )


if __name__ == "__main__":
    unittest.main()
