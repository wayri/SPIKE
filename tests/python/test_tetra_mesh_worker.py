# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Worker routing checks; actual OCC geometry is tested separately."""
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.service_assembly_handlers import handle_assembly_request


class TetraMeshWorkerTests(unittest.TestCase):
    def test_routes_budgets_and_cleans_case(self):
        with patch("python.spike_core.gmsh_occ_runtime.run_occ_case", return_value={"status": "completed"}) as run:
            response = handle_assembly_request("generate_tetrahedral_mesh", {
                "request": {"contract": "fixture"}, "timeout_s": 90, "memory_limit_mb": 1024})
            self.assertTrue(response["ok"])
            self.assertEqual(run.call_args.kwargs, {"timeout_s": 90, "memory_limit_mb": 1024})
            self.assertFalse(Path(run.call_args.args[1]).parent.exists())

    def test_runtime_failure_is_structured(self):
        with patch("python.spike_core.gmsh_occ_runtime.run_occ_case", side_effect=ValueError("GMSH_RUNTIME: unavailable")):
            response = handle_assembly_request("generate_tetrahedral_mesh", {"request": {}})
            self.assertFalse(response["ok"])
            self.assertIn("GMSH_RUNTIME", str(response))

    def test_rejects_executable_override(self):
        with patch("python.spike_core.gmsh_occ_runtime.run_occ_case") as run:
            response = handle_assembly_request("generate_tetrahedral_mesh", {"request": {}, "executable": "anything"})
            self.assertFalse(response["ok"])
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
