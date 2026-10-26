# SPDX-License-Identifier: Apache-2.0
"""Release-route checks for the experimental AC resistor-loss to CHT composition."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from python.spike_core.cli import EXIT_OK, build_parser, main
from python.spike_core.cli_em_cosimulation import dispatch_em_cosimulation
from python.spike_core.contract_catalog import schema_operation
from python.spike_core.service import handle
from python.spike_core.service_em_cosimulation import handle_em_cosimulation_request
from tests.python.test_em_network_resistor_cht import request

ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "scripts" / "spike_worker_entry.py"
METHOD = "run_em_network_resistor_cht"
COMMAND = "resistor-cht"


class EmNetworkChtReleaseRouteTests(unittest.TestCase):
    def assertExperimentalResult(self, result):
        self.assertEqual(result["contract"], "spike/em-network-resistor-cht-result/v1")
        self.assertEqual(result["model_status"], "experimental")
        self.assertIs(result["production_qualified"], False)
        self.assertEqual(result["ac"]["contract"], "spike/em-network-ac-result/v1")
        self.assertEqual(result["cht"]["status"], "completed")
        self.assertEqual(result["ac"]["model_status"], "experimental")
        self.assertEqual(result["cht"]["model_status"], "experimental")
        self.assertIn("diagnostics", result["cht"])

    def test_direct_service_route_preserves_complete_child_results(self):
        raw, _ = request()
        response = handle({"method": METHOD, "params": {"request": raw}})
        self.assertTrue(response["ok"], response)
        self.assertExperimentalResult(response["result"])

    def test_fresh_json_line_worker_executes_owned_composition(self):
        raw, _ = request()
        process = subprocess.run(
            [sys.executable, str(ENTRYPOINT)], cwd=ROOT,
            input=json.dumps({"id": "cht-release", "method": METHOD,
                              "params": {"request": raw}}) + "\n",
            text=True, capture_output=True, timeout=30, check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        response = json.loads(process.stdout)
        self.assertEqual(response["id"], "cht-release")
        self.assertTrue(response["ok"], response)
        self.assertExperimentalResult(response["result"])

    def test_cli_parser_and_actual_command_use_public_spelling(self):
        parsed = build_parser().parse_args(["em-cosim", COMMAND, "request.json"])
        self.assertEqual(parsed.em_cosim_command, COMMAND)
        temp_root = ROOT / ".local" / "test-temp" / "release-full-20261023"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as directory:
            request_path = Path(directory) / "request.json"
            output_path = Path(directory) / "result.json"
            request_path.write_text(json.dumps(request()[0]), encoding="utf-8")
            code = main(["--quiet", "--output", str(output_path), "em-cosim",
                         COMMAND, str(request_path)])
            self.assertEqual(code, EXIT_OK)
            self.assertExperimentalResult(json.loads(output_path.read_text(encoding="utf-8")))

    def test_wrapper_rejects_malformed_nonfinite_and_resource_inputs_before_solver(self):
        malformed = ({}, {"request": {}, "executable": "not-allowed"}, {"request": []},
                     {"request": {"bad": float("nan")}},
                     {"request": {"oversized": "x" * (8 * 1024**2)}})
        for params in malformed:
            with self.subTest(params_type=type(params).__name__), patch(
                    "python.spike_core.solvers.execution.coupling.em_network_resistor_cht.run_em_network_resistor_cht") as engine:
                response = handle_em_cosimulation_request(METHOD, params)
                self.assertFalse(response["ok"], response)
                self.assertNotIn("result", response)
                engine.assert_not_called()
        path, read, response = Mock(), Mock(), Mock()
        path.stat.return_value.st_size = 8 * 1024**2 + 1
        with self.assertRaisesRegex(ValueError, "8 MiB"):
            dispatch_em_cosimulation(SimpleNamespace(request=path, em_cosim_command=COMMAND),
                                     read_json=read, response=response)
        read.assert_not_called()
        response.assert_not_called()

    def test_child_failure_is_structured_and_never_promoted(self):
        raw, _ = request()
        raw["cht_request"]["energy"]["source_w_m3"][0] = 1.0
        response = handle_em_cosimulation_request(METHOD, {"request": raw})
        self.assertFalse(response["ok"], response)
        self.assertNotIn("result", response)
        self.assertIn("double counting", response["error_detail"]["detail"])

    def test_installed_schema_resolves_ac_contract_and_is_strict_at_top_level(self):
        raw, _ = request()
        report = schema_operation("validate", {
            "name": "em-network-resistor-cht-request-v1.schema.json", "document": raw,
        })
        self.assertTrue(report["valid"], report)
        bad = deepcopy(raw)
        bad["executable"] = "not-allowed"
        self.assertFalse(schema_operation("validate", {
            "name": "em-network-resistor-cht-request-v1.schema.json", "document": bad,
        })["valid"])


if __name__ == "__main__":
    unittest.main()
