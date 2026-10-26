# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import ast
import json
from pathlib import Path
import tempfile
import unittest

from scripts.verify_solver_layout import LayoutError, load_manifest, validate_layout


ROOT = Path(__file__).resolve().parents[2]


def write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class SolverLayoutVerifierTests(unittest.TestCase):
    def test_refinement_child_source_inventory_resolves_before_launch(self):
        from scripts.benchmark_board_volume_scaling import METHODS

        self.assertGreater(len(METHODS), 1)
        self.assertEqual(len(METHODS), len(set(METHODS)))
        for source in METHODS:
            with self.subTest(source=source):
                self.assertTrue((ROOT / source).is_file())

    def fixture(self, *, source: str = "VALUE = 1\n") -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        fixture_root = ROOT / "build" / "solver-layout-tests"
        fixture_root.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="layout-", dir=fixture_root)
        root = Path(temporary.name)
        for package in (
            "python", "python/spike_core", "python/spike_core/solvers",
            "python/spike_core/solvers/example",
        ):
            write(root / package / "__init__.py")
        write(root / "python/spike_core/solvers/example/moved.py", source)
        write(root / "src/solvers/example/native.cpp", "// moved\n")
        manifest = root / "layout.json"
        manifest.write_text(json.dumps({
            "contract": "spike/solver-source-layout/v1",
            "python_modules": {
                "python/spike_core/moved.py": "python/spike_core/solvers/example/moved.py",
            },
            "native_files": {
                "src/legacy/native.cpp": "src/solvers/example/native.cpp",
            },
        }), encoding="utf-8")
        return temporary, root, manifest

    def test_valid_layout_passes_without_importing_destination(self):
        temporary, root, manifest = self.fixture(source="raise AssertionError('must not import')\n")
        self.addCleanup(temporary.cleanup)
        report = validate_layout(root, manifest)
        self.assertEqual(report["status"], "passed", report["errors"])

    def test_malformed_mapping_and_duplicate_destination_reject(self):
        temporary, root, manifest = self.fixture()
        self.addCleanup(temporary.cleanup)
        manifest.write_text(json.dumps({
            "contract": "spike/solver-source-layout/v1",
            "python_modules": {"../escape.py": "python/spike_core/solvers/example/moved.py"},
            "native_files": {"src/a.cpp": "python/spike_core/solvers/example/moved.py"},
        }), encoding="utf-8")
        with self.assertRaises(LayoutError):
            load_manifest(manifest)

    def test_missing_destination_and_old_source_reject(self):
        temporary, root, manifest = self.fixture()
        self.addCleanup(temporary.cleanup)
        (root / "python/spike_core/solvers/example/moved.py").unlink()
        write(root / "python/spike_core/moved.py")
        report = validate_layout(root, manifest)
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any("still exists" in error for error in report["errors"]))
        self.assertTrue(any("destination is missing" in error for error in report["errors"]))

    def test_stale_import_and_mock_target_strings_reject(self):
        temporary, root, manifest = self.fixture()
        self.addCleanup(temporary.cleanup)
        write(root / "scripts/consumer.py", "from python.spike_core import moved\n")
        write(root / "app/src/frontend.ts", 'const target = "python.spike_core.moved.run";\n')
        report = validate_layout(root, manifest)
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any("stale flat from-import" in error for error in report["errors"]))
        self.assertTrue(any("frontend.ts" in error for error in report["errors"]))
        write(root / "scripts/short_consumer.py", "from spike_core.moved import run\n")
        report = validate_layout(root, manifest)
        self.assertTrue(any("short_consumer.py" in error for error in report["errors"]))

    def test_solver_source_paths_resolve_cross_group_canonical_files(self):
        from python.spike_core.solver_source_paths import solver_source_path

        magnetic = solver_source_path("magnetic_fem.py")
        cfd = solver_source_path("cfd_tetra_mesh.py")
        self.assertEqual(
            magnetic.resolve(),
            (ROOT / "python/spike_core/solvers/electromagnetics/machines/magnetic_fem.py").resolve(),
        )
        self.assertEqual(
            cfd.resolve(),
            (ROOT / "python/spike_core/solvers/thermal_fluid/flow/cfd_tetra_mesh.py").resolve(),
        )
        self.assertTrue(magnetic.is_file())
        self.assertTrue(cfd.is_file())

        helper = ROOT / "python/spike_core/solver_source_paths.py"
        tree = ast.parse(helper.read_text(encoding="utf-8"), filename=str(helper))
        imports = {
            alias.name
            for node in ast.walk(tree) if isinstance(node, ast.Import)
            for alias in node.names
        }
        from_imports = {
            node.module for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module
        }
        self.assertEqual(imports | from_imports, {"pathlib"})


if __name__ == "__main__":
    unittest.main()
