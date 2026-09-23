# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
from __future__ import annotations

import importlib.util
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_solver_qualification_environment.py"
SPEC = importlib.util.spec_from_file_location("qualification_preflight", SCRIPT)
preflight = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(preflight)


class QualificationEnvironmentPreflightTests(unittest.TestCase):
    def test_complete_inventory_passes_without_numerical_promotion(self):
        report = preflight.collect_preflight(self._imports())
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(len(report['native']['sha256']), 64)
        self.assertIn('not numerical qualification', report['scope'])

    def test_missing_native_module_fails(self):
        report = preflight.collect_preflight(self._imports(missing=preflight.NATIVE_MODULE))
        self.assertEqual(report['status'], 'failed')
        self.assertIsNone(report['native']['sha256'])

    def _imports(self, missing: str | None = None, native_apis: tuple[str, ...] | None = None):
        artifact = tempfile.NamedTemporaryFile(delete=False)
        self.addCleanup(lambda: Path(artifact.name).unlink(missing_ok=True))
        artifact.write(b"mock-native-extension")
        artifact.close()
        apis = native_apis if native_apis is not None else preflight.REQUIRED_NATIVE_APIS
        modules = {
            name: types.SimpleNamespace(__version__="test-version")
            for name in preflight.DEPENDENCIES
        }
        modules[preflight.NATIVE_MODULE] = types.SimpleNamespace(
            __file__=artifact.name, **{name: object() for name in apis}
        )

        def import_module(name: str):
            if name == missing:
                raise ModuleNotFoundError(name)
            return modules[name]

        return import_module

    def test_missing_dependency_fails_and_is_reported(self):
        report = preflight.collect_preflight(self._imports(missing="pyarrow"))
        self.assertEqual(report["status"], "failed")
        self.assertIsNone(report["dependencies"]["pyarrow"]["version"])
        self.assertIn("ModuleNotFoundError", report["dependencies"]["pyarrow"]["error"])

    def test_missing_native_api_fails_and_is_reported(self):
        available = tuple(api for api in preflight.REQUIRED_NATIVE_APIS if api != "PlanarPoint2")
        report = preflight.collect_preflight(self._imports(native_apis=available))
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["native"]["apis"]["PlanarPoint2"])
        self.assertIsNotNone(report["native"]["sha256"])


if __name__ == "__main__":
    unittest.main()
