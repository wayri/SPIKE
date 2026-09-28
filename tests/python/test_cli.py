import contextlib
import hashlib
import json
import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from python.spike_core.cli import (
    EXIT_ANALYSIS,
    EXIT_OK,
    EXIT_VALIDATION,
    FIELD_CIRCUIT_PACKAGE_CONTRACT,
    _project_request,
    execute_request,
    main,
)
from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.project_package import write_spike_package


class SpikeCliTests(unittest.TestCase):
    def test_version_matches_application_package(self):
        from python.spike_core import __version__
        output = StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as result:
            main(["--version"])
        self.assertEqual(result.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), f"SPIKE CLI {__version__}")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.state_environment = patch.dict(os.environ, {"SPIKE_STATE_HOME": str(self.root / "state")})
        self.state_environment.start()
        design = DesignIR(
            name="cli fixture",
            source_format="fixture",
            source_path=str(self.root / "fixture.json"),
            layers=[{"name": "F.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            tracks=[{"start": [0, 0], "end": [10, 0], "width": 1, "layer": "F.Cu", "net_name": "VCC"}],
            stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
        )
        self.design_path = self.root / "fixture.json"
        self.design_path.write_text(json.dumps(design.to_dict()), encoding="utf-8")

    def tearDown(self):
        self.state_environment.stop()
        self.temporary.cleanup()

    def invoke(self, *arguments):
        output = StringIO()
        with contextlib.redirect_stdout(output):
            code = main(arguments)
        return code, json.loads(output.getvalue())

    def test_inspect_returns_normalized_counts(self):
        code, result = self.invoke("inspect", str(self.design_path))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(result["counts"]["tracks"], 1)
        self.assertEqual(result["counts"]["nets"], 1)

    def test_setup_commands_enforce_two_gb_solver_memory_minimum(self):
        for command, frequency_args in (
            ("setup-dc", ()),
            ("setup-ac", ("--start-hz", "1000", "--stop-hz", "1000000", "--points", "3")),
        ):
            code, result = self.invoke(
                command,
                str(self.design_path),
                "--net", "VCC",
                "--source", "0,0,F.Cu,5",
                "--load", "10,0,F.Cu,1",
                "--memory-limit-gb", "1",
                *frequency_args,
            )
            self.assertNotEqual(code, EXIT_OK)
            self.assertIn("at least 2 GB", result["error"])

    def test_capability_ledger_command_exposes_native_release_gates(self):
        code, result = self.invoke("capability-ledger")
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(result["contract"], "spike/native-capability-ledger/v1")
        self.assertTrue(result["policy"]["released_ui_requires_native_owner"])

    def test_native_mna_validate_and_run_commands(self):
        request_path = self.root / "native-mna.json"
        request_path.write_text(json.dumps({
            "contract": "spike/native-mna-request/v1",
            "request_id": "cli-mna",
            "ground_node": "0",
            "analysis": {"mode": "operating_point"},
            "elements": [
                {"id": "V1", "type": "voltage_source", "positive_node": "out", "negative_node": "0", "dc_value": 5.0},
                {"id": "R1", "type": "resistor", "positive_node": "out", "negative_node": "0", "resistance_ohm": 1000.0},
            ],
        }), encoding="utf-8")

        code, validation = self.invoke("native-mna-validate", str(request_path))
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(validation["valid"])
        code, result = self.invoke("native-mna-run", str(request_path))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(result["status"], "completed")
        self.assertAlmostEqual(result["data"]["element_power_w"]["R1"], 0.025)

    def test_native_workspace_compile_and_run_commands(self):
        circuit_design_path = self.root / "native-workspace-design.json"
        design_data = json.loads(self.design_path.read_text(encoding="utf-8"))
        design_data["components"] = [{"id": "v1", "reference": "V1"}, {"id": "r1", "reference": "R1"}]
        design_data["pads"] = [
            {"id": "v1p", "ref": "V1", "name": "1", "net_name": "VCC"},
            {"id": "v1n", "ref": "V1", "name": "2", "net_name": "GND"},
            {"id": "r1p", "ref": "R1", "name": "1", "net_name": "VCC"},
            {"id": "r1n", "ref": "R1", "name": "2", "net_name": "GND"},
        ]
        circuit_design_path.write_text(json.dumps(design_data), encoding="utf-8")
        workspace_path = self.root / "native-workspace.json"
        workspace_path.write_text(json.dumps({
            "contract": "spike/spice-workspace/v1",
            "name": "CLI native workspace",
            "domain": "pi",
            "ground_node": "GND",
            "models": [
                {
                    "id": "source", "kind": "primitive", "primitive": "voltage_source",
                    "pins": ["p", "n"], "value": "5", "origin": "built_in",
                    "parameters": {"dc_value": 5.0},
                },
                {
                    "id": "load", "kind": "primitive", "primitive": "resistor",
                    "pins": ["p", "n"], "value": "1000", "origin": "built_in",
                    "parameters": {"resistance_ohm": 1000.0},
                },
            ],
            "assignments": [
                {
                    "id": "source-binding", "component_ref": "V1", "model_id": "source", "enabled": True,
                    "pin_bindings": [
                        {"model_pin": "p", "pad_id": "v1p", "circuit_node": "VCC"},
                        {"model_pin": "n", "pad_id": "v1n", "circuit_node": "GND"},
                    ],
                },
                {
                    "id": "load-binding", "component_ref": "R1", "model_id": "load", "enabled": True,
                    "pin_bindings": [
                        {"model_pin": "p", "pad_id": "r1p", "circuit_node": "VCC"},
                        {"model_pin": "n", "pad_id": "r1n", "circuit_node": "GND"},
                    ],
                },
            ],
            "parasitics": [],
            "analysis": {"mode": "operating_point"},
        }), encoding="utf-8")

        code, compiled = self.invoke("native-workspace-compile", str(circuit_design_path), str(workspace_path))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(compiled["status"], "ready")
        code, solved = self.invoke("native-workspace-run", str(circuit_design_path), str(workspace_path))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(solved["status"], "completed")
        self.assertAlmostEqual(solved["result"]["data"]["node_voltage_v"]["VCC"], 5.0)

    def test_pi_release_qualification_is_machine_readable_and_fail_closed(self):
        runtime_path = self.root / "runtime-qualification.json"
        runtime_path.write_text(json.dumps({
            "contract": "spike/release-runtime-qualification/v1",
            "status": "passed",
            "summary": {"total": 1, "passed": 1, "failed": 0},
            "source_snapshot_digest": "same",
            "packaged_snapshot_digest": "same",
        }), encoding="utf-8")
        benchmark_path = self.root / "benchmarks.json"
        benchmark_path.write_text(json.dumps({
            "contract": "spike/solver-benchmark-report/v1",
            "status": "passed",
            "summary": {"total": 1, "passed": 1, "failed": 0, "skipped": 0},
        }), encoding="utf-8")

        code, report = self.invoke(
            "pi-release-qualification",
            "--runtime-report", str(runtime_path),
            "--benchmark-report", str(benchmark_path),
        )
        self.assertEqual(code, EXIT_VALIDATION)
        self.assertEqual(report["contract"], "spike/pi-release-qualification/v1")
        self.assertFalse(report["deployable"])
        self.assertIn("workflow.pi.ac_rlcg", report["blocked_checks"])

    def test_pi_release_qualification_runs_current_benchmarks_when_report_is_omitted(self):
        runtime_path = self.root / "runtime-qualification.json"
        runtime_path.write_text(json.dumps({
            "contract": "spike/release-runtime-qualification/v1",
            "status": "passed",
            "summary": {"total": 1, "passed": 1, "failed": 0},
            "source_snapshot_digest": "same",
            "packaged_snapshot_digest": "same",
        }), encoding="utf-8")

        code, report = self.invoke(
            "pi-release-qualification",
            "--runtime-report", str(runtime_path),
        )
        self.assertEqual(code, EXIT_VALIDATION)
        benchmark_check = next(
            item for item in report["checks"]
            if item["id"] == "validation.native_benchmarks"
        )
        self.assertEqual(benchmark_check["status"], "passed")
        self.assertEqual(benchmark_check["evidence"]["source"], "explicit_report")
        self.assertGreaterEqual(benchmark_check["evidence"]["summary"]["passed"], 15)
        dc_check = next(
            item for item in report["checks"]
            if item["id"] == "workflow.pi.dc_conduction"
        )
        self.assertTrue(all(
            status == "passed"
            for status in dc_check["evidence"]["benchmark_status"].values()
        ))

    def test_v3_package_can_be_inspected_and_used_as_a_design(self):
        design = json.loads(self.design_path.read_text(encoding="utf-8"))
        source_bytes = self.design_path.read_bytes()
        source_digest = hashlib.sha256(source_bytes).hexdigest()
        design_v2 = DesignIRV2.from_v1(DesignIR(**design)).to_dict()
        design_v2["source"]["source_digest"] = source_digest
        design_v2["source"]["artifact_path"] = f"package:sources/{source_digest}.json"
        package_path = self.root / "fixture.spike"
        write_spike_package(package_path, {
            "project": {"id": "cli-project", "name": "CLI project"},
            "design_ir": design_v2,
            "analyses": {},
            "results": {},
        }, source_artifacts={"fixture.json": source_bytes})

        code, package = self.invoke("project-inspect", str(package_path))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(package["manifest"]["format"], "spike-project-package/v3")
        self.assertEqual(package["design"]["contract"], "spike/design-ir/v2")

        code, inspected = self.invoke("inspect", str(package_path))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(inspected["counts"]["tracks"], 1)

    def test_v3_project_analysis_binds_unique_active_board_scope(self):
        design = json.loads(self.design_path.read_text(encoding="utf-8"))
        source_bytes = self.design_path.read_bytes()
        source_digest = hashlib.sha256(source_bytes).hexdigest()
        design_v2 = DesignIRV2.from_v1(DesignIR(**design)).to_dict()
        design_v2["source"]["source_digest"] = source_digest
        design_v2["source"]["artifact_path"] = f"package:sources/{source_digest}.json"
        package_path = self.root / "assembly-fixture.spike"
        write_spike_package(package_path, {
            "project": {"id": "cli-assembly", "name": "CLI assembly"},
            "design_ir": design_v2,
            "assembly_ir": {
                "contract": "spike/assembly-ir/v1", "assembly_id": "cli-assembly", "name": "CLI assembly",
                "frame": {"frame_id": "assembly"},
                "boards": [{"id": "board-a", "name": "Board A", "design_id": design_v2["design_id"], "frame": {"frame_id": "board-a-frame", "parent_frame_id": "assembly"}}],
                "harnesses": [], "connector_mappings": [], "rigid_flex_links": [], "parts": [],
                "materials": [], "thermal_contacts": [], "electrical_bonds": [],
            },
            "analyses": {}, "results": {},
        }, source_artifacts={"fixture.json": source_bytes})
        request = _project_request(package_path)
        scope = request["assembly_scope"]
        self.assertEqual(scope["contract"], "spike/assembly-analysis-scope/v1")
        self.assertEqual(scope["active_board_id"], "board-a")
        self.assertEqual(scope["active_design_id"], design_v2["design_id"])

    def test_legacy_project_migrates_to_v3_from_cli(self):
        legacy_path = self.root / "legacy.spike.json"
        output_path = self.root / "legacy.spike"
        legacy_path.write_text(json.dumps({
            "format": "spike-project-package/v2",
            "project": {"name": "legacy.spike"},
            "design": {
                "source_file": "legacy.kicad_pcb",
                "source_board": "(kicad_pcb (version 20240108) (generator pcbnew) (layers (0 \"F.Cu\" signal)) (net 0 \"\"))",
            },
            "analysis": {"mode": "DC IR Drop", "pi_setup": {}},
        }), encoding="utf-8")

        code, result = self.invoke("project-migrate", str(legacy_path), str(output_path))
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(output_path.is_file())
        self.assertEqual(result["manifest"]["format"], "spike-project-package/v3")

    def test_acceleration_and_external_engine_catalog_commands(self):
        code, accelerators = self.invoke("accelerators")
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(accelerators["contract"], "spike/acceleration-catalog/v1")
        self.assertIn("scipy-superlu", {item["id"] for item in accelerators["backends"]})

        code, engines = self.invoke("external-engines")
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(engines["contract"], "spike/external-engine-catalog/v1")
        self.assertIn("external.openems", {item["id"] for item in engines["engines"]})
        self.assertIn("external.sparselizard", {item["id"] for item in engines["engines"]})
        elmer = next(item for item in engines["engines"] if item["id"] == "external.elmer")
        self.assertEqual(elmer["capabilities"], [])
        self.assertIn("register", elmer["actions"])
        self.assertNotIn("run", elmer["actions"])

    def test_sparselizard_validation_status_is_machine_readable_and_fail_closed(self):
        with patch(
            "python.spike_core.sparselizard_validation.detect_sparselizard_runtime",
            return_value={"available": False, "signature_verified": False, "manifest": {}},
        ):
            code, report = self.invoke(
                "sparselizard-validation-status", "--evidence-root", str(self.root / "missing-evidence"),
            )
        self.assertEqual(code, EXIT_VALIDATION)
        self.assertEqual(report["contract"], "spike/sparselizard-validation-report/v1")
        self.assertEqual(report["status"], "blocked")

    def test_openems_reference_benchmark_command_reports_convergence(self):
        def fixture_run(output_directory, *, mesh_resolution_mm, max_timesteps, timeout_seconds):
            return {
                "status": "passed",
                "mesh_resolution_mm": mesh_resolution_mm,
                "resonance_hz": 2.4e9,
                "maximum_directivity_linear": [4.5],
                "case_dir": str(output_directory),
            }

        with patch("python.spike_core.cli.run_patch_antenna_benchmark", side_effect=fixture_run):
            code, result = self.invoke(
                "openems-benchmark",
                "--case-root", str(self.root / "openems-reference"),
                "--mesh-resolution-mm", "5", "4", "3",
            )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(result["contract"], "spike/openems-benchmark-suite/v1")
        self.assertEqual(result["convergence"]["status"], "passed")
        self.assertEqual(len(result["runs"]), 3)

    def test_environment_profile_list_materialize_and_validate_commands(self):
        code, catalog = self.invoke("environment-list")
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(catalog["contract"], "spike/environment-profile-catalog/v1")
        self.assertEqual(catalog["supported_domains"], ["pi", "si", "thermal", "emi"])
        self.assertIn("automotive", {item["profile_id"] for item in catalog["profiles"]})

        overrides_path = self.root / "environment-overrides.json"
        overrides_path.write_text(json.dumps({
            "physical": {"thermal": {"ambient_temperature_k": 360.0, "initial_temperature_k": 360.0}},
        }), encoding="utf-8")
        code, profile = self.invoke(
            "environment-materialize", "preset", "automotive", "--overrides", str(overrides_path),
        )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(profile["contract"], "spike/environment-profile/v1")
        self.assertEqual(profile["physical"]["thermal"]["ambient_temperature_k"], 360.0)
        self.assertFalse(profile["validity"]["certification_claimed"])

        profile_path = self.root / "automotive-environment.json"
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        code, validation = self.invoke(
            "environment-validate", str(profile_path), "--domain", "pi", "--domain", "thermal",
        )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(validation["contract"], "spike/environment-profile-validation/v1")
        self.assertTrue(validation["can_supply_solver_inputs"])
        self.assertEqual(validation["requested_domains"], ["pi", "thermal"])
        self.assertEqual(validation["certification"]["status"], "not_assessed")
        self.assertFalse(validation["certification"]["claimed"])

    def test_environment_materialize_user_profile_keeps_readiness_and_certification_explicit(self):
        physical_path = self.root / "user-environment-physical.json"
        physical_path.write_text(json.dumps({
            "thermal": {"ambient_temperature_k": 300.0},
        }), encoding="utf-8")
        code, profile = self.invoke(
            "environment-materialize", "user", "bench-chamber", "--name", "Bench chamber",
            "--physical", str(physical_path), "--source-title", "Chamber data sheet",
            "--source-locator", "internal:chamber-7",
        )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(profile["profile_id"], "bench-chamber")
        self.assertEqual(profile["provenance"]["origin"], "user")
        self.assertEqual(profile["provenance"]["sources"][0]["title"], "Chamber data sheet")

        profile_path = self.root / "user-environment.json"
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        code, validation = self.invoke("environment-validate", str(profile_path), "--domain", "pi")
        self.assertEqual(code, 3)
        self.assertFalse(validation["can_supply_solver_inputs"])
        self.assertEqual(validation["certification"]["status"], "not_assessed")
        self.assertFalse(validation["certification"]["claimed"])

    def test_solver_manager_register_tune_recommend_and_forget_commands(self):
        sparse_root = self.root / "sparselizard"
        (sparse_root / "src").mkdir(parents=True)
        (sparse_root / "CMakeLists.txt").write_text("project(sparselizard)\n", encoding="utf-8")
        code, registered = self.invoke("solver-register", "external.sparselizard", str(sparse_root))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(registered["registration"]["path"], str(sparse_root.resolve()))

        code, tuned = self.invoke("solver-tune", "native.sparse", "linear_backend=\"superlu\"", "thread_count=4")
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(tuned["configured"]["thread_count"], 4)

        code, recommendation = self.invoke("solver-recommend", "dc_pi")
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(recommendation["workload"]["recommended"]["id"], "spike.routed_dc")

        code, removed = self.invoke("solver-unregister", "external.sparselizard")
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(removed["removed"])
        self.assertTrue(sparse_root.exists())

    def test_openems_prepare_cli_writes_an_inspectable_case(self):
        request_path = self.root / "openems-request.json"
        case_path = self.root / "openems-case"
        request_path.write_text(json.dumps({
            "contract": "spike/analysis-request/v1",
            "design": json.loads(self.design_path.read_text(encoding="utf-8")),
            "spec": {
                "contract": "spike/v1",
                "analysis_id": "cli-openems",
                "mode": "broadband_hf",
                "net_names": ["VCC"],
                "frequency_start_hz": 1e6,
                "frequency_stop_hz": 1e9,
                "frequency_points": 21,
                "options": {"ports": []},
            },
        }), encoding="utf-8")

        code, result = self.invoke(
            "openems-prepare", str(request_path),
            "--case-dir", str(case_path),
            "--mesh-resolution-mm", "0.25",
        )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(result["status"], "prepared_review_required")
        self.assertTrue((case_path / "job.json").is_file())
        job = json.loads((case_path / "job.json").read_text(encoding="utf-8"))
        self.assertEqual(job["options"]["mesh_resolution_mm"], 0.25)

    def test_emi_preflight_and_screen_commands_use_versioned_setup(self):
        setup_path = self.root / "emi-setup.json"
        setup_path.write_text(json.dumps({
            "contract": "spike/emi-setup/v1",
            "selected_nets": ["VCC"],
            "return_nets": [],
            "requested_analyses": ["conducted_screening"],
            "frequency": {"start_hz": 1e6, "stop_hz": 1e9, "points": 101},
            "environment": {"kind": "free_space"},
            "radiated_emissions_standard": {"id": "cispr-32-2015-amd1-2019", "classification": "B"},
            "mesh": {"resolution_mm": 0.25, "padding_cells": 8},
            "max_solver_time_s": 3600,
            "excitation": {"mode": "prepass_results", "ports": []},
            "net_metrics": [{
                "net": "VCC", "source": "measured", "dv_dt_v_per_s": 1e8,
                "di_dt_a_per_s": 2e7, "peak_current_a": 1, "loop_area_mm2": 5,
                "return_discontinuities": 0,
            }],
        }), encoding="utf-8")

        code, preflight = self.invoke("emi-preflight", str(self.design_path), str(setup_path))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(preflight["contract"], "spike/emi-preflight/v1")
        self.assertTrue(preflight["can_screen"])
        self.assertEqual(preflight["reference_standard"]["comparison_status"], "unavailable")
        self.assertFalse(preflight["reference_standard"]["compliance_available"])

        code, screened = self.invoke("emi-screen", str(self.design_path), str(setup_path))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(screened["status"], "completed_screening_only")
        self.assertEqual(screened["screening"]["recommended_nets"][0]["net"], "VCC")
        self.assertFalse(screened["provenance"]["compliance_prediction"])

    def test_dc_supports_multiple_terminals_and_saves_request(self):
        request_path = self.root / "request.json"
        code, result = self.invoke(
            "analyze-dc", str(self.design_path),
            "--net", "VCC",
            "--source", "0,0,F.Cu,5,0.01,0.02",
            "--load", "10,0,F.Cu,0.4",
            "--load", "10,0,F.Cu,0.6",
            "--save-request", str(request_path),
        )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["summary"]["geometry_counts"]["contact"], 1)
        self.assertTrue(request_path.is_file())

    def test_staged_dc_setup_preflight_and_run(self):
        request_path = self.root / "staged-request.json"
        code, request = self.invoke(
            "setup-dc", str(self.design_path),
            "--net", "VCC",
            "--source", "0,0,F.Cu,5",
            "--load", "10,0,F.Cu,1",
            "--via-model", "plated_cylinder",
            "--via-plating-mm", "0.03",
            "--save-request", str(request_path),
        )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(request["contract"], "spike/analysis-request/v1")
        self.assertEqual(request["spec"]["mesh"]["via_model"], "plated_cylinder")
        self.assertEqual(request["spec"]["mesh"]["via_plating_thickness_mm"], 0.03)

        code, preflight = self.invoke("preflight", str(request_path))
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(preflight["can_solve"])

        code, result = self.invoke("run", str(request_path))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(result["status"], "completed")

    def test_transient_setup_exposes_time_controls_and_waveforms(self):
        code, request = self.invoke(
            "setup-transient", str(self.design_path),
            "--net", "VCC",
            "--source", "0,0,F.Cu,5",
            "--load", "10,0,F.Cu,1",
            "--source-waveform", "constant",
            "--load-waveform", "step,0,2e-6,1e-6",
            "--stop-time-s", "8e-6",
            "--time-step-s", "2e-7",
            "--output-decimation", "5",
            "--output-decimation-mode", "manual",
            "--playback-fps", "18",
            "--max-solver-time-s", "30",
            "--memory-budget-mb", "256",
            "--capacitance-model", "none",
        )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(request["spec"]["mode"], "transient")
        self.assertEqual(request["spec"]["solver_id"], "spike.peec_rl_transient")
        self.assertEqual(request["spec"]["loads"][0]["profile"]["kind"], "step")
        self.assertEqual(request["spec"]["transient"]["output_decimation"], 5)
        self.assertEqual(request["spec"]["transient"]["output_decimation_mode"], "manual")
        self.assertEqual(request["spec"]["transient"]["time_step_mode"], "manual")
        self.assertEqual(request["spec"]["transient"]["memory_budget_mb"], 256)
        self.assertEqual(request["spec"]["transient"]["playback_fps"], 18)

    def test_transient_setup_can_recommend_time_step(self):
        code, request = self.invoke(
            "setup-transient", str(self.design_path),
            "--net", "VCC",
            "--source", "0,0,F.Cu,5",
            "--load", "10,0,F.Cu,1",
            "--load-waveform", "step,0,2e-6,1e-6",
            "--stop-time-s", "8e-6",
        )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(request["spec"]["transient"]["time_step_mode"], "auto")
        self.assertGreater(request["spec"]["transient"]["time_step_s"], 0)

    def test_cli_runs_an_isolated_secondary_return_loop(self):
        design = DesignIR(
            name="isolated cli fixture",
            source_format="fixture",
            layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
            nets=[{"id": 1, "name": "VCC_ISO"}, {"id": 2, "name": "GND_ISO"}],
            tracks=[
                {"id": "supply", "start": [0, 0], "end": [10, 0], "width": 1, "layer": "F.Cu", "net_name": "VCC_ISO"},
                {"id": "return", "start": [0, 2], "end": [10, 2], "width": 1, "layer": "B.Cu", "net_name": "GND_ISO"},
            ],
            stackup=[
                {"name": "F.Cu", "type": "copper", "thickness": 0.035},
                {"name": "dielectric", "type": "core", "thickness": 1.53},
                {"name": "B.Cu", "type": "copper", "thickness": 0.035},
            ],
        )
        path = self.root / "isolated.json"
        path.write_text(json.dumps(design.to_dict()), encoding="utf-8")
        code, result = self.invoke(
            "analyze-dc", str(path),
            "--net", "VCC_ISO",
            "--source", "0,0,F.Cu,5",
            "--load", "10,0,F.Cu,1",
            "--return-net", "GND_ISO",
            "--return-source", "0,2,B.Cu,0",
            "--return-load", "10,2,B.Cu,1",
            "--return-mode", "isolated_secondary",
            "--domain-id", "secondary-1",
        )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(result["summary"]["return_path_count"], 1)
        self.assertEqual(result["summary"]["isolated_domain_count"], 1)
        self.assertTrue(result["networks"]["return_path"]["galvanically_isolated"])

    def test_batch_stops_or_continues_using_result_status(self):
        request = {
            "contract": "spike/analysis-request/v1",
            "design": json.loads(self.design_path.read_text(encoding="utf-8")),
            "spec": {
                "mode": "dc",
                "net_names": ["VCC"],
                "sources": [{"position_mm": [0, 0], "layer": "F.Cu", "voltage_v": 5}],
                "loads": [{"position_mm": [10, 0], "layer": "F.Cu", "current_a": 1}],
            },
        }
        batch_path = self.root / "batch.json"
        batch_path.write_text(json.dumps({"contract": "spike/analysis-batch/v1", "jobs": [
            {"id": "pass-1", **request},
            {"id": "pass-2", **request},
        ]}), encoding="utf-8")
        code, result = self.invoke("run", str(batch_path), "--continue-on-error")
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(result["completed"], 2)

    def test_execute_request_preflights_once_before_solver_dispatch(self):
        request = {
            "contract": "spike/analysis-request/v1",
            "design": json.loads(self.design_path.read_text(encoding="utf-8")),
            "spec": {"mode": "dc"},
            "assembly_scope": {"contract": "test-scope"},
        }
        calls = []

        def response(method, params):
            calls.append((method, params))
            if method == "preflight_analysis":
                return {"result": {"contract": "spike/preflight/v1", "can_solve": True}}
            return {"result": {"contract": "spike/analysis-result/v1", "status": "completed"}}

        with patch("python.spike_core.cli._response", side_effect=response):
            result = execute_request(request)

        self.assertEqual(result["status"], "completed")
        self.assertEqual([method for method, _ in calls], ["preflight_analysis", "run_analysis"])
        self.assertTrue(all(params["assembly_scope"] == {"contract": "test-scope"} for _, params in calls))

    def test_execute_request_returns_blocked_preflight_without_solver_dispatch(self):
        request = {
            "contract": "spike/analysis-request/v1",
            "design": json.loads(self.design_path.read_text(encoding="utf-8")),
            "spec": {"mode": "dc"},
        }
        blocked = {
            "contract": "spike/preflight/v1",
            "status": "blocked",
            "can_solve": False,
            "issues": [{"code": "SPIKE-BE-VAL-0001"}],
        }

        with patch("python.spike_core.cli._response", return_value={"result": blocked}) as response:
            result = execute_request(request)

        self.assertEqual(result, blocked)
        response.assert_called_once()
        self.assertEqual(response.call_args.args[0], "preflight_analysis")

    def test_report_and_comparison_workflows(self):
        _, result = self.invoke(
            "analyze-dc", str(self.design_path),
            "--net", "VCC",
            "--source", "0,0,F.Cu,5",
            "--load", "10,0,F.Cu,1",
        )
        result_path = self.root / "result.json"
        result_path.write_text(json.dumps(result), encoding="utf-8")
        report_path = self.root / "report.html"
        code, report = self.invoke("report", str(result_path), "--report-format", "html", "--report-output", str(report_path))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(report["status"], "completed")
        self.assertIn("SPIKE Analysis Report", report_path.read_text(encoding="utf-8"))

        pdf_path = self.root / "report.pdf"
        code, report = self.invoke("report", str(result_path), "--report-format", "pdf", "--report-output", str(pdf_path))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(report["format"], "pdf")
        self.assertTrue(pdf_path.read_bytes().startswith(b"%PDF-"))

        code, comparison = self.invoke("compare", str(result_path), str(result_path))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(comparison["status"], "pass")

        changed = dict(result)
        changed["summary"] = dict(result["summary"])
        changed["summary"]["max_voltage_drop_v"] *= 2
        changed_path = self.root / "changed.json"
        changed_path.write_text(json.dumps(changed), encoding="utf-8")
        code, comparison = self.invoke("compare", str(result_path), str(changed_path))
        self.assertEqual(code, EXIT_ANALYSIS)
        self.assertEqual(comparison["status"], "regression")

    def test_ac_report_exports_impedance_sweep(self):
        result = {
            "status": "completed",
            "model_status": "approximate",
            "mode": "ac",
            "summary": {},
            "issues": [],
            "provenance": {"solver": "test"},
            "networks": {"parasitics": [{
                "net": "VCC",
                "source_node": 1,
                "sink_node": 2,
                "impedance": [{
                    "frequency_hz": 1_000_000,
                    "resistance_ohm": 0.012,
                    "reactance_ohm": 0.034,
                    "magnitude_ohm": 0.0360555,
                    "phase_deg": 70.56,
                }],
            }]},
        }
        result_path = self.root / "ac-result.json"
        result_path.write_text(json.dumps(result), encoding="utf-8")
        csv_path = self.root / "ac-result.csv"
        html_path = self.root / "ac-result.html"

        code, _ = self.invoke("report", str(result_path), "--report-format", "csv", "--report-output", str(csv_path))
        self.assertEqual(code, EXIT_OK)
        csv_text = csv_path.read_text(encoding="utf-8")
        self.assertIn("frequency_hz,resistance_ohm,reactance_ohm,magnitude_ohm,phase_deg", csv_text)
        self.assertIn("1000000", csv_text)

        code, _ = self.invoke("report", str(result_path), "--report-format", "html", "--report-output", str(html_path))
        self.assertEqual(code, EXIT_OK)
        html_text = html_path.read_text(encoding="utf-8")
        self.assertIn("Frequency-dependent impedance", html_text)
        self.assertIn("0.0360555", html_text)

    def test_batch_report_exports_each_job_and_preserves_failures(self):
        batch = {
            "contract": "spike/analysis-batch-result/v1",
            "status": "failed",
            "results": [
                {
                    "index": 0,
                    "id": "rail-dc",
                    "result": {
                        "status": "completed",
                        "mode": "dc",
                        "model_status": "approximate",
                        "summary": {"net_names": ["VCC"], "max_voltage_drop_v": 0.004},
                        "issues": [],
                        "provenance": {"solver": "spike.dc"},
                    },
                },
                {"index": 1, "id": "rail-ac", "error": "worker stopped"},
            ],
        }
        source = self.root / "batch.json"
        source.write_text(json.dumps(batch), encoding="utf-8")
        html_path = self.root / "batch.html"
        csv_path = self.root / "batch.csv"

        code, report = self.invoke("report", str(source), "--report-format", "html", "--report-output", str(html_path))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(report["report_contract"], "spike/pi-batch-report-data/v1")
        html_text = html_path.read_text(encoding="utf-8")
        self.assertIn("SPIKE Power Integrity Batch Report", html_text)
        self.assertIn("rail-dc", html_text)
        self.assertIn("rail-ac", html_text)
        self.assertIn("worker stopped", html_text)

        code, _ = self.invoke("report", str(source), "--report-format", "csv", "--report-output", str(csv_path))
        self.assertEqual(code, EXIT_OK)
        csv_text = csv_path.read_text(encoding="utf-8")
        self.assertIn("rail-dc", csv_text)
        self.assertIn("rail-ac", csv_text)

    def test_preflight_and_mesh_preview_commands(self):
        request_path = self.root / "request.json"
        self.invoke(
            "analyze-dc", str(self.design_path),
            "--net", "VCC",
            "--source", "0,0,F.Cu,5",
            "--load", "10,0,F.Cu,1",
            "--save-request", str(request_path),
        )
        code, preflight = self.invoke("preflight", str(request_path))
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(preflight["can_solve"])
        self.assertGreater(preflight["mesh"]["cell_count"], 0)
        self.assertNotIn("cells", preflight["mesh"])
        code, preview = self.invoke("mesh-preview", str(request_path))
        self.assertEqual(code, EXIT_OK)
        self.assertGreater(preview["cell_count"], 0)
        code, volume = self.invoke(
            "mesh-preview", str(request_path),
            "--dimension", "volume_3d",
            "--target-size-mm", "2",
        )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(volume["contract"], "spike/mesh/v3")
        self.assertEqual(volume["dimension"], "volume_3d")
        self.assertTrue(all(
            len(cell["vertices_mm"]) >= 8 and len(cell["vertices_mm"]) % 2 == 0
            for cell in volume["cells"]
        ))
        self.assertIn("hex8", volume["topology_counts"])
        self.assertTrue(any(name.startswith("prism") for name in volume["topology_counts"]))

    def test_field_circuit_run_validates_then_writes_structured_result(self):
        package_path = self.root / "field-circuit.json"
        result_path = self.root / "field-circuit-result.json"
        package_path.write_text(json.dumps({
            "contract": FIELD_CIRCUIT_PACKAGE_CONTRACT,
            "design": json.loads(self.design_path.read_text(encoding="utf-8")),
            "workspace": {"contract": "spike/spice-workspace/v1"},
            "request": {"contract": "spike/field-circuit-cosimulation-request/v1"},
            "field_analysis_spec": {
                "contract": "spike/v1",
                "analysis_id": "cli-field-circuit",
                "mode": "ac",
            },
        }), encoding="utf-8")
        calls = []

        def response(method, params):
            calls.append((method, params))
            if method == "validate_field_circuit_cosimulation":
                return {"result": {
                    "contract": "spike/field-circuit-cosimulation-validation/v1",
                    "valid": True,
                    "issues": [],
                }}
            self.assertEqual(method, "run_field_circuit_cosimulation")
            return {"result": {
                "contract": "spike/field-circuit-cosimulation-result/v1",
                "status": "completed",
                "model_status": "experimental",
            }}

        with patch("python.spike_core.cli._response", side_effect=response):
            code, result = self.invoke(
                "--output", str(result_path), "field-circuit-run", str(package_path),
            )

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(result["status"], "completed")
        self.assertEqual([call[0] for call in calls], [
            "validate_field_circuit_cosimulation",
            "run_field_circuit_cosimulation",
        ])
        self.assertEqual(json.loads(result_path.read_text(encoding="utf-8")), result)

    def test_field_circuit_run_fails_closed_before_service_for_invalid_package(self):
        package_path = self.root / "invalid-field-circuit.json"
        package_path.write_text(json.dumps({
            "contract": FIELD_CIRCUIT_PACKAGE_CONTRACT,
            "design": json.loads(self.design_path.read_text(encoding="utf-8")),
            "workspace": {"contract": "spike/spice-workspace/v1"},
            "request": {"contract": "spike/field-circuit-cosimulation-request/v1"},
        }), encoding="utf-8")

        with patch("python.spike_core.cli._response") as response:
            code, result = self.invoke("field-circuit-run", str(package_path))

        self.assertEqual(code, EXIT_VALIDATION)
        self.assertFalse(result["valid"])
        self.assertEqual(result["contract"], "spike/field-circuit-cosimulation-package-validation/v1")
        self.assertTrue(any(issue["path"] == "field_analysis_spec" for issue in result["issues"]))
        response.assert_not_called()

    def test_touchstone_inspection_and_renormalization(self):
        source = self.root / "channel.s2p"
        source.write_text(
            "# GHz S RI R 50\n"
            "1 0 0 0.5 0 0.5 0 0 0\n"
            "2 0 0 0.4 0 0.4 0 0 0\n",
            encoding="ascii",
        )
        code, inspection = self.invoke("sparam-inspect", str(source))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(inspection["contract"], "spike/touchstone-analysis/v1")
        self.assertEqual(inspection["port_count"], 2)
        self.assertEqual(inspection["checks"]["passivity"]["status"], "pass")
        self.assertEqual(len(inspection["traces"]["S21"]), 2)

        output = self.root / "renormalized.s2p"
        code, conversion = self.invoke(
            "sparam-renormalize",
            str(source),
            "--to-ohms", "75",
            "--touchstone-output", str(output),
            "--format", "MA",
        )
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(output.is_file())
        self.assertEqual(conversion["new_reference_impedance_ohm"], [75.0, 75.0])

    def test_compact_thermal_estimate_cli(self):
        scenario_path = self.root / "thermal.json"
        scenario_path.write_text(json.dumps({
            "contract": "spike/thermal/v1",
            "mode": "steady_state",
            "ambient_temperature_c": 25,
            "heat_sources": [{
                "id": "board-total",
                "power_w": 8,
                "theta_ja_c_per_w": 12.5,
                "thermal_capacitance_j_per_c": 20,
            }],
        }), encoding="utf-8")
        code, result = self.invoke("thermal-estimate", str(scenario_path))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(result["model_status"], "approximate")
        self.assertAlmostEqual(result["summary"]["max_steady_temperature_c"], 125.0)


if __name__ == "__main__":
    unittest.main()
