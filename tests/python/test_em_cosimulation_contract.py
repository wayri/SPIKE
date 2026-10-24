# SPDX-License-Identifier: Apache-2.0
"""Release-boundary tests for experimental EM co-simulation routes."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from python.spike_core.cli import EXIT_OK, EXIT_USAGE, main
from python.spike_core.em_network_ac import WAVE_CONVENTION
from python.spike_core.service import handle
from tests.python.test_em_network_cosimulation import analysis, request as ac_request
from tests.python.test_assembly_tetra_thermal import request as thermal_request
from tests.python.test_pdn_dielectric_thermomechanical import request as thermomechanical_request


ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "scripts" / "spike_worker_entry.py"


def prepare_request() -> dict:
    return {
        "result": analysis(),
        "binding": {"design_id": "board", "digest_sha256": "a" * 64},
        "expected_case_sha256": "b" * 64,
        "expected_script_sha256": "c" * 64,
        "port_bindings": {
            "p0": {
                "positive_node": "signal",
                "negative_node": "0",
                "reference_plane": "declared-pad",
            }
        },
        "wave_convention": WAVE_CONVENTION,
    }


def resistor_thermal_request() -> dict:
    thermal = thermal_request()
    count = len(thermal["mesh"]["cells"])
    return {
        "contract": "spike/em-network-resistor-thermal-request/v1",
        "ac_request": ac_request(),
        "thermal_request": thermal,
        "sample_index": 0,
        "resistor_cell_weights": {
            "p0": {cell["id"]: 1 / count for cell in thermal["mesh"]["cells"]}
        },
    }


class EmCosimulationContractTests(unittest.TestCase):
    def test_strict_request_schemas_accept_real_inputs_and_reject_extra_fields(self) -> None:
        cases = (
            ("emerge-cosimulation-prepare-parameters-v1.schema.json", prepare_request()),
            ("em-network-ac-request-v1.schema.json", ac_request()),
            ("em-network-resistor-thermal-request-v1.schema.json", resistor_thermal_request()),
        )
        for filename, request in cases:
            with self.subTest(schema=filename):
                schema = json.loads((ROOT / "schemas" / filename).read_text(encoding="utf-8"))
                Draft202012Validator.check_schema(schema)
                validator = Draft202012Validator(schema)
                validator.validate(request)
                invalid = copy.deepcopy(request)
                invalid["unexpected"] = True
                self.assertTrue(list(validator.iter_errors(invalid)))

    def test_actual_worker_prepare_preserves_warning_and_rejects_source_error(self) -> None:
        request = prepare_request()
        warning = {"code": "OMITTED_LOSS", "severity": "warning", "message": "not modeled"}
        request["result"]["status"] = "completed_with_warnings"
        request["result"]["issues"] = [warning]
        response = handle({
            "method": "prepare_emerge_cosimulation_source",
            "params": {"request": request},
        })
        self.assertTrue(response["ok"], response)
        result = response["result"]
        self.assertEqual(result["source_issues"], [warning])
        self.assertEqual(result["model_status"], "unvalidated")
        self.assertIs(result["production_qualified"], False)

        request["result"]["issues"][0]["severity"] = "error"
        rejected = handle({
            "method": "prepare_emerge_cosimulation_source",
            "params": {"request": request},
        })
        self.assertFalse(rejected["ok"], rejected)
        self.assertEqual(rejected["error_code"], "SPIKE-BE-IPC-E-0001")
        self.assertIn("blocking error", rejected["error_detail"]["detail"])

    def test_actual_worker_ac_resistor_thermal_and_thermomechanical(self) -> None:
        cases = (
            ("solve_em_network_ac", ac_request(), "spike/em-network-ac-result/v1"),
            ("run_em_network_resistor_thermal", resistor_thermal_request(),
             "spike/em-network-resistor-thermal-result/v1"),
            ("run_pdn_dielectric_thermomechanical", thermomechanical_request(1),
             "spike/pdn-dielectric-thermomechanical-result/v1"),
        )
        for method, request, contract in cases:
            with self.subTest(method=method):
                response = handle({"method": method, "params": {"request": request}})
                self.assertTrue(response["ok"], response)
                self.assertEqual(response["result"]["contract"], contract)
                self.assertEqual(response["result"]["model_status"], "experimental")
                self.assertIs(response["result"]["production_qualified"], False)
        self.assertAlmostEqual(
            handle({"method": "solve_em_network_ac", "params": {"request": ac_request()}})
            ["result"]["samples"][0]["series_resistor_power_w"][0],
            0.02,
        )

    def test_worker_params_are_exact_and_fail_with_structured_context(self) -> None:
        for method in (
            "prepare_emerge_cosimulation_source",
            "solve_em_network_ac",
            "run_em_network_resistor_thermal",
            "run_pdn_dielectric_thermomechanical",
        ):
            for params in ({}, {"request": {}, "extra": True}):
                with self.subTest(method=method, params=params):
                    response = handle({"method": method, "params": params})
                    self.assertFalse(response["ok"], response)
                    self.assertEqual(response["error_code"], "SPIKE-BE-IPC-E-0001")
                    self.assertEqual(response["error_detail"]["context"]["method"], method)
                    self.assertIn("kernel_code", response["error_detail"]["context"])

    def test_cli_group_runs_all_actual_public_subcommands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = (
                ("prepare", prepare_request(), "spike/emerge-cosimulation-source/v1"),
                ("ac", ac_request(), "spike/em-network-ac-result/v1"),
                ("resistor-thermal", resistor_thermal_request(),
                 "spike/em-network-resistor-thermal-result/v1"),
            )
            for command, request, contract in cases:
                with self.subTest(command=command):
                    request_path = root / f"{command}.json"
                    output_path = root / f"{command}-result.json"
                    request_path.write_text(json.dumps(request), encoding="utf-8")
                    code = main(["--quiet", "--output", str(output_path),
                                 "em-cosim", command, str(request_path)])
                    self.assertEqual(code, EXIT_OK)
                    result = json.loads(output_path.read_text(encoding="utf-8"))
                    self.assertEqual(result["contract"], contract)
                    self.assertIs(result["production_qualified"], False)

    def test_subprocess_worker_and_cli_execute_actual_ac_and_failed_output_is_json(self) -> None:
        worker = subprocess.run(
            [sys.executable, str(ENTRYPOINT)],
            cwd=ROOT,
            input=json.dumps({
                "id": "em-cosim-ac",
                "method": "solve_em_network_ac",
                "params": {"request": ac_request()},
            }) + "\n",
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(worker.returncode, 0, worker.stderr)
        worker_response = json.loads(worker.stdout)
        self.assertTrue(worker_response["ok"], worker_response)
        self.assertEqual(worker_response["result"]["contract"], "spike/em-network-ac-result/v1")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid_path = root / "ac.json"
            valid_path.write_text(json.dumps(ac_request()), encoding="utf-8")
            cli = subprocess.run(
                [sys.executable, str(ENTRYPOINT), "--cli", "--compact",
                 "em-cosim", "ac", str(valid_path)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(cli.returncode, EXIT_OK, cli.stderr)
            self.assertEqual(json.loads(cli.stdout)["contract"], "spike/em-network-ac-result/v1")

            invalid_path = root / "invalid.json"
            failed_path = root / "failed.json"
            invalid_path.write_text("{}", encoding="utf-8")
            failed = subprocess.run(
                [sys.executable, str(ENTRYPOINT), "--cli", "--quiet", "--output",
                 str(failed_path), "em-cosim", "ac", str(invalid_path)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(failed.returncode, EXIT_USAGE)
            self.assertEqual(failed.stdout, "")
            error = json.loads(failed_path.read_text(encoding="utf-8"))
            self.assertIs(error["ok"], False)
            self.assertIn("invalid", error["error"].lower())


if __name__ == "__main__":
    unittest.main()
