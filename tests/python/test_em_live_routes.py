# SPDX-License-Identifier: Apache-2.0
"""Actual worker/CLI execution and fail-closed transport for live EM routes."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from numpy.linalg import LinAlgError

from python.spike_core.cli import EXIT_OK, EXIT_USAGE, main
from python.spike_core.cli_em_cosimulation import dispatch_em_cosimulation
from python.spike_core.service import handle
from python.spike_core.service_em_cosimulation import handle_em_cosimulation_request
from tests.python.test_em_body_heating import request as body_request
from tests.python.test_em_spice_coupling import request as spice_request

ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "scripts" / "spike_worker_entry.py"
METHODS = ("run_em_spice_coupling", "run_em_body_heating")
CASES = (
    ("spice", METHODS[0], spice_request, "spike/em-spice-coupling-result/v1"),
    ("body-heating", METHODS[1], lambda: body_request()[0], "spike/em-body-heating-result/v1"),
)


class EmLiveRouteTests(unittest.TestCase):
    def assertExperimental(self, result, contract):
        self.assertEqual(result["contract"], contract)
        self.assertEqual(result["model_status"], "experimental")
        self.assertIs(result["production_qualified"], False)
        if contract == "spike/em-spice-coupling-result/v1":
            self.assertEqual(result["provenance"]["native_execution_count"], 1)
            self.assertFalse(result["provenance"]["native_ac_route"])
            self.assertAlmostEqual(result["samples"][0]["voltage_rms_v"][0][0], 4/3)
        else:
            self.assertIs(result["source_authenticity_verified"], False)
            self.assertIs(result["shared_solver_mesh_verified"], False)
            self.assertGreater(result["deposited_body_power_w"], 0)
            self.assertLess(result["deposited_body_power_w"], result["accepted_port_power_w"])

    def test_actual_worker_routes_execute_and_preserve_unqualified_status(self):
        for _, method, factory, contract in CASES:
            with self.subTest(method=method):
                response = handle({"method": method, "params": {"request": factory()}})
                self.assertTrue(response["ok"], response)
                self.assertExperimental(response["result"], contract)

    def test_exact_wrapper_finite_json_and_size_checks_precede_numerics(self):
        invalid_params = (
            {}, {"request": {}, "executable": "untrusted"}, {"request": []},
            {"request": {"nonfinite": float("nan")}},
            {"request": {"oversized": "x"*(8*1024**2)}},
        )
        for _, method, _, _ in CASES:
            target = "python.spike_core." + ("solvers.execution.coupling.em_spice_coupling." if method == METHODS[0] else "solvers.execution.coupling.em_body_heating.") + method
            for params in invalid_params:
                with self.subTest(method=method, keys=list(params)), patch(target) as engine:
                    response = handle_em_cosimulation_request(method, params)
                    self.assertFalse(response["ok"], response)
                    self.assertEqual(response["error_code"], "SPIKE-BE-IPC-E-0001")
                    self.assertEqual(response["error_detail"]["context"]["method"], method)
                    self.assertNotIn("result", response)
                    engine.assert_not_called()

    def test_unavailable_abi_io_and_numerical_errors_return_structured_failure(self):
        failures = (RuntimeError("owned ABI unavailable"), OSError("owned library unavailable"),
                    FloatingPointError("overflow"), LinAlgError("singular"))
        for _, method, _, _ in CASES:
            target = "python.spike_core." + ("solvers.execution.coupling.em_spice_coupling." if method == METHODS[0] else "solvers.execution.coupling.em_body_heating.") + method
            for failure in failures:
                with self.subTest(method=method, error=type(failure).__name__), patch(target, side_effect=failure):
                    response = handle_em_cosimulation_request(method, {"request": {}})
                    self.assertFalse(response["ok"], response)
                    self.assertNotIn("result", response)
                    self.assertIn(str(failure), response["error_detail"]["detail"])
                    self.assertEqual(response["error_detail"]["context"]["method"], method)

    def test_actual_physics_admission_failures_are_not_promoted(self):
        spice = spice_request()
        spice["source"]["s_parameters"][0][0][0]["real"] = 1.1
        body, _ = body_request()
        body["source_binding"]["mesh_digest"] = "f"*64
        for method, candidate in zip(METHODS, (spice, body)):
            response = handle({"method": method, "params": {"request": candidate}})
            self.assertFalse(response["ok"], response)
            self.assertNotIn("result", response)
        self.assertIsNone(handle_em_cosimulation_request("not-an-em-route", {}))

    def test_actual_cli_commands_and_invalid_request_json_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for command, _, factory, contract in CASES:
                with self.subTest(command=command):
                    path, output = root / f"{command}.json", root / f"{command}-out.json"
                    path.write_text(json.dumps(factory()), encoding="utf-8")
                    exit_code = main(["--quiet", "--output", str(output), "em-cosim", command, str(path)])
                    self.assertEqual(exit_code, EXIT_OK)
                    self.assertExperimental(json.loads(output.read_text(encoding="utf-8")), contract)
                    path.write_text("{}", encoding="utf-8")
                    exit_code = main(["--quiet", "--output", str(output), "em-cosim", command, str(path)])
                    self.assertEqual(exit_code, EXIT_USAGE)
                    failure = json.loads(output.read_text(encoding="utf-8"))
                    self.assertIs(failure["ok"], False)
                    self.assertNotIn("production_qualified", failure)

    def test_cli_file_size_guard_precedes_read_and_dispatch(self):
        for command, _, _, _ in CASES:
            path = Mock()
            path.stat.return_value.st_size = 8*1024**2 + 1
            read, response = Mock(), Mock()
            with self.assertRaisesRegex(ValueError, "8 MiB"):
                dispatch_em_cosimulation(SimpleNamespace(request=path, em_cosim_command=command),
                                         read_json=read, response=response)
            read.assert_not_called()
            response.assert_not_called()

    def test_fresh_worker_process_executes_both_new_routes(self):
        for _, method, factory, contract in CASES:
            with self.subTest(method=method):
                process = subprocess.run([sys.executable, str(ENTRYPOINT)], cwd=ROOT,
                    input=json.dumps({"id": method, "method": method, "params": {"request": factory()}})+"\n",
                    text=True, capture_output=True, timeout=30, check=False)
                self.assertEqual(process.returncode, 0, process.stderr)
                response = json.loads(process.stdout)
                self.assertTrue(response["ok"], response)
                self.assertExperimental(response["result"], contract)


if __name__ == "__main__":
    unittest.main()
