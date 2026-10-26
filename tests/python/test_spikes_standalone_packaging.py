# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.build_spikes_standalone_project import (
    ROOT, STANDALONE_EXCLUDED_TESTS, STANDALONE_SPIKE_CORE_MODULES,
    copy_standalone_python_boundary, copy_tree,
)


class SpikesStandalonePackagingTests(unittest.TestCase):
    def make_boundary(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        fixture_root = ROOT / "build" / "standalone-boundary-tests"
        fixture_root.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="boundary-", dir=fixture_root)
        package = Path(temporary.name) / "export"
        copy_tree(ROOT / "standalone/spikes_project/python", package / "python")
        copy_tree(ROOT / "python/spikes", package / "python/spikes")
        (package / "python").mkdir(parents=True, exist_ok=True)
        (package / "python/__init__.py").write_bytes((ROOT / "python/__init__.py").read_bytes())
        copy_standalone_python_boundary(package)
        return temporary, package

    def test_explicit_closure_uses_canonical_layout(self):
        self.assertIn(
            "python/spike_core/solvers/circuits/models/native_source_waveforms.py",
            STANDALONE_SPIKE_CORE_MODULES,
        )
        self.assertIn(
            "python/spike_core/solvers/execution/resources/gpu_acceleration.py",
            STANDALONE_SPIKE_CORE_MODULES,
        )
        self.assertNotIn("python/spike_core/service.py", STANDALONE_SPIKE_CORE_MODULES)
        self.assertIn("test_spikes_standalone_packaging.py", STANDALONE_EXCLUDED_TESTS)
        for relative in STANDALONE_SPIKE_CORE_MODULES:
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_relocated_boundary_imports_and_solves_without_repository_fallback(self):
        temporary, package = self.make_boundary()
        self.addCleanup(temporary.cleanup)
        probe = r'''import json
from python.spike_core.solvers.circuits.models.native_mna import run_native_mna
from python.spike_core.native_mna import run_native_mna as compatibility_run
from python.spike_core.solvers.external_engines.circuits.ngspice_plugin import NgspicePlugin
from python.spike_core.spikes_runtime import ENGINE_CONTRACT
request={"contract":"spike/native-mna-request/v1","request_id":"relocated","ground_node":"0","analysis":{"mode":"operating_point"},"elements":[{"id":"V1","type":"voltage_source","positive_node":"n","negative_node":"0","dc_value":1.0},{"id":"R1","type":"resistor","positive_node":"n","negative_node":"0","resistance_ohm":1000.0}]}
result=run_native_mna(request)
print(json.dumps({"same":run_native_mna is compatibility_run,"voltage":result["data"]["node_voltage_v"]["n"],"plugin":NgspicePlugin.__name__,"runtime_contract":ENGINE_CONTRACT}))
'''
        bootstrap = f"import sys;sys.path.insert(0,{str(package)!r});" + probe
        process = subprocess.run(
            [sys.executable, "-I", "-c", bootstrap], cwd=package.parent,
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertTrue(result["same"])
        self.assertAlmostEqual(result["voltage"], 1.0, places=12)
        self.assertEqual(result["plugin"], "NgspicePlugin")
        self.assertEqual(result["runtime_contract"], "spikes/owned-engine-status/v1")

    def test_native_tree_matches_standalone_cmake_layout(self):
        fixture_root = ROOT / "build" / "standalone-boundary-tests"
        fixture_root.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(
            prefix="native-", dir=fixture_root,
        )
        self.addCleanup(temporary.cleanup)
        package = Path(temporary.name) / "export"
        copy_tree(
            ROOT / "src/solvers/circuits/spikes",
            package / "engine/src/solvers/circuits/spikes",
        )
        expected = package / "engine/src/solvers/circuits/spikes/dc_solver.cpp"
        self.assertTrue(expected.is_file())
        cmake = (ROOT / "standalone/spikes_project/CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("engine/src/solvers/circuits/spikes", cmake)


if __name__ == "__main__":
    unittest.main()
