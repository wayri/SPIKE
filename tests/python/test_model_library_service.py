# SPDX-License-Identifier: Apache-2.0
"""Model import is inert, explicit, persistent and composable with existing models."""
import copy
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.service_model_library import handle_model_library_request
from python.spike_core.spice_model_import import import_spice_model
from python.spike_core.spice_workspace import compose_spice_workspace, validate_spice_workspace
from tests.python.test_spice_workspace import fixture_design, fixture_workspace

LIBRARY = ".param shared=10\n.subckt stage a b params: r=1k\nR1 a b {r}\n.ends stage\n.subckt pair a b\nX1 a b stage r=2k\n.ends pair\n"


class ModelLibraryServiceTests(unittest.TestCase):
    def test_exact_inert_service_and_user_provenance(self):
        with patch("subprocess.Popen", side_effect=AssertionError("Import must not start a process")):
            reply = handle_model_library_request("inspect_spice_model_library", {"text": LIBRARY, "name": "owned.lib"})
            self.assertTrue(reply["ok"])
            self.assertEqual([row["subcircuit_name"] for row in reply["result"]["candidates"]], ["stage", "pair"])
            result = handle_model_library_request("import_spice_model", {
                "text": LIBRARY, "name": "owned.lib", "subcircuit_name": "pair",
                "source_locator": "Original user-authored fixture", "license_note": "Apache-2.0"})
        self.assertTrue(result["ok"])
        self.assertFalse(result["result"]["execution_admitted"])
        self.assertEqual(result["result"]["model"]["import_provenance"]["license_note"], "Apache-2.0")

    def test_shipped_library_fixture_imports_every_entry(self):
        source = (Path(__file__).resolve().parents[2] / "examples/user_model_library/filters.lib").read_text(encoding="utf-8")
        reply = handle_model_library_request("inspect_spice_model_library", {"text": source, "name": "filters.lib"})
        self.assertTrue(reply["result"]["valid"], reply)
        self.assertEqual([row["subcircuit_name"] for row in reply["result"]["candidates"]], ["RC_STAGE", "TWO_STAGE"])
        workspace = fixture_workspace()
        for symbol in ("RC_STAGE", "TWO_STAGE"):
            model = import_spice_model(source, symbol, "filters.lib")
            self.assertEqual(model["pins"], ["in", "out", "ref"])
            workspace["models"].append(model)
        preview = compose_spice_workspace(workspace, fixture_design())
        self.assertEqual(preview["status"], "ready", preview["validation"])
        self.assertEqual(preview["netlist"].count(".subckt RC_STAGE "), 1)

    def test_malformed_requests_cannot_select_execution_or_paths(self):
        for params in ({"text": LIBRARY}, {"text": LIBRARY, "name": "x", "execute": True},
                       {"path": "vendor.lib", "name": "x"}):
            self.assertFalse(handle_model_library_request("inspect_spice_model_library", params)["ok"])
        self.assertFalse(handle_model_library_request("import_spice_model", {
            "text": LIBRARY, "name": "x", "subcircuit_name": "pair", "license_note": "x\ncontrol"})["ok"])
        self.assertIsNone(handle_model_library_request("execute_model_library", {}))

    def test_project_roundtrip_and_shared_dependency_composition(self):
        workspace = fixture_workspace()
        workspace["models"] += [import_spice_model(LIBRARY, name, "owned.lib") for name in ("stage", "pair")]
        workspace = json.loads(json.dumps(workspace))
        preview = compose_spice_workspace(workspace, fixture_design())
        self.assertEqual(preview["status"], "ready", preview["validation"])
        self.assertEqual(preview["netlist"].count(".subckt stage "), 1)
        self.assertEqual(len(re.findall(r"(?m)^\.param shared\s*=\s*10$", preview["netlist"])), 1)
        self.assertIn("SPICE_IMPORTED_MODEL_REVIEW", {row["code"] for row in preview["validation"]["warnings"]})

    def test_source_changes_conflicts_and_pin_order_reject_before_run(self):
        for change in ("conflict", "pin_order", "unsafe_source"):
            with self.subTest(change=change):
                workspace = fixture_workspace()
                model = import_spice_model(LIBRARY, "stage")
                workspace["models"].append(model)
                if change == "conflict":
                    duplicate = copy.deepcopy(model)
                    duplicate.update(id="other", source=model["source"].replace("{r}", "7k"))
                    workspace["models"].append(duplicate)
                elif change == "pin_order":
                    model["pins"].reverse()
                else:
                    model["source"] += ".include hidden.lib\n"
                preview = compose_spice_workspace(workspace, fixture_design())
                self.assertEqual(preview["status"], "blocked")
                self.assertEqual(preview["netlist"], "")

    def test_fresh_worker_routes_import_without_a_design_or_solver(self):
        request = {"id": "model-import", "method": "inspect_spice_model_library", "params": {"text": LIBRARY, "name": "owned.lib"}}
        run = subprocess.run([sys.executable, "-m", "python.spike_core.service"],
                             input=json.dumps(request) + "\n", text=True, capture_output=True,
                             cwd=Path(__file__).resolve().parents[2], timeout=30, check=True)
        reply = json.loads(run.stdout)
        self.assertTrue(reply["ok"], reply)
        self.assertTrue(reply["result"]["valid"])


if __name__ == "__main__":
    unittest.main()
