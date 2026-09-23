from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.external_engines import (
    ExternalEngineDescriptor,
    _run_isolated_python,
    external_engine_catalog,
    prepare_openems_case,
    run_openems_case,
)
from python.spike_core.openems_case_integrity import load_strict_json
from python.spike_core.openems_validation import validate_normalized_result


def openems_design() -> DesignIR:
    return DesignIR(
        design_id="fixture",
        name="OpenEMS fixture",
        layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
        nets=[{"id": "1", "name": "RF"}],
        tracks=[{
            "id": "track-1",
            "start": [0.0, 0.0],
            "end": [20.0, 0.0],
            "width": 1.0,
            "layer": "F.Cu",
            "net_name": "RF",
        }],
        stackup=[
            {"name": "F.Cu", "type": "copper", "thickness": 0.035},
            {"name": "dielectric 1", "type": "core", "thickness": 1.53, "epsilon_r": 4.2, "loss_tangent": 0.02},
            {"name": "B.Cu", "type": "copper", "thickness": 0.035},
        ],
    )


class ExternalEngineTests(unittest.TestCase):
    def setUp(self):
        self.state_directory = tempfile.TemporaryDirectory()
        self.state_environment = patch.dict(
            os.environ,
            {"SPIKE_STATE_HOME": str(Path(self.state_directory.name) / "state")},
        )
        self.state_environment.start()

    def tearDown(self):
        self.state_environment.stop()
        self.state_directory.cleanup()

    def test_integrity_key_is_written_as_opaque_binary_material(self):
        spec = AnalysisSpec(
            analysis_id="openems-binary-key",
            mode="broadband_hf",
            net_names=["RF"],
            frequency_start_hz=1e6,
            frequency_stop_hz=1e9,
        )
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"SPIKE_STATE_HOME": str(Path(directory) / "state")}
        ), patch(
            "python.spike_core.openems_case_integrity.secrets.token_bytes",
            return_value=b"\n" * 32,
        ):
            result = prepare_openems_case(openems_design(), spec, Path(directory) / "case")
            key = (Path(directory) / "state" / "external-case.key").read_bytes()

        self.assertEqual(result["status"], "prepared_review_required")
        self.assertEqual(key, b"\n" * 32)

    def test_catalog_contains_capability_gated_openems(self):
        catalog = external_engine_catalog(refresh=True)
        self.assertEqual(catalog["contract"], "spike/external-engine-catalog/v1")
        self.assertEqual(catalog["installation_policy"], "explicit_local_discovery_no_implicit_downloads")
        openems = next(item for item in catalog["engines"] if item["id"] == "external.openems")
        self.assertIn("prepare", openems["actions"])
        self.assertIn("fdtd_3d_experimental", openems["capabilities"])
        self.assertIn("nf2ff_far_field", openems["capabilities"])
        if openems["state"] == "reference_validated":
            self.assertIn("far_field", openems["capabilities"])
            self.assertEqual(openems["model_status"], "reference_validated")
            self.assertEqual(openems["validation_scope"], "openems_adapter.simple_patch_antenna")
        else:
            self.assertNotIn("far_field", openems["capabilities"])

    def test_reference_validated_engine_remains_runnable(self):
        design = openems_design()
        design.nets.append({"id": "2", "name": "GND"})
        design.tracks.append({
            "id": "track-2",
            "start": [0.0, 2.0],
            "end": [20.0, 2.0],
            "width": 1.0,
            "layer": "F.Cu",
            "net_name": "GND",
        })
        spec = AnalysisSpec(
            net_names=["RF", "GND"],
            frequency_start_hz=1e6,
            frequency_stop_hz=1e9,
            options={"ports": [{
                "start": [10.0, 0.0, 0.0],
                "stop": [10.0, 2.0, 0.0],
                "direction": "y",
                "impedance_ohm": 50,
                "excite": True,
            }]},
        )
        validated = ExternalEngineDescriptor(
            id="external.openems",
            name="openEMS FDTD",
            role="test",
            license="GPL-3.0-or-later",
            homepage="https://docs.openems.de/",
            state="reference_validated",
        )
        with tempfile.TemporaryDirectory() as directory, patch(
            "python.spike_core.external_engines._openems_descriptor", return_value=validated
        ):
            result = prepare_openems_case(design, spec, Path(directory) / "case")

        self.assertEqual(result["status"], "ready_to_run")
        self.assertTrue(result["validation"]["can_run"])

    def test_prepare_writes_reproducible_job_and_object_map(self):
        spec = AnalysisSpec(
            analysis_id="openems-fixture",
            mode="broadband_hf",
            net_names=["RF"],
            frequency_start_hz=1e6,
            frequency_stop_hz=1e9,
            frequency_points=21,
        )
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory) / "case"
            result = prepare_openems_case(openems_design(), spec, case)
            self.assertEqual(result["status"], "prepared_review_required")
            self.assertTrue((case / "job.json").is_file())
            self.assertTrue((case / "geometry.json").is_file())
            self.assertTrue((case / "object-map.json").is_file())
            self.assertTrue((case / "engine-input" / "run_openems.py").is_file())
            compile((case / "engine-input" / "run_openems.py").read_text(encoding="utf-8"), "run_openems.py", "exec")
            job = json.loads((case / "job.json").read_text(encoding="utf-8"))
            self.assertEqual(job["contract"], "spike/external-engine-job/v1")
            self.assertFalse(job["validation"]["can_run"])
            mapped = json.loads((case / "object-map.json").read_text(encoding="utf-8"))
            self.assertEqual(mapped["entities"][0]["design_id"], "track-1")

    def test_component_bonds_are_counted_and_mapped_for_openems(self):
        design = openems_design()
        design.component_bonds = [{
            "id": "bond:C1:1",
            "enabled": True,
            "component_ref": "C1",
            "pad_id": "pad-C1-1",
            "pad_number": "1",
            "net_name": "RF",
            "connected_layers": ["F.Cu"],
            "status": "ready",
            "electrical": {"resistance_ohm": 0.001, "current_limit_a": 2.0},
            "thermal": {"conductivity_w_mk": 50.0, "contact_area_mm2": 0.8},
        }]
        spec = AnalysisSpec(net_names=["RF"], frequency_start_hz=1e6, frequency_stop_hz=1e9)
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory) / "case"
            result = prepare_openems_case(design, spec, case)
            mapped = json.loads((case / "object-map.json").read_text(encoding="utf-8"))

        self.assertEqual(result["validation"]["coverage"]["component_bonds"], 1)
        bond = next(item for item in mapped["entities"] if item["kind"] == "component_bond")
        self.assertEqual(bond["design_id"], "bond:C1:1")
        self.assertEqual(bond["net"], "RF")

    def test_unreviewed_component_bond_blocks_openems_case(self):
        design = openems_design()
        design.component_bonds = [{"id": "bond:C1:1", "enabled": True, "net_name": "RF", "status": "warning"}]
        spec = AnalysisSpec(net_names=["RF"], frequency_start_hz=1e6, frequency_stop_hz=1e9)
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory) / "case"
            result = prepare_openems_case(design, spec, case)

        self.assertEqual(result["status"], "blocked")
        self.assertIn("OPENEMS_COMPONENT_BOND_INVALID", {item["code"] for item in result["validation"]["errors"]})

    def test_missing_stackup_blocks_case_before_writing(self):
        design = openems_design()
        design.stackup = []
        spec = AnalysisSpec(net_names=["RF"], frequency_start_hz=1e6, frequency_stop_hz=1e9)
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory) / "case"
            result = prepare_openems_case(design, spec, case)
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(case.exists())

    def test_stackup_without_copper_blocks_case_before_writing(self):
        design = openems_design()
        design.stackup = [{"name": "dielectric 1", "type": "core", "thickness": 1.6, "epsilon_r": 4.2}]
        spec = AnalysisSpec(net_names=["RF"], frequency_start_hz=1e6, frequency_stop_hz=1e9)
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory) / "case"
            result = prepare_openems_case(design, spec, case)
            self.assertEqual(result["status"], "blocked")
            codes = {item["code"] for item in result["validation"]["errors"]}
            self.assertIn("OPENEMS_COPPER_STACKUP_REQUIRED", codes)
            self.assertFalse(case.exists())

    def test_nonphysical_documentation_layers_do_not_become_dielectrics(self):
        design = openems_design()
        design.stackup.insert(0, {"name": "F.SilkS", "type": "silkscreen"})
        design.stackup.append({"name": "B.Paste", "type": "solder paste"})
        spec = AnalysisSpec(net_names=["RF"], frequency_start_hz=1e6, frequency_stop_hz=1e9)
        with tempfile.TemporaryDirectory() as directory:
            result = prepare_openems_case(design, spec, Path(directory) / "case")
        self.assertEqual(result["status"], "prepared_review_required")

    def test_tampered_result_path_is_rejected(self):
        spec = AnalysisSpec(
            analysis_id="openems-tamper",
            mode="broadband_hf",
            net_names=["RF"],
            frequency_start_hz=1e6,
            frequency_stop_hz=1e9,
        )
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory) / "case"
            prepare_openems_case(openems_design(), spec, case)
            job_path = case / "job.json"
            job = json.loads(job_path.read_text(encoding="utf-8"))
            job["files"]["result"] = "../outside.json"
            job_path.write_text(json.dumps(job), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "outside the job directory"):
                run_openems_case(case, setup_only=True)

    def test_nonfinite_frequency_and_missing_selected_geometry_are_blocked(self):
        design = openems_design()
        spec = AnalysisSpec(net_names=["MISSING"], frequency_start_hz=math.nan, frequency_stop_hz=math.inf)
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory) / "case"
            result = prepare_openems_case(design, spec, case)
            codes = {item["code"] for item in result["validation"]["errors"]}
            self.assertIn("OPENEMS_FREQUENCY_INVALID", codes)
            self.assertIn("OPENEMS_SELECTED_GEOMETRY_REQUIRED", codes)
            self.assertFalse(case.exists())

    def test_default_job_name_ignores_untrusted_analysis_id(self):
        spec = AnalysisSpec(
            analysis_id="..\\..\\escaped",
            mode="broadband_hf",
            net_names=["RF"],
            frequency_start_hz=1e6,
            frequency_stop_hz=1e9,
        )
        with tempfile.TemporaryDirectory() as directory, patch(
            "python.spike_core.external_engines._default_job_base", return_value=Path(directory)
        ):
            result = prepare_openems_case(openems_design(), spec)
            case = Path(result["case_dir"])
            self.assertEqual(case.parent, Path(directory).resolve())
            self.assertNotIn("escaped", case.name)

    def test_runner_uses_trusted_source_over_isolated_stdin(self):
        spec = AnalysisSpec(
            analysis_id="openems-isolated",
            mode="broadband_hf",
            net_names=["RF"],
            frequency_start_hz=1e6,
            frequency_stop_hz=1e9,
        )
        validated = ExternalEngineDescriptor(
            id="external.openems",
            name="openEMS FDTD",
            role="test",
            license="GPL-3.0-or-later",
            homepage="https://docs.openems.de/",
            state="reference_validated",
        )
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory) / "case"
            prepare_openems_case(openems_design(), spec, case)
            (case / "engine-input" / "run_openems.py").write_text("raise RuntimeError('tampered')", encoding="utf-8")
            job = json.loads((case / "job.json").read_text(encoding="utf-8"))
            run_uuid = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
            (case / "engine-input" / "spike-openems.xml").write_text("<openEMS/>", encoding="utf-8")
            result_path = case / "engine-output" / "normalized-result.json"
            result_path.write_text(json.dumps({
                "contract": "spike/external-result/v1",
                "engine_id": "external.openems",
                "status": "setup_completed",
                "model_status": "approximate",
                "artifacts": ["engine-input/spike-openems.xml"],
                "mesh": {"resolution_mm": 0.5},
                "run_binding": {
                    "run_id": str(run_uuid),
                    "job_id": spec.analysis_id,
                    "input_digest": job["integrity"]["payload_sha256"],
                    "mesh_resolution_mm": 0.5,
                    "frequency_start_hz": 1e6,
                    "frequency_stop_hz": 1e9,
                    "frequency_points": spec.frequency_points,
                },
            }), encoding="utf-8")
            with patch("python.spike_core.external_engines.uuid.uuid4", return_value=run_uuid), patch(
                "python.spike_core.external_engines._openems_descriptor", return_value=validated
            ), patch(
                "python.spike_core.external_engines._openems_python", return_value=sys.executable
            ), patch("python.spike_core.external_engines._run_isolated_python", return_value={
                "returncode": 0,
                "timed_out": False,
                "quota_exceeded": False,
                "log_truncated": False,
            }) as spawned:
                result = run_openems_case(case, setup_only=True)

        self.assertEqual(result["status"], "setup_completed")
        self.assertIn(b"Generated by SPIKE", spawned.call_args.args[1])
        self.assertIn(b"SPIKE_GEOMETRY_SNAPSHOT", spawned.call_args.args[1])
        self.assertEqual(spawned.call_args.args[2][:2], ["--job", str(case)])
        self.assertNotIn(str(case / "engine-input" / "run_openems.py"), spawned.call_args.args[2])

    def test_isolated_runner_does_not_import_job_local_modules(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            output.mkdir()
            (root / "json.py").write_text("raise RuntimeError('job-local import executed')", encoding="utf-8")
            log = root / "worker.log"
            process = _run_isolated_python(
                sys.executable,
                b"import json; print(json.__file__)",
                [],
                cwd=root,
                environment=dict(os.environ),
                log_path=log,
                output_root=output,
                timeout_seconds=5,
            )
            diagnostic = log.read_text(encoding="utf-8")

        self.assertEqual(process["returncode"], 0)
        self.assertNotIn(str(root / "json.py"), diagnostic)
        self.assertNotIn("job-local import executed", diagnostic)

    def test_run_reports_unavailable_engine_without_spawning(self):
        spec = AnalysisSpec(
            analysis_id="openems-unavailable",
            mode="broadband_hf",
            net_names=["RF"],
            frequency_start_hz=1e6,
            frequency_stop_hz=1e9,
        )
        unavailable = ExternalEngineDescriptor(
            id="external.openems",
            name="openEMS FDTD",
            role="test",
            license="GPL-3.0-or-later",
            homepage="https://docs.openems.de/",
            reason="not installed",
        )
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory) / "case"
            prepare_openems_case(openems_design(), spec, case)
            with patch("python.spike_core.external_engines._openems_descriptor", return_value=unavailable):
                result = run_openems_case(case, setup_only=True)
        self.assertEqual(result["status"], "solver_unavailable")

    def test_job_or_geometry_tampering_requires_case_repreparation(self):
        spec = AnalysisSpec(net_names=["RF"], frequency_start_hz=1e6, frequency_stop_hz=1e9)
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"SPIKE_CASE_INTEGRITY_KEY": str(Path(directory) / "case.key")}
        ):
            case = Path(directory) / "case"
            prepare_openems_case(openems_design(), spec, case)
            geometry_path = case / "geometry.json"
            geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
            geometry["conductors"]["tracks"] = []
            geometry_path.write_text(json.dumps(geometry), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "changed after validation"):
                run_openems_case(case, setup_only=True)

    def test_nonphysical_dielectric_and_unbounded_mesh_are_blocked(self):
        design = openems_design()
        design.stackup[1]["epsilon_r"] = math.nan
        spec = AnalysisSpec(net_names=["RF"], frequency_start_hz=1e6, frequency_stop_hz=1e9)
        with tempfile.TemporaryDirectory() as directory:
            result = prepare_openems_case(design, spec, Path(directory) / "bad-material")
            codes = {item["code"] for item in result["validation"]["errors"]}
            self.assertIn("OPENEMS_DIELECTRIC_INVALID", codes)

            result = prepare_openems_case(
                openems_design(), spec, Path(directory) / "bad-mesh", {"mesh_resolution_mm": 0.0001}
            )
            codes = {item["code"] for item in result["validation"]["errors"]}
            self.assertIn("OPENEMS_CELL_BUDGET_EXCEEDED", codes)

    def test_ports_must_terminate_on_distinct_exported_conductors(self):
        design = openems_design()
        design.nets.append({"id": "2", "name": "GND"})
        design.tracks.append({
            "id": "track-2",
            "start": [0.0, 2.0],
            "end": [20.0, 2.0],
            "width": 1.0,
            "layer": "F.Cu",
            "net_name": "GND",
        })
        valid_port = {
            "start": [10.0, 0.0, 0.0],
            "stop": [10.0, 2.0, 0.0],
            "direction": "y",
            "impedance_ohm": 50,
            "excite": True,
        }
        spec = AnalysisSpec(
            net_names=["RF", "GND"],
            frequency_start_hz=1e6,
            frequency_stop_hz=1e9,
            options={"ports": [valid_port]},
        )
        with tempfile.TemporaryDirectory() as directory:
            result = prepare_openems_case(design, spec, Path(directory) / "valid-port")
            self.assertNotIn("OPENEMS_PORT_CONDUCTOR_REQUIRED", {item["code"] for item in result["validation"]["errors"]})

            invalid = AnalysisSpec(**{**spec.to_dict(), "options": {"ports": [{**valid_port, "stop": [1000.0, 1000.0, 0.0]}]}})
            result = prepare_openems_case(design, invalid, Path(directory) / "invalid-port")
            codes = {item["code"] for item in result["validation"]["errors"]}
            self.assertIn("OPENEMS_PORT_CONDUCTOR_REQUIRED", codes)

    def test_normalized_result_rejects_wrong_engine_shape_and_nonfinite_values(self):
        root = Path(__file__).resolve().parent
        ports = [{"excite": True}, {"excite": False}]
        valid = {
            "contract": "spike/external-result/v1",
            "engine_id": "external.openems",
            "status": "completed",
            "model_status": "approximate",
            "frequency_hz": [1e6, 2e6],
            "s_parameters": {
                "s11": {"real": [0.1, 0.2], "imag": [0.0, 0.0]},
                "s21": {"real": [0.8, 0.7], "imag": [0.0, 0.0]},
            },
            "artifacts": [Path(__file__).name],
            "mesh": {"resolution_mm": 0.5},
            "run_binding": {
                "run_id": "run-1",
                "job_id": "job-1",
                "input_digest": "digest-1",
                "mesh_resolution_mm": 0.5,
                "frequency_start_hz": 1e6,
                "frequency_stop_hz": 2e6,
                "frequency_points": 2,
            },
        }
        expected = {
            "setup_only": False,
            "expected_points": 2,
            "expected_start_hz": 1e6,
            "expected_stop_hz": 2e6,
            "expected_job_id": "job-1",
            "expected_input_digest": "digest-1",
            "expected_run_id": "run-1",
            "ports": ports,
            "root": root,
        }
        self.assertEqual(
            validate_normalized_result(valid, **expected)["status"],
            "completed",
        )
        invalid = dict(valid, engine_id="wrong.engine")
        with self.assertRaisesRegex(ValueError, "engine ID"):
            validate_normalized_result(invalid, **expected)
        invalid = {**valid, "frequency_hz": [1e6, math.nan]}
        with self.assertRaisesRegex(ValueError, "finite"):
            validate_normalized_result(invalid, **expected)
        invalid = {**valid, "run_binding": {**valid["run_binding"], "run_id": "stale-run"}}
        with self.assertRaisesRegex(ValueError, "does not belong"):
            validate_normalized_result(invalid, **expected)
        invalid = {**valid, "frequency_hz": [1e6, 1.5e6]}
        with self.assertRaisesRegex(ValueError, "requested sweep"):
            validate_normalized_result(invalid, **expected)

    def test_strict_json_rejects_nan(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            path.write_text('{"frequency_hz":[NaN]}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Non-finite JSON"):
                load_strict_json(path)

    def test_strict_json_enforces_a_preparse_byte_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oversized.json"
            path.write_text('{"value":"0123456789"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "byte input limit"):
                load_strict_json(path, max_bytes=8, label="test JSON")


if __name__ == "__main__":
    unittest.main()
