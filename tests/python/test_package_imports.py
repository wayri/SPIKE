# SPDX-License-Identifier: Apache-2.0
"""Public exports stay compatible without loading unrelated numerical engines."""
import subprocess
import sys
import unittest
from pathlib import Path


class PackageImportTests(unittest.TestCase):
    def run_fresh(self, source):
        result = subprocess.run([sys.executable, "-c", source],
                                cwd=Path(__file__).resolve().parents[2],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_contract_import_does_not_initialize_field_solver(self):
        self.run_fresh("""
import sys
import python.spike_core as core
from python.spike_core.contracts import AnalysisSpec
assert core.AnalysisSpec is AnalysisSpec
assert core.DesignIR is core.SpiDeR
assert core.DesignIRV2 is core.SpiDeRV2
assert set(core.__all__).issubset(dir(core))
assert 'python.spike_core.solvers.execution.coupling.field_circuit_cosim' not in sys.modules
assert 'python.spike_core.solvers.power_integrity.peec.peec_field_provider' not in sys.modules
assert 'scipy' not in sys.modules
""")

    def test_lazy_exports_keep_identity_and_star_import(self):
        self.run_fresh("""
import python.spike_core as core
from python.spike_core.solvers.execution.coupling.field_circuit_cosim import run_iterative_field_circuit_cosimulation
from python.spike_core.solvers.power_integrity.peec.peec_field_provider import NativePeecFieldReductionProvider
from python.spike_core.extensions import ExtensionManifest
assert core.run_iterative_field_circuit_cosimulation is run_iterative_field_circuit_cosimulation
assert core.NativePeecFieldReductionProvider is NativePeecFieldReductionProvider
assert core.ExtensionManifest is ExtensionManifest
scope = {}
exec('from python.spike_core import *', scope)
assert all(name in scope for name in core.__all__)
assert scope['run_iterative_field_circuit_cosimulation'] is run_iterative_field_circuit_cosimulation
try:
    core.nonexistent_public_export
except AttributeError:
    pass
else:
    raise AssertionError('unknown exports must raise AttributeError')
""")


if __name__ == "__main__":
    unittest.main()
