# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from python.spike_core.beta_runtime_readiness import (
    BetaReadinessError,
    build_readiness_report,
    inspect_circuit_package,
)


ROOT = Path(__file__).resolve().parents[2]


class BetaRuntimeReadinessTests(unittest.TestCase):
    def test_checkout_report_preserves_truthful_beta_states(self) -> None:
        with patch(
            "python.spike_core.beta_runtime_readiness.probe_runtime_capabilities",
            return_value={
                "status": "not_found", "product_physics_eligible": False,
                "reason": "test fixture has no native runtime",
            },
        ):
            report = build_readiness_report(ROOT)
        self.assertEqual(report["status"], "passed")
        self.assertFalse(report["production_qualified"])
        self.assertEqual(
            report["components"]["layout_scoring_process"]["state"],
            "available_from_source",
        )
        circuit = report["components"]["circuit_worker"]
        self.assertEqual(circuit["validation_state"], "experimental")
        self.assertTrue(circuit["integrity_verified"])
        native = report["components"]["native_solver_adapter"]
        self.assertEqual(native["state"], "integration_pending")
        self.assertEqual(native["physics"], [])
        self.assertFalse(native["product_physics_eligible"])

    def test_required_native_runtime_fails_closed(self) -> None:
        with patch(
            "python.spike_core.beta_runtime_readiness.probe_runtime_capabilities",
            return_value={"status": "not_found", "product_physics_eligible": False},
        ):
            report = build_readiness_report(ROOT, require_native_runtime=True)
        self.assertEqual(report["status"], "failed")
        self.assertTrue(report["errors"])

    def test_circuit_manifest_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "app" / "src-tauri" / "resources" / "worker"
            package.mkdir(parents=True)
            (package / "spike-circuit-worker").mkdir()
            manifest = {
                "contract": "spike/owned-spice-process-package/v1",
                "capability": {
                    "engine": "spike-circuit-worker", "validation_state": "experimental",
                    "structured_workspace_only": True, "raw_netlist_accepted": False,
                    "shell_invoked": False, "trusted_host_supervision_required": True,
                    "binary_and_library_sha256_admission": True,
                },
                "files": [{"path": "../escape", "bytes": 0, "sha256": "0" * 64}],
            }
            (package / "spike-circuit-worker.manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8",
            )
            with self.assertRaises(BetaReadinessError):
                inspect_circuit_package(root)

    def test_help_identifies_non_qualification_boundary(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "run_beta_process_smoke.py"), "--help"],
            cwd=ROOT, capture_output=True, text=True, shell=False, check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertIn("does not qualify numerical physics", completed.stdout)


if __name__ == "__main__":
    unittest.main()
