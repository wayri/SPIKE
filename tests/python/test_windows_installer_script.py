"""Regression guards for the Windows preview packaging boundary.

These source-contract checks supplement, not replace, native application launch
acceptance: Tauri interprets absolute Windows drive paths as frontend URLs.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
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

    def test_retained_frontend_is_bounded_preview_only_and_does_not_skip_tests(self):
        self.assertIn('[string]$FrontendSnapshot', self.script)
        self.assertIn('Retained frontend snapshots are preview-only', self.script)
        self.assertIn('strictly below this checkout', self.script)
        self.assertIn('Frontend snapshot reparse points are not allowed', self.script)
        self.assertIn('Copy-Item -LiteralPath $frontendSource', self.script)
        self.assertNotIn('$SkipTests = $true', self.script)

    def test_preview_frontend_build_is_isolated_before_vite_can_empty_output(self):
        self.assertIn('build\\frontend-builds\\', self.script)
        self.assertIn('[Guid]::NewGuid().ToString("N")', self.script)
        self.assertIn('"--outDir", $frontendBuildOutput', self.script)
        self.assertIn('$frontendSource = $frontendBuildOutput', self.script)

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

    def test_preview_can_select_nsis_without_weakening_msi_admission(self):
        self.assertIn('[ValidateSet("nsis", "msi")]', self.script)
        self.assertIn('[string[]]$Bundles = @("nsis", "msi")', self.script)
        self.assertIn('$bundleArgument = $bundleKinds -join', self.script)
        self.assertIn('@("--bundles", $bundleArgument)', self.script)
        self.assertIn('if ($msiRequested) {', self.script)
        self.assertIn('scripts/windows_msi_version.py', self.script)
        self.assertIn('Production packaging requires both NSIS and MSI installers', self.script)

    def test_selected_bundles_drive_artifact_collection_and_verification(self):
        self.assertIn('$expectedExtensions = @($bundleKinds | ForEach-Object', self.script)
        self.assertIn('$_.Extension.ToLowerInvariant() -in $expectedExtensions', self.script)
        self.assertIn('@($installers).Count -ne $expectedExtensions.Count', self.script)
        self.assertIn('$missingExtensions.Count -ne 0', self.script)

    @unittest.skipUnless(shutil.which("pwsh") or shutil.which("powershell"), "PowerShell required")
    def test_actual_collection_accepts_one_nsis_and_rejects_missing_or_duplicate(self):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        section = self.script[self.script.index('$bundleRoot ='):self.script.index('# Read-only MSI database')]
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            bundle = root / "app/src-tauri/target/release/bundle/nsis"
            bundle.mkdir(parents=True)
            for count in (0, 1, 2):
                if count:
                    (bundle / f"SPIKE_0.4.2-beta_x64-{count}.exe").write_bytes(b"fixture")
                escaped = str(root).replace("'", "''")
                command = f"""
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {{
$app = Join-Path '{escaped}' 'app'
$artifactRoot = Join-Path '{escaped}' 'artifacts'
$version = '0.4.2-beta'
$expectedExtensions = @('.exe')
$bundleArgument = 'nsis'
{section}
Write-Output "ACCEPTED_COUNT=$($installers.Count)"
}} catch {{ Write-Output $_.Exception.Message; exit 1 }}
"""
                result = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", command],
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0 if count == 1 else 1, result.stdout + result.stderr)
                if count == 1:
                    self.assertIn("ACCEPTED_COUNT=1", result.stdout)

    def test_nsis_preflight_still_validates_semver_and_config_coherence(self):
        generic_gate = self.script.index('$effectiveConfigVersion -ne $applicationVersion')
        semver_gate = self.script.index('$semanticVersionPattern =')
        msi_gate = self.script.index('if ($msiRequested) {', semver_gate)
        self.assertLess(generic_gate, msi_gate)
        self.assertLess(semver_gate, msi_gate)
        self.assertIn('Invalid numeric prerelease identifier', self.script)

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
