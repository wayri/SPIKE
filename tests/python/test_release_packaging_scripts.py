"""Source-contract checks for cross-platform release packaging order."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ReleasePackagingScriptTests(unittest.TestCase):
    def test_unix_builds_required_native_helpers_before_frozen_worker(self):
        script = (ROOT / "scripts/build_unix_release.sh").read_text(encoding="utf-8")
        airflow = script.index("python scripts/build_native_airflow.py --build-dir build-native-airflow --generator Ninja")
        circuit = script.index("python scripts/build_packaged_circuit_worker.py")
        worker = script.index("python scripts/build_packaged_worker.py")
        self.assertLess(airflow, circuit)
        self.assertLess(circuit, worker)

    def test_windows_uses_cargo_desktop_identity_in_install_root(self):
        script = (ROOT / "scripts/build_windows_ci.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("$defaultRunMatch", script)
        self.assertIn('Join-Path $installRoot ($defaultRunMatch.Groups[1].Value + ".exe")', script)
        self.assertIn('Test-Path -LiteralPath $desktopExecutable -PathType Leaf', script)
        self.assertIn('"scripts/verify_windows_desktop.py", $desktopExecutable', script)
        self.assertNotIn("$desktopCandidates", script)


if __name__ == "__main__":
    unittest.main()
