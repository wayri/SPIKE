"""Contract tests for the deterministic OpenFOAM thermal adapter."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.openfoam import (
    ADAPTER_CONTRACT,
    CASE_CONTRACT,
    RESULT_CONTRACT,
    _digest,
    _write_normalized_result,
    import_case_result,
    _wsl_case_path,
    openfoam_capabilities,
    prepare_case,
)
from python.spike_core.thermal import ThermalScenario, validate_scenario


def _air_scenario(*, forced: bool = False) -> ThermalScenario:
    return ThermalScenario(
        convection="forced" if forced else "natural",
        heat_sources=[{"id": "U1", "power_w": 8.0, "position": [50.0, 40.0, 3.0]}],
        fans=[{"id": "fan-1", "position": [0, 70, 20], "direction": [1, 0, 0], "flow_rate_m3_s": 0.01}] if forced else [],
    )


class OpenFoamAdapterTests(unittest.TestCase):
    def test_missing_location_is_valid_for_compact_but_blocks_cfd_generation(self):
        validation = validate_scenario(ThermalScenario(heat_sources=[{"id": "U1", "power_w": 4.0}]))
        self.assertTrue(validation["valid"])
        self.assertFalse(validation["capability"]["case_generation_ready"])
        self.assertIn("HEAT_SOURCE_POSITION_INVALID", {issue["code"] for issue in validation["case_issues"]})

    def test_heat_source_outside_volume_blocks_cfd_generation(self):
        scenario = _air_scenario()
        scenario.heat_sources[0]["position"] = [500.0, 40.0, 3.0]
        validation = validate_scenario(scenario)
        self.assertTrue(validation["valid"])
        self.assertFalse(validation["capability"]["case_generation_ready"])
        self.assertIn("HEAT_SOURCE_OUTSIDE_VOLUME", {issue["code"] for issue in validation["case_issues"]})

    def test_generation_is_deterministic_and_uses_a_3d_boundary(self):
        scenario = _air_scenario()
        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "first"
            second = Path(temp_dir) / "second"
            self.assertNotEqual(prepare_case(scenario, first)["status"], "blocked")
            self.assertNotEqual(prepare_case(scenario, second)["status"], "blocked")
            self.assertEqual(
                (first / "system" / "blockMeshDict").read_text(encoding="utf-8"),
                (second / "system" / "blockMeshDict").read_text(encoding="utf-8"),
            )
            boundary = (first / "system" / "blockMeshDict").read_text(encoding="utf-8")
            self.assertNotIn("type empty", boundary)
            self.assertIn("scale 1;", boundary)
            self.assertNotIn("convertToMeters", boundary)
            self.assertTrue((first / "constant" / "turbulenceProperties").is_file())
            self.assertTrue((first / "0" / "alphat").is_file())

    def test_forced_case_has_nonzero_inlet_velocity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "case"
            self.assertNotEqual(prepare_case(_air_scenario(forced=True), root)["status"], "blocked")
            self.assertNotIn("value uniform (0 0 0)", (root / "0" / "U").read_text(encoding="utf-8"))

    def test_result_import_requires_matching_provenance_and_all_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "case"
            self.assertNotEqual(prepare_case(_air_scenario(), root)["status"], "blocked")
            case = json.loads((root / "spike_case.json").read_text(encoding="utf-8"))
            payload = {
                "contract": RESULT_CONTRACT,
                "adapter_contract": ADAPTER_CONTRACT,
                "status": "completed",
                "model_status": "experimental",
                "summary": {"max_temperature_k": 315.0},
                "issues": [],
                "provenance": {
                    "scenario_digest": case["scenario"]["digest"],
                    "case_file_digest": _digest(case["files"]),
                    "runtime": "openfoam2606",
                },
                "fields": {
                    "temperature_k": {"unit": "K", "samples": [{"point_m": [0.01, 0.02, 0.03], "value": 315.0}]},
                    "velocity_m_s": {"unit": "m/s", "samples": [{"point_m": [0.01, 0.02, 0.03], "value": [0.1, 0.0, 0.0]}]},
                    "pressure_pa": {"unit": "Pa", "samples": [{"point_m": [0.01, 0.02, 0.03], "value": 0.0}]},
                },
            }
            target = root / "postProcessing" / "spike" / "thermal-result.json"
            target.parent.mkdir(parents=True)
            target.write_text(json.dumps(payload), encoding="utf-8")
            result = import_case_result(root)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(len(result["fields"]["velocity_m_s"]), 1)
            self.assertIn("OPENFOAM_EXPERIMENTAL_NOT_VALIDATED", {issue["code"] for issue in result["issues"]})

    def test_zero_load_ambient_fields_are_accepted_as_physical_equilibrium(self):
        scenario = _air_scenario()
        scenario.heat_sources[0]["power_w"] = 0.0
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "case"
            self.assertNotEqual(prepare_case(scenario, root)["status"], "blocked")
            latest = root / "1"
            latest.mkdir()
            header = "FoamFile {{ format ascii; }}\ninternalField nonuniform List<{}>\n1\n(\n{}\n)\n;\n"
            (latest / "C").write_text(header.format("vector", "(0.01 0.02 0.03)"), encoding="utf-8")
            (latest / "T").write_text(header.format("scalar", "298.15"), encoding="utf-8")
            (latest / "U").write_text(header.format("vector", "(0 0 0)"), encoding="utf-8")
            (latest / "p_rgh").write_text(header.format("scalar", "0"), encoding="utf-8")
            case = json.loads((root / "spike_case.json").read_text(encoding="utf-8"))
            payload = _write_normalized_result(root, case, {"version": "test"}, "End\n")
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["summary"]["convergence_criterion"], "zero_load_field_equilibrium")

    def test_wsl_runtime_is_execution_ready_without_native_commands(self):
        runtime = {
            "available": True, "transport": "wsl_process", "executable": "wsl://Ubuntu/usr/bin/openfoam2606",
            "version": "2606", "distribution": "Ubuntu", "launcher": "C:/Windows/System32/wsl.exe",
            "command_prefix": ["C:/Windows/System32/wsl.exe", "-d", "Ubuntu", "--", "/usr/bin/openfoam2606"],
        }
        with patch("python.spike_core.openfoam.detect_openfoam_runtime", return_value=runtime), patch(
            "python.spike_core.openfoam.shutil.which", return_value=None
        ):
            capabilities = openfoam_capabilities()
        self.assertTrue(capabilities["execution_ready"])
        self.assertEqual(capabilities["process_transport"], "fixed_argv_no_shell")

    def test_wsl_case_path_uses_fixed_argv_mounted_drive_validation(self):
        runtime = {"launcher": "C:/Windows/System32/wsl.exe", "distribution": "Ubuntu"}
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch("python.spike_core.openfoam.subprocess.run", return_value=completed) as spawned:
            path = _wsl_case_path(runtime, Path(r"C:\\Users\\yawar\\AppData\\Local\\Temp\\case"))
        self.assertEqual(path, "/mnt/c/Users/yawar/AppData/Local/Temp/case")
        self.assertEqual(spawned.call_args.args[0][-3:], ["test", "-d", path])
        self.assertFalse(spawned.call_args.kwargs["shell"])


if __name__ == "__main__":
    unittest.main()
