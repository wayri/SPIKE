from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from python.spike_core.openfoam_multiregion_execution import (
    MultiRegionExecutionError, RUNNABLE_CASE_CONTRACT, _digest,
    _bounded_command, _command, _write_native_field_export, import_multiregion_fields,
    load_verified_runnable_case, run_multiregion_case,
)


def _case(root: Path) -> dict:
    control = root / "system" / "controlDict"; control.parent.mkdir(parents=True); control.write_text("application chtMultiRegionFoam;\n", encoding="utf-8")
    files = {"system/controlDict": hashlib.sha256(control.read_bytes()).hexdigest()}
    manifest = {"contract": RUNNABLE_CASE_CONTRACT, "status": "runnable", "solver": "chtMultiRegionFoam", "regions": ["board", "air"], "region_kinds": {"board": "solid", "air": "fluid"}, "region_conductivity_w_mk": {"board": 0.35, "air": 0.026}, "view_factor_regions": [], "input_files": files, "field_export_path": "postProcessing/spike/fields.json"}
    manifest["manifest_digest"] = _digest(manifest)
    (root / "spike_multiregion_runnable_case.json").write_text(json.dumps(manifest), encoding="utf-8")
    _export(root, manifest)
    return manifest


def _export(root: Path, manifest: dict) -> Path:
    payload = {"manifest_digest": manifest["manifest_digest"], "regions": [
        {"id": "board", "kind": "solid", "positions_m": [[0, 0, 0]], "temperature_k": [300], "heat_flux_w_m2": [[1, 2, 2]]},
        {"id": "air", "kind": "fluid", "positions_m": [[0.001, 0, 0]], "temperature_k": [301], "heat_flux_w_m2": [[0, 0, 1]], "velocity_m_s": [[0.2, 0, 0]], "pressure_pa": [101325]},
    ]}
    target = root / "postProcessing" / "spike" / "fields.json"; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def _foam_field(kind: str, values: list[object]) -> str:
    body = "\n".join(str(value) for value in values)
    return f"FoamFile {{ format ascii; }}\ninternalField nonuniform List<{kind}>\n{len(values)}\n(\n{body}\n)\n;\n"


class OpenFoamMultiRegionExecutionTests(unittest.TestCase):
    def test_import_requires_verified_manifest_and_complete_aligned_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest = _case(root)
            verified_root, verified = load_verified_runnable_case(root)
            result = import_multiregion_fields(verified_root, verified)
            self.assertEqual(result["contract"], "spike/thermal-field-result/v1")
            self.assertEqual(result["summary"]["total_samples"], 2)
            self.assertEqual(len(result["provenance"]["field_export_sha256"]), 64)
            self.assertAlmostEqual(result["fields"]["temperature_k"]["samples"][0]["value"], 300.0)
            self.assertEqual(result["fields"]["heat_flux_w_m2"]["samples"][0]["value"], [1.0, 2.0, 2.0])
            self.assertFalse(result["qualification"]["production_qualified"])
            manifest["manifest_digest"] = "0" * 64
            (root / "spike_multiregion_runnable_case.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(MultiRegionExecutionError):
                load_verified_runnable_case(root)

    def test_native_postprocess_fields_produce_schema_valid_canonical_result(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest = _case(root)
            latest = root / "10"
            for region, fluid in (("board", False), ("air", True)):
                folder = latest / region; folder.mkdir(parents=True)
                (folder / "C").write_text(_foam_field("vector", ["(0.001 0.002 0.003)"]), encoding="utf-8")
                (folder / "T").write_text(_foam_field("scalar", ["310"]), encoding="utf-8")
                (folder / "grad(T)").write_text(_foam_field("vector", ["(2 -1 0.5)"]), encoding="utf-8")
                if fluid:
                    (folder / "U").write_text(_foam_field("vector", ["(0.2 0 0)"]), encoding="utf-8")
                    (folder / "p_rgh").write_text(_foam_field("scalar", ["101325"]), encoding="utf-8")
            _write_native_field_export(root, manifest)
            result = import_multiregion_fields(root, manifest)
            schema_path = Path(__file__).resolve().parents[2] / "schemas" / "thermal-field-result-v1.schema.json"
            Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).validate(result)
            self.assertEqual(set(result["fields"]), {"temperature_k", "heat_flux_w_m2", "velocity_m_s", "pressure_pa"})
            self.assertEqual(result["fields"]["temperature_k"]["total_samples"], 2)
            self.assertEqual(result["fields"]["velocity_m_s"]["total_samples"], 1)
            self.assertEqual(result["fields"]["heat_flux_w_m2"]["samples"][0]["value"], [-0.7, 0.35, -0.175])

    def test_wsl_command_uses_mounted_case_path_and_no_shell_tokens(self):
        runtime = {
            "transport": "wsl_process", "version": "2606", "launcher": "C:/Windows/System32/wsl.exe", "distribution": "Ubuntu",
            "command_prefix": ["C:/Windows/System32/wsl.exe", "-d", "Ubuntu", "--", "/usr/bin/openfoam2606"],
        }
        with patch("python.spike_core.openfoam_multiregion_execution._wsl_case_path", return_value="/mnt/c/case") as mapped:
            argv = _command(runtime, "checkMesh", Path(r"C:\\case"), "-allRegions", "-allTopology")
        self.assertEqual(argv, [*runtime["command_prefix"], "checkMesh", "-case", "/mnt/c/case", "-allRegions", "-allTopology"])
        mapped.assert_called_once()
        self.assertFalse(any(any(character in item for character in "|;&$") for item in argv))

    def test_wsl_solver_limits_are_applied_inside_linux_without_shell(self):
        runtime = {
            "transport": "wsl_process", "version": "2606", "distribution": "Ubuntu",
            "command_prefix": ["C:/Windows/System32/wsl.exe", "-d", "Ubuntu", "--", "/usr/bin/openfoam2606"],
        }
        with patch("python.spike_core.openfoam_multiregion_execution._wsl_case_path", return_value="/mnt/c/case"):
            argv = _bounded_command(
                runtime, "chtMultiRegionFoam", Path(r"C:\case"),
                timeout_s=60, memory_limit_mb=1024, output_limit_bytes=1048576,
            )
        self.assertEqual(argv[5:11], ["/usr/bin/prlimit", "--as=1073741824", "--cpu=63", "--fsize=1048576", "--", "chtMultiRegionFoam"])
        self.assertEqual(argv[11:], ["-case", "/mnt/c/case"])
        self.assertFalse(any(any(character in item for character in "|;&$") for item in argv))

    def test_unaligned_or_partial_export_rejects_all_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest = _case(root)
            target = root / "postProcessing" / "spike" / "fields.json"
            payload = json.loads(target.read_text(encoding="utf-8")); payload["regions"][1]["pressure_pa"] = []
            target.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(MultiRegionExecutionError, "aligned"):
                import_multiregion_fields(root, manifest)

    def test_execution_uses_fixed_argv_checks_every_region_then_imports(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); _case(root); calls = []
            def runner(argv, **kwargs):
                calls.append((argv, kwargs)); return {"return_code": 0, "stdout": "ok", "stderr": ""}
            runtime = {"transport": "native_process", "version": "2606"}
            with patch("python.spike_core.openfoam_multiregion_execution.shutil.which", side_effect=lambda name: f"/opt/openfoam/{name}"), patch(
                "python.spike_core.openfoam_multiregion_execution._write_native_field_export", side_effect=lambda case_root, manifest: _export(case_root, manifest),
            ):
                result = run_multiregion_case(root, runtime=runtime, runner=runner)
            self.assertEqual(result["status"], "completed", result)
            commands = [call[0][0].split("/")[-1] for call in calls]
            self.assertEqual(commands[:3], ["checkMesh", "chtMultiRegionFoam", "postProcess"])
            self.assertEqual(commands[3], "checkMesh")
            self.assertEqual(commands[4], "chtMultiRegionFoam")
            self.assertEqual(commands[5:], ["postProcess"] * 6)
            self.assertTrue(all(isinstance(item, str) for call, _ in calls for item in call))

    def test_view_factor_case_probes_and_executes_required_preprocessors_before_solver(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest = _case(root); calls = []
            manifest["view_factor_regions"] = ["board"]
            manifest["manifest_digest"] = _digest({key: value for key, value in manifest.items() if key != "manifest_digest"})
            (root / "spike_multiregion_runnable_case.json").write_text(json.dumps(manifest), encoding="utf-8")

            def runner(argv, **kwargs):
                calls.append((argv, kwargs)); return {"return_code": 0, "stdout": "ok", "stderr": ""}

            runtime = {"transport": "native_process", "version": "2606"}
            with patch("python.spike_core.openfoam_multiregion_execution.shutil.which", side_effect=lambda name: f"/opt/openfoam/{name}"), patch(
                "python.spike_core.openfoam_multiregion_execution._write_native_field_export", side_effect=lambda case_root, verified: _export(case_root, verified),
            ):
                result = run_multiregion_case(root, runtime=runtime, runner=runner)

            self.assertEqual(result["status"], "completed", result)
            probe_names = list(result["runtime_probe"]["commands"])
            self.assertEqual(probe_names, ["checkMesh", "chtMultiRegionFoam", "postProcess", "faceAgglomerate", "viewFactorsGen"])
            execution = result["execution"]
            self.assertEqual(
                [(item["command"], item.get("region")) for item in execution[:4]],
                [("checkMesh", None), ("faceAgglomerate", "board"), ("viewFactorsGen", "board"), ("chtMultiRegionFoam", None)],
            )
            self.assertEqual(execution[1]["argv"][-2:], ["-region", "board"])
            self.assertEqual(execution[2]["argv"][-2:], ["-region", "board"])

    def test_cancellation_never_returns_partial_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); _case(root)
            event = __import__("threading").Event(); event.set()
            result = run_multiregion_case(root, cancellation_event=event)
            self.assertEqual(result["status"], "cancelled")
            self.assertEqual(result["fields"], {})

    def test_postprocess_or_import_failure_never_returns_partial_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); _case(root)
            def runner(argv, **kwargs):
                return {"return_code": 0, "stdout": "ok", "stderr": ""}
            runtime = {"transport": "native_process", "version": "2606"}
            with patch("python.spike_core.openfoam_multiregion_execution.shutil.which", return_value="/opt/openfoam/command"), patch(
                "python.spike_core.openfoam_multiregion_execution._write_native_field_export", side_effect=MultiRegionExecutionError("missing grad(T)"),
            ):
                result = run_multiregion_case(root, runtime=runtime, runner=runner)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["fields"], {})


if __name__ == "__main__":
    unittest.main()
