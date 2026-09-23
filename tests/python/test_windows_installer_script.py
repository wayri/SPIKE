"""Regression guards for the Windows preview packaging boundary.

These source-contract checks supplement, not replace, native application launch
acceptance: Tauri interprets absolute Windows drive paths as frontend URLs.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class WindowsInstallerScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = (ROOT / "scripts/build_windows_installer.ps1").read_text(encoding="utf-8-sig")

    def test_frontend_snapshot_is_a_relative_path_not_a_drive_url(self):
        self.assertIn('$snapshotRelativePath = "../../build/frontend-snapshots/', self.script)
        self.assertIn('frontendDist = $snapshotRelativePath', self.script)
        self.assertNotIn('frontendDist = $frontendSnapshot }', self.script)

    def test_native_ui_build_does_not_generate_installers(self):
        self.assertIn('[switch]$BuildOnly', self.script)
        self.assertIn('$previewBuildArguments += "--no-bundle"', self.script)
        self.assertLess(self.script.index('No installer was generated.'), self.script.index('$bundleRoot ='))
        self.assertIn('BuildOnly is for preview native-UI verification', self.script)

    def test_competing_build_is_rejected_and_mutex_is_released(self):
        self.assertIn('$buildMutex.WaitOne(0)', self.script)
        self.assertIn('Another SPIKE installer build owns this checkout', self.script)
        self.assertIn('catch [System.Threading.AbandonedMutexException]', self.script)
        self.assertIn('finally {\n    if ($ownsBuildMutex) { $buildMutex.ReleaseMutex() }', self.script)


if __name__ == "__main__":
    unittest.main()
