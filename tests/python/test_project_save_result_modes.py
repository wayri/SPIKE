# SPDX-License-Identifier: Apache-2.0
"""Result-inclusive and result-free project saves preserve assembly setup."""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from python.spike_core.project_package import read_project
from python.spike_core.project_state_artifacts import hydrate_result_state
from python.spike_core.service_project_handlers import handle_project_request
from tests.python import test_assembly_designs as assembly_fixtures


class ProjectSaveResultModesTests(unittest.TestCase):
    def test_links_and_results_round_trip_then_result_free_save(self):
        design, _, assembly, designs = assembly_fixtures.AssemblyDesignTests().fixture()
        mate = {"id": "stack-mate", "kind": "connector-mate", "name": "Stack header",
                "data": {"endpoint_a": "controller-board::J3", "endpoint_b": "load-board::J4",
                         "pin_map": {"1": "2"}}}
        assembly["connector_mappings"].append(mate)
        result = {"analysis_id": "run-1", "mode": "pi", "scalar_fields": {"voltage_v": [1.2]},
                  "future_engine_output": {"all_samples": [1, 2, 3]}}
        setup = {"mode": "pi", "pi_setup": {"net": "+3V3"}, "latest_result": result,
                 "result_history": [{"id": "run-1", "bundle": result}]}
        snapshot = {"format": "spike-project-package/v2", "contract": "spike/project/v2",
                    "project": {"name": "stack.spike"}, "design": {"source_board": ""},
                    "analysis": copy.deepcopy(setup), "assembly_ir": assembly,
                    "assembly_designs": designs, "emi": {"setup": {"band": "test"}, "screening": {"result": 1}},
                    "thermal": {"scenario": {"ambient_c": 25, "result": {"peak_c": 55},
                                             "field_result": {"peak_c": 55}}}}
        payload = {"project": {"name": "stack.spike"}, "design_ir": design,
                   "assembly_ir": assembly, "assembly_designs": designs,
                   "analyses": copy.deepcopy(setup), "results": {"latest_result": result},
                   "extensions": {"legacy": snapshot}}
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "with-results.spike"
            response = handle_project_request("write_project_package", {"path": str(first),
                "snapshot": payload, "generate_geometry_tables": False},
                request_id="save-with", application_version="test")
            self.assertTrue(response["ok"], response)
            opened = read_project(first, include_members=True)
            self.assertEqual(opened.payload["assembly_ir"]["connector_mappings"][-1]["data"], mate["data"])
            self.assertEqual(opened.payload["assembly_ir"]["harnesses"], assembly["harnesses"])
            self.assertTrue(any(name.startswith("state/artifacts/") for name in opened.members))
            restored = hydrate_result_state(opened.payload, first, opened.manifest["manifest_payload_sha256"])
            self.assertEqual(restored["analyses"]["latest_result"], result)
            self.assertEqual(restored["extensions"]["legacy"]["analysis"]["result_history"][0]["bundle"], result)

            second = Path(directory) / "without-results.spike"
            response = handle_project_request("write_project_package", {"path": str(second),
                "snapshot": payload, "base_package_path": str(first),
                "include_results": False, "generate_geometry_tables": False},
                request_id="save-without", application_version="test")
            self.assertTrue(response["ok"], response)
            reopened = read_project(second, include_members=True)
            self.assertEqual(reopened.payload["assembly_ir"], opened.payload["assembly_ir"])
            self.assertEqual(reopened.payload["analyses"]["pi_setup"], setup["pi_setup"])
            self.assertEqual(reopened.payload["analyses"]["result_history"], [])
            self.assertNotIn("latest_result", reopened.payload["analyses"])
            self.assertEqual(reopened.payload["results"], {})
            self.assertEqual(reopened.payload["extensions"]["legacy"]["emi"]["setup"], {"band": "test"})
            self.assertNotIn("screening", reopened.payload["extensions"]["legacy"]["emi"])
            self.assertEqual(reopened.payload["extensions"]["legacy"]["thermal"]["scenario"], {"ambient_c": 25})
            self.assertFalse(any(name.startswith("state/artifacts/") for name in reopened.members))


if __name__ == "__main__":
    unittest.main()
