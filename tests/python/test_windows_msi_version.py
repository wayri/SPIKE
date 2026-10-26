# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.windows_msi_version import validate_wix_override, stable_msi_core, validate_product_version

ROOT = Path(__file__).resolve().parents[2]


class WindowsMsiVersionTests(unittest.TestCase):
    def test_stable_default_and_exact_override(self):
        validate_wix_override("0.4.1", None)
        validate_wix_override("0.4.1", "0.4.1")
        self.assertEqual(stable_msi_core("0.4.1"), (0, 4, 1))
        for actual in ("0.4.1", "0.4.1.0"):
            validate_product_version("0.4.1", actual)

    def test_stale_malformed_and_fourth_component_overrides_reject(self):
        for override in ("0.3.12.1", "0.3.12", "0.4.1.0", "0.4.1.1", "00.4.1", "", 41, True):
            with self.subTest(override=override), self.assertRaises(ValueError):
                validate_wix_override("0.4.1", override)

    def test_internal_version_not_filename_is_authoritative(self):
        for actual in ("0.3.12.1", "0.3.12", "0.4.1.1", "0.4.2", "0.4", " 0.4.1", None):
            with self.subTest(actual=actual), self.assertRaises(ValueError):
                validate_product_version("0.4.1", actual)

    def test_prerelease_is_not_silently_promoted_or_ordered_by_fourth_field(self):
        validate_wix_override("0.4.1-alpha.1", None)
        with self.assertRaises(ValueError):
            validate_wix_override("0.4.1-alpha.1", "0.4.1")
        with self.assertRaises(ValueError):
            stable_msi_core("0.4.1-alpha.1")
        with self.assertRaises(ValueError):
            validate_product_version("0.4.1-alpha.1", "0.4.1.1")
        for version in ("0.4.1-alpha.01", "0.4.1-", "256.0.0", "0.256.0", "0.0.65536"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                stable_msi_core(version)

    def test_readonly_postbuild_admission_precedes_signing_and_copy(self):
        script = (ROOT / "scripts/build_windows_installer.ps1").read_text(encoding="utf-8-sig")
        query = script.index('$msiDatabase = $msiInstaller.OpenDatabase($msiPath, 0)')
        gate = script.index('"--product-version", $msiProductVersion')
        self.assertLess(query, gate)
        self.assertLess(gate, script.index('Invoke-SpikeAuthenticodeSigning $signToolPath $installer.FullName'))
        self.assertLess(gate, script.index('Copy-Item -LiteralPath $installer.FullName'))
        self.assertLess(script.index('$effectiveVersionConfig ='), script.index('if (-not $SkipWorker)'))

    def test_cli_checks_actual_effective_config_and_product_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "tauri.json"
            config.write_text(json.dumps({"version": "0.4.1"}), encoding="utf-8")
            command = [sys.executable, str(ROOT / "scripts/windows_msi_version.py"),
                       "--config", str(config), "--application", "0.4.1"]
            for actual, accepted in (("0.4.1.0", True), ("0.3.12.1", False)):
                result = subprocess.run(command + ["--product-version", actual],
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode == 0, accepted, result.stderr)
            config.write_text(json.dumps({"version": "0.4.0"}), encoding="utf-8")
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Effective Tauri version differs", result.stderr)

    def test_release_version_preflight_invokes_wix_admission(self):
        from scripts.release_automation import version
        with patch("scripts.windows_msi_version.validate_wix_override") as admission:
            expected = json.loads((ROOT / "app/package.json").read_text())["version"]
            self.assertEqual(version(ROOT), expected)
            admission.assert_called_once_with(expected, None)


if __name__ == "__main__":
    unittest.main()
