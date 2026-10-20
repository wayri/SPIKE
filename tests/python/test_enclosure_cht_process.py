# SPDX-License-Identifier: Apache-2.0
"""Actual enclosure CHT CLI round trips and capability-claim controls."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from python.spike_core.service_cfd import handle_cfd_request
from tests.python.test_enclosure_cht import fixture


ROOT = Path(__file__).resolve().parents[2]


def run_cli(request):
    temporary_parent = ROOT / "build"
    temporary_parent.mkdir(parents=True, exist_ok=True)
    directory = tempfile.TemporaryDirectory(prefix="enclosure-cht-process-", dir=temporary_parent)
    root = Path(directory.name)
    request_path = root / "request.json"
    output_path = root / "result.json"
    request_path.write_text(json.dumps(request, allow_nan=False), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_cfd.py"),
         "--engine", "enclosure-cht", "--request", str(request_path),
         "--output", str(output_path)],
        cwd=ROOT, capture_output=True, text=True, timeout=60, shell=False,
    )
    response = json.loads(output_path.read_text(encoding="utf-8"))
    return directory, completed, response


class EnclosureChtProcessTests(unittest.TestCase):
    def test_actual_cli_completed_result_returns_zero(self):
        directory, completed, response = run_cli(fixture((2, 2, 2)))
        with directory:
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(response["ok"], response)
            result = response["result"]
            self.assertEqual(result["status"], "completed", result)
            self.assertEqual(result["contract"], "spike/enclosure-cht-result/v1")
            self.assertFalse(result["production_qualified"])
            self.assertIn("fields", result)
            self.assertFalse(result["grid"]["momentum_locally_refined"])

    def test_actual_cli_blocked_result_returns_three_without_fields(self):
        request = fixture((2, 2, 2))
        request["flow"]["model"] = "SST"
        directory, completed, response = run_cli(request)
        with directory:
            self.assertEqual(completed.returncode, 3, completed.stderr)
            self.assertTrue(response["ok"], response)
            result = response["result"]
            self.assertEqual(result["status"], "blocked", result)
            self.assertNotIn("fields", result)
            self.assertTrue(result["issues"])

    def test_service_and_process_capabilities_remain_bounded_and_honest(self):
        response = handle_cfd_request("cfd_capabilities", {})
        self.assertTrue(response["ok"], response)
        catalog = response["result"]
        capability = catalog["engines"]["spike.enclosure_cht"]
        self.assertTrue(capability["available"])
        self.assertEqual(capability["model_status"], "experimental")
        self.assertEqual(capability["geometry"],
                         "supplied_voxel_regions_nested_thermal_tensor_grid")
        self.assertTrue(capability["creeping_obstacles"])
        self.assertTrue(capability["inertial_rectangular_fluid_region"])
        self.assertTrue(capability["local_thermal_refinement"])
        self.assertFalse(capability["local_momentum_refinement"])
        self.assertFalse(capability["turbulence"])
        self.assertFalse(capability["rotating_machinery"])
        self.assertFalse(capability["production_qualified"])
        self.assertFalse(catalog["production_qualified"])
        self.assertFalse(catalog["assembly_cht_supported"])

        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "run_cfd.py"), "--capabilities"],
            cwd=ROOT, capture_output=True, text=True, timeout=30, shell=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        process_catalog = json.loads(completed.stdout)["result"]
        self.assertEqual(process_catalog["engines"]["spike.enclosure_cht"], capability)


if __name__ == "__main__":
    unittest.main()
