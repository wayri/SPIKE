# SPDX-License-Identifier: Apache-2.0
"""Platform-specific dependency evidence admission without building binaries."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_packaged_circuit_worker as builder


def report(platform="linux", system="Linux", machine="x86_64"):
    return {"version": "1", "pip_version": "25.0", "environment": {
        "sys_platform": platform, "platform_system": system, "platform_machine": machine,
        "python_full_version": "3.12.9"}, "install": [{
            "metadata": {"name": "pyinstaller", "version": "6.21.0"},
            "download_info": {"url": "https://example.invalid/original-fixture.whl"}}]}


def platform_context(platform="linux", system="Linux", machine="x86_64"):
    stack = ExitStack()
    stack.enter_context(patch.object(builder.sys, "platform", platform))
    for key, value in (("system", system), ("machine", machine), ("python_version", "3.12.9")):
        stack.enter_context(patch.object(builder.platform, key, return_value=value))
    return stack


class CircuitWorkerDependencyProvenanceTests(unittest.TestCase):
    def test_linux_and_macos_bind_actual_report_without_windows_lock_claim(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "python-install.json"
            for platform, system, machine in (("linux", "Linux", "x86_64"),
                                              ("darwin", "Darwin", "arm64"),
                                              ("darwin", "Darwin", "x86_64")):
                raw = report(platform, system, machine)
                path.write_text(json.dumps(raw), encoding="utf-8")
                with self.subTest(platform=platform, machine=machine), platform_context(platform, system, machine):
                    result = builder._dependency_provenance(path)
                self.assertEqual(set(result), {"dependency_provenance"})
                evidence = result["dependency_provenance"]
                self.assertEqual(evidence["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
                self.assertEqual(evidence["environment"], raw["environment"])
                self.assertEqual(evidence["report"], path.name)
                self.assertNotIn(str(path.parent), json.dumps(result))

    def test_windows_preserves_existing_lock_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / "requirements-build-circuit-windows-x64.txt"
            lock.write_bytes(b"original lock fixture")
            with platform_context("win32", "Windows", "AMD64"), patch.object(builder, "BUILD_LOCK", lock):
                self.assertEqual(builder._dependency_provenance(None), {
                    "build_lock": lock.name, "build_lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest()})
                with self.assertRaisesRegex(ValueError, "Windows build lock"):
                    builder._dependency_provenance(lock)

    def test_missing_invalid_and_wrong_platform_reports_fail_before_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "python-install.json"
            invalid = [[], {}, {**report(), "version": "2"}, {**report(), "install": [None]}]
            mismatch = deepcopy(report())
            mismatch["environment"]["platform_machine"] = "other"
            invalid.append(mismatch)
            with platform_context():
                with self.assertRaises(ValueError):
                    builder._dependency_provenance(path)
                for raw in invalid:
                    path.write_text(json.dumps(raw), encoding="utf-8")
                    with self.subTest(raw=raw), self.assertRaises(ValueError):
                        builder._dependency_provenance(path)
                for text in ('{"version":"1","version":"1"}', '{"number":NaN}', 'invalid-json'):
                    path.write_text(text, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        builder._dependency_provenance(path)
                with patch.object(builder, "_require_builder", return_value="6.21.0"), patch.object(
                        builder, "_library") as library, patch.object(builder, "_remove_managed") as remove:
                    with self.assertRaisesRegex(ValueError, "--dependency-report"):
                        builder.build()
                    library.assert_not_called()
                    remove.assert_not_called()

    def test_dependency_drift_rejects_manifest_after_mocked_freeze(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            resources, work = root / "resources", root / "work"
            library = root / "library"
            library.write_bytes(b"native library fixture")
            def freeze(*args, **kwargs):
                artifact = resources / "spike-circuit-worker"
                artifact.mkdir()
                (artifact / ("spike-circuit-worker.exe" if os.name == "nt" else "spike-circuit-worker")).write_bytes(b"worker")
            with patch.object(builder, "RESOURCE_ROOT", resources), patch.object(builder, "BUILD_ROOT", work), \
                    patch.object(builder, "_library", return_value=library), \
                    patch.object(builder, "_require_builder", return_value="6.21.0"), \
                    patch.object(builder, "_dependency_provenance", side_effect=[{"sha256": "a"}, {"sha256": "b"}]), \
                    patch.object(builder.subprocess, "run", side_effect=freeze), \
                    patch.object(builder, "_smoke", return_value={}):
                with self.assertRaisesRegex(RuntimeError, "changed during"):
                    builder.build(keep_work=True)
            self.assertFalse((resources / "spike-circuit-worker.manifest.json").exists())

    def test_unix_script_passes_the_install_transaction_report(self):
        source = (builder.ROOT / "scripts/build_unix_release.sh").read_text(encoding="utf-8")
        self.assertIn("pip install --report build/qualification/python-install.json", source)
        self.assertIn("build_packaged_circuit_worker.py --dependency-report build/qualification/python-install.json", source)


if __name__ == "__main__":
    unittest.main()
