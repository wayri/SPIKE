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

    def test_packaged_builds_explicitly_embed_frontend(self):
        production = self.script[self.script.index('"run", "tauri", "build", "--", "--bundles"'):]
        production = production[:production.index(') $app')]
        self.assertIn('"--features", "custom-protocol"', production)
        preview = next(line for line in self.script.splitlines() if '$previewBuildArguments = ' in line)
        self.assertIn('"--features", "custom-protocol"', preview)

    def test_ci_embeds_frontend_and_requires_native_acceptance(self):
        ci = (ROOT / "scripts/build_windows_ci.ps1").read_text(encoding="utf-8-sig")
        command = next(line for line in ci.splitlines() if '"run", "tauri", "build"' in line)
        self.assertIn('"--features", "custom-protocol"', command)
        self.assertIn('"scripts/verify_windows_desktop.py"', ci)
        self.assertNotIn('Start-Sleep -Seconds 10', ci)

    def test_worker_builds_produce_native_airflow_and_circuit_package_first(self):
        ci = (ROOT / "scripts/build_windows_ci.ps1").read_text(encoding="utf-8-sig")
        for script in (self.script, ci):
            airflow = script.index('"scripts/build_native_airflow.py"')
            circuit = script.index('"scripts/build_packaged_circuit_worker.py"')
            worker = script.index('"scripts/build_packaged_worker.py"')
            self.assertLess(airflow, circuit)
            self.assertLess(circuit, worker)
            self.assertIn('"--build-dir", "build-native-airflow"', script)
            self.assertIn('"--generator", "Ninja"', script)

    def test_ci_pins_the_release_python_baseline(self):
        workflow = (ROOT / ".github/workflows/windows-release.yml").read_text(encoding="utf-8")
        self.assertIn("python-version: '3.12'", workflow)
        self.assertIn('run: ./scripts/build_windows_ci.ps1', workflow)

    def test_native_ui_build_does_not_generate_installers(self):
        self.assertIn('[switch]$BuildOnly', self.script)
        self.assertIn('$previewBuildArguments += "--no-bundle"', self.script)
        self.assertLess(self.script.index('No installer was generated.'), self.script.index('$bundleRoot ='))
        self.assertIn('BuildOnly is for preview native-UI verification', self.script)

    def test_competing_build_is_rejected_and_mutex_is_released(self):
        self.assertIn('$buildMutex.WaitOne(0)', self.script)
        self.assertIn('Another SPIKE installer build owns this checkout', self.script)
        self.assertIn('catch [System.Threading.AbandonedMutexException]', self.script)
        # Configuration restoration may precede mutex release in the cleanup
        # block. Both must remain in finally, with disposal after release.
        cleanup = self.script[self.script.rindex('\nfinally {'):]
        self.assertIn('if ($ownsBuildMutex) { $buildMutex.ReleaseMutex() }', cleanup)
        self.assertLess(cleanup.index('$buildMutex.ReleaseMutex()'), cleanup.index('$buildMutex.Dispose()'))


if __name__ == "__main__":
    unittest.main()
