"""Fail-closed tests for Windows production-candidate signing helpers."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
HELPERS = ROOT / "scripts" / "windows_authenticode.ps1"
CMS_HELPERS = ROOT / "scripts" / "windows_cms.ps1"
BUILD = ROOT / "scripts" / "build_windows_installer.ps1"
PRODUCTION_CONFIG = ROOT / "app" / "src-tauri" / "tauri.production.conf.json"


def run_powershell(expression: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", f". '{HELPERS}'; {expression}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


class WindowsSigningContractTests(unittest.TestCase):
    def test_production_build_fails_before_build_when_release_inputs_are_absent(self) -> None:
        environment = {
            "SystemRoot": r"C:\Windows",
            "TEMP": str(ROOT / "build"),
            "TMP": str(ROOT / "build"),
        }
        completed = subprocess.run(
            [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(BUILD),
             "-Channel", "Production", "-SkipTests", "-SkipWorker"],
            cwd=ROOT, text=True, capture_output=True, check=False, env=environment,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Production packaging is blocked", completed.stderr)

    def test_thumbprint_normalization_is_exact(self) -> None:
        completed = run_powershell("Normalize-SpikeSigningThumbprint 'aa aa aa aa aa aa aa aa aa aa aa aa aa aa aa aa aa aa aa aa'")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "A" * 40)
        rejected = run_powershell("Normalize-SpikeSigningThumbprint 'abc'")
        self.assertNotEqual(rejected.returncode, 0)

    def test_timestamp_policy_rejects_non_https_paths_and_unapproved_hosts(self) -> None:
        for value in ("http://timestamp.digicert.com", "https://timestamp.digicert.com/path", "https://evil.example"):
            with self.subTest(value=value):
                completed = run_powershell(f"Assert-SpikeTimestampUri '{value}' @('timestamp.digicert.com')")
                self.assertNotEqual(completed.returncode, 0)
        accepted = run_powershell("(Assert-SpikeTimestampUri 'https://timestamp.digicert.com' @('timestamp.digicert.com')).DnsSafeHost")
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertEqual(accepted.stdout.strip(), "timestamp.digicert.com")

    def test_signtool_resolution_rejects_wrong_or_missing_explicit_path(self) -> None:
        completed = run_powershell(f"Resolve-SpikeSignTool '{HELPERS}'")
        self.assertNotEqual(completed.returncode, 0)
        missing = run_powershell("Resolve-SpikeSignTool 'Z:\\missing\\signtool.exe'")
        self.assertNotEqual(missing.returncode, 0)

    def test_policy_and_build_keep_candidate_distinct_from_qualification(self) -> None:
        policy = json.loads((ROOT / "config" / "windows-signing-policy.json").read_text(encoding="utf-8"))
        self.assertEqual(policy["schema"], "spike/windows-signing-policy/v1")
        self.assertEqual(policy["digest_algorithm"], "sha256")
        self.assertEqual(policy["timestamp_protocol"], "rfc3161")
        script = BUILD.read_text(encoding="utf-8")
        self.assertIn('contract = "spike/windows-installer-manifest/v2"', script)
        self.assertIn('release_state = "production-candidate"', script)
        self.assertIn('production_qualified = $false', script)
        self.assertIn("Invoke-SpikeAuthenticodeSigning", script)
        self.assertIn("Get-SpikeAuthenticodeMetadata", script)
        self.assertIn("scripts/check_windows_release_inputs.py", script)
        self.assertIn("SPIKE_WINDOWS_BUILD_WHEELHOUSE", script)
        self.assertIn("SPIKE_WINDOWS_RUNTIME_WHEELHOUSE", script)
        self.assertIn("New-SpikeDetachedCmsSignature", script)
        self.assertIn("scripts/stage_windows_release_evidence.py", script)
        self.assertIn("tauri.production.conf.json", script)
        self.assertIn("scripts/build_windows_release_provenance.py", script)
        self.assertIn("scripts/verify_windows_release_provenance.py", script)
        self.assertNotIn("SPIKE_SIGNING_PASSWORD", script)

    def test_production_tauri_config_embeds_reviewed_release_inputs(self) -> None:
        config = json.loads(PRODUCTION_CONFIG.read_text(encoding="utf-8"))
        resources = config["bundle"]["resources"]
        self.assertEqual(
            resources["../../artifacts/windows/production-candidate/dependencies.lock.json.p7s"],
            "dependencies.lock.json.p7s",
        )
        self.assertIn("../../config/windows-component-inventory.json", resources)
        self.assertIn("../../licenses/windows-component-approvals.json", resources)
        self.assertIn("../../requirements-runtime-windows-x64.txt", resources)
        self.assertEqual(
            config["bundle"]["licenseFile"],
            "../../licenses/SPIKE-COMMERCIAL-EULA-DRAFT.md",
        )

    def test_dependency_cms_helper_is_detached_sha256_and_fails_closed(self) -> None:
        script = CMS_HELPERS.read_text(encoding="utf-8")
        self.assertIn("New-SpikeDetachedCmsSignature", script)
        self.assertIn("Get-SpikeDetachedCmsMetadata", script)
        self.assertIn("2.16.840.1.101.3.4.2.1", script)
        completed = subprocess.run(
            [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-Command", f". '{CMS_HELPERS}'; Get-SpikeDetachedCmsMetadata 'missing.json' 'missing.p7s' '{'A' * 40}'"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("requires both content and signature", completed.stderr)


if __name__ == "__main__":
    unittest.main()
