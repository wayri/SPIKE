from __future__ import annotations

import copy
import contextlib
import json
import tempfile
import threading
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from python.spike_core.cli import EXIT_OK, main
from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.service import handle
from python.spike_core.sparselizard_adapter import (
    SparseLizardAdapterError,
    _run_adapter_process,
    discover_sparselizard_adapter,
    prepare_sparselizard_case,
    run_sparselizard_case,
)
from python.spike_core.solver_geometry import DC_FEM_GEOMETRY_CONTRACT, build_dc_fem_geometry


FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "python" / "spike_core" / "validation_data"
    / "sparselizard-pcb-result-fixtures-v1.json"
)


def result_fixtures() -> dict[str, dict]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if payload.get("contract") != "spike/sparselizard-pcb-result-fixtures/v1":
        raise AssertionError("Unexpected sparseLizard result fixture contract.")
    return {fixture["id"]: fixture for fixture in payload["fixtures"]}


def fixture_design() -> DesignIR:
    return DesignIR(
        design_id="sparselizard-fixture",
        name="sparseLizard PI fixture",
        layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
        nets=[{"name": "VCC"}, {"name": "GND"}],
        pads=[
            {"id": "U1.1", "net_name": "VCC", "layer": "F.Cu"},
            {"id": "U1.2", "net_name": "GND", "layer": "F.Cu"},
            {"id": "C1.1", "net_name": "VCC", "layer": "F.Cu"},
            {"id": "C1.2", "net_name": "GND", "layer": "F.Cu"},
        ],
        stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
    )


def fixture_ports() -> list[dict]:
    return [
        {
            "id": "load", "role": "observation", "endpoint_reviewed": True,
            "positive_terminal": {"object_id": "U1.1", "object_type": "pad", "net": "VCC"},
            "negative_terminal": {"object_id": "U1.2", "object_type": "pad", "net": "GND"},
        },
        {
            "id": "C1", "role": "candidate", "endpoint_reviewed": True,
            "positive_terminal": {"object_id": "C1.1", "object_type": "pad", "net": "VCC"},
            "negative_terminal": {"object_id": "C1.2", "object_type": "pad", "net": "GND"},
            "location": {"component_ref": "C1"},
        },
    ]


def fixture_spec() -> AnalysisSpec:
    return AnalysisSpec(
        analysis_id="sl-fixture", mode="ac", net_names=["VCC", "GND"],
        frequency_start_hz=1e3, frequency_stop_hz=1e4, frequency_points=2,
        options={"ports": fixture_ports()},
    )


def dc_fixture() -> tuple[DesignIR, AnalysisSpec]:
    design = DesignIR(
        design_id="dc-fem-fixture",
        name="DC FEM copper bar",
        layers=[{"name": "F.Cu", "type": "copper"}],
        nets=[{"name": "VCC"}],
        tracks=[{
            "id": "bar", "start": [0.0, 0.0], "end": [20.0, 0.0],
            "width": 2.0, "layer": "F.Cu", "net_name": "VCC",
        }],
        stackup=[{
            "name": "F.Cu", "type": "copper", "thickness": 0.035,
            "conductivity_s_m": 5.8e7,
        }],
    )
    spec = AnalysisSpec(
        analysis_id="dc-fem", mode="dc", net_names=["VCC"],
        sources=[{"id": "vin", "position_mm": [0.0, 0.0], "layer": "F.Cu", "net": "VCC", "voltage_v": 1.0}],
        loads=[{"id": "load", "position_mm": [20.0, 0.0], "layer": "F.Cu", "net": "VCC", "current_a": 1.0}],
        mesh={"target_size_mm": 1.0, "max_preview_cells": 10000, "memory_budget_mb": 64},
    )
    return design, spec


def materialize_result(fixture: dict, case: dict) -> dict:
    result = copy.deepcopy(fixture["result"])
    if result.get("contract") == "spike/pi-multiport-result/v1":
        result["ports"] = copy.deepcopy(case["ports"])
        result["provenance"].update({
            "geometry_digest": case["provenance"]["geometry_digest"],
            "request_digest": case["provenance"]["request_digest"],
        })
    return result


class SparseLizardAdapterTests(unittest.TestCase):
    def test_dc_fem_contract_requires_volumes_materials_and_terminal_faces(self):
        design, spec = dc_fixture()
        geometry = build_dc_fem_geometry(design, spec)

        self.assertEqual(geometry["contract"], DC_FEM_GEOMETRY_CONTRACT)
        self.assertTrue(geometry["volumes"])
        self.assertTrue(all(len(cell["vertices_mm"]) >= 8 for cell in geometry["volumes"]))
        self.assertEqual(geometry["material_regions"][0]["material"], "copper")
        self.assertEqual(
            {face["role"] for face in geometry["terminal_boundary_faces"]},
            {"source", "load"},
        )

    def test_dc_case_writes_field_mesh_not_hybrid_graph(self):
        design, spec = dc_fixture()
        with tempfile.TemporaryDirectory() as directory:
            prepared = prepare_sparselizard_case(design, spec, Path(directory) / "case")
            mesh = json.loads(Path(prepared["mesh_path"]).read_text(encoding="utf-8"))

        self.assertEqual(mesh["contract"], DC_FEM_GEOMETRY_CONTRACT)
        self.assertNotIn("branches", mesh)
        self.assertGreater(prepared["mesh_counts"]["terminal_boundary_faces"], 0)

    def test_dc_fem_rejects_graph_only_or_unanchored_terminal_setup(self):
        design, spec = dc_fixture()
        spec.loads = [{"id": "missing", "net": "VCC", "current_a": 1.0}]
        with self.assertRaisesRegex(ValueError, "mapped conductor object or a coordinate"):
            build_dc_fem_geometry(design, spec)

    def test_dc_fem_rejects_distant_coordinate_instead_of_nearest_cell_fallback(self):
        design, spec = dc_fixture()
        spec.loads = [{
            "id": "remote-load",
            "net": "VCC",
            "position_mm": [500.0, 500.0],
            "current_a": 1.0,
        }]
        with self.assertRaisesRegex(ValueError, "coordinate is not on selected copper"):
            build_dc_fem_geometry(design, spec)

    def test_prepare_is_deterministic_and_blocks_unreviewed_ports(self):
        with tempfile.TemporaryDirectory() as directory:
            first = prepare_sparselizard_case(fixture_design(), fixture_spec(), Path(directory) / "one")
            second = prepare_sparselizard_case(fixture_design(), fixture_spec(), Path(directory) / "two")
            first_case = json.loads(Path(first["case_path"]).read_text(encoding="utf-8"))
            second_case = json.loads(Path(second["case_path"]).read_text(encoding="utf-8"))

        self.assertEqual(first_case, second_case)
        self.assertEqual(first_case["mesh"]["path"], "mesh.json")
        self.assertEqual(first_case["analysis"]["physics"], "ac_rlcg")
        self.assertTrue(first_case["materials"])
        invalid = fixture_spec()
        invalid.options["ports"][1]["endpoint_reviewed"] = False
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(SparseLizardAdapterError, "explicitly reviewed"):
                prepare_sparselizard_case(fixture_design(), invalid, Path(directory) / "blocked")

    def test_discovery_rejects_non_adapter_executable_name(self):
        with tempfile.TemporaryDirectory() as directory:
            wrong = Path(directory) / "sparselizard.exe"
            wrong.write_text("not an adapter", encoding="utf-8")
            discovery = discover_sparselizard_adapter(executable=wrong)

        self.assertFalse(discovery.available)

    def test_service_prepares_a_versioned_case(self):
        with tempfile.TemporaryDirectory() as directory:
            response = handle({
                "method": "prepare_sparselizard_case",
                "params": {
                    "design": fixture_design().to_dict(),
                    "spec": fixture_spec().to_dict(),
                    "ports": fixture_ports(),
                    "output_dir": str(Path(directory) / "case"),
                },
            })

            self.assertTrue(response["ok"], response.get("error"))
            self.assertEqual(response["result"]["contract"], "spike/sparselizard-case/v1")
            self.assertTrue(Path(response["result"]["case_path"]).is_file())

    def test_cli_prepares_a_versioned_case(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request_path = root / "request.json"
            case_path = root / "case"
            request_path.write_text(json.dumps({
                "contract": "spike/analysis-request/v1",
                "design": fixture_design().to_dict(),
                "spec": fixture_spec().to_dict(),
            }), encoding="utf-8")
            output = StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main((
                    "sparselizard-prepare", str(request_path),
                    "--case-dir", str(case_path),
                ))
            result = json.loads(output.getvalue())

            self.assertEqual(exit_code, EXIT_OK)
            self.assertEqual(result["status"], "prepared_review_required")
            ports = json.loads((case_path / "case.json").read_text(encoding="utf-8"))["ports"]
            self.assertEqual([port["id"] for port in ports], ["load", "C1"])
            self.assertTrue(all(port["endpoint_reviewed"] for port in ports))
            self.assertTrue(all(isinstance(port["location"], dict) for port in ports))

    def test_run_accepts_only_validated_contract_output_from_mocked_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "case"
            prepared = prepare_sparselizard_case(fixture_design(), fixture_spec(), root)
            case = json.loads(Path(prepared["case_path"]).read_text(encoding="utf-8"))
            adapter = Path(directory) / "spike-sparselizard-adapter.exe"
            adapter.write_text("fixture", encoding="utf-8")

            fixture = result_fixtures()["ac-rlcg-reviewed-two-port"]

            def fake_process(command, **_kwargs):
                output = Path(command[command.index("--output") + 1])
                output.write_text(json.dumps(materialize_result(fixture, case)), encoding="utf-8")
                return {"return_code": 0, "stdout": "", "stderr": "", "memory_limit_enforced": False}

            with patch("python.spike_core.sparselizard_adapter._run_adapter_process", side_effect=fake_process):
                run = run_sparselizard_case(root, executable=adapter)

        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["model_status"], "validated")
        self.assertEqual(run["result"]["contract"], "spike/pdn-multiport/v1")
        self.assertAlmostEqual(run["result"]["z_parameters"][1]["reactance_ohm"][1][1], 0.12566370614359174)

    def test_run_rejects_legacy_unbound_pcb_result_domains(self):
        fixtures = result_fixtures()
        for fixture_id in ("dc-conduction-result", "thermal-result", "field-output-result"):
            with self.subTest(fixture=fixture_id), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "case"
                prepare_sparselizard_case(fixture_design(), fixture_spec(), root)
                adapter = Path(directory) / "spike-sparselizard-adapter.exe"
                adapter.write_text("fixture", encoding="utf-8")

                def fake_process(command, **_kwargs):
                    output = Path(command[command.index("--output") + 1])
                    output.write_text(json.dumps(fixtures[fixture_id]["result"]), encoding="utf-8")
                    return {"return_code": 0, "stdout": "", "stderr": "", "memory_limit_enforced": False}

                with patch("python.spike_core.sparselizard_adapter._run_adapter_process", side_effect=fake_process):
                    with self.assertRaisesRegex(SparseLizardAdapterError, "spike/sparselizard-pcb-result/v1"):
                        run_sparselizard_case(root, executable=adapter)

    def test_run_rejects_claimed_validated_result_without_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "case"
            prepared = prepare_sparselizard_case(fixture_design(), fixture_spec(), root)
            case = json.loads(Path(prepared["case_path"]).read_text(encoding="utf-8"))
            adapter = Path(directory) / "spike-sparselizard-adapter.exe"
            adapter.write_text("fixture", encoding="utf-8")
            fixture = result_fixtures()["claimed-validated-without-evidence"]

            def fake_process(command, **_kwargs):
                output = Path(command[command.index("--output") + 1])
                output.write_text(json.dumps(materialize_result(fixture, case)), encoding="utf-8")
                return {"return_code": 0, "stdout": "", "stderr": "", "memory_limit_enforced": False}

            with patch("python.spike_core.sparselizard_adapter._run_adapter_process", side_effect=fake_process):
                with self.assertRaisesRegex(SparseLizardAdapterError, fixture["expected"]["error"]):
                    run_sparselizard_case(root, executable=adapter)

    def test_run_rejects_unvalidated_pi_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "case"
            prepared = prepare_sparselizard_case(fixture_design(), fixture_spec(), root)
            case = json.loads(Path(prepared["case_path"]).read_text(encoding="utf-8"))
            adapter = Path(directory) / "spike-sparselizard-adapter.exe"
            adapter.write_text("fixture", encoding="utf-8")
            fixture = result_fixtures()["unvalidated-pi-result"]

            def fake_process(command, **_kwargs):
                output = Path(command[command.index("--output") + 1])
                output.write_text(json.dumps(materialize_result(fixture, case)), encoding="utf-8")
                return {"return_code": 0, "stdout": "", "stderr": "", "memory_limit_enforced": False}

            with patch("python.spike_core.sparselizard_adapter._run_adapter_process", side_effect=fake_process):
                with self.assertRaisesRegex(SparseLizardAdapterError, fixture["expected"]["error"]):
                    run_sparselizard_case(root, executable=adapter)

    def test_run_converts_validated_pcb_fields_to_analysis_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "case"
            prepared = prepare_sparselizard_case(fixture_design(), fixture_spec(), root)
            case = json.loads(Path(prepared["case_path"]).read_text(encoding="utf-8"))
            adapter = Path(directory) / "spike-sparselizard-adapter.exe"
            adapter.write_text("fixture", encoding="utf-8")
            payload = {
                "contract": "spike/sparselizard-pcb-result/v1",
                "engine_id": "external.sparselizard", "status": "completed",
                "model_status": "validated", "analysis_id": "sl-fixture", "mode": "ac",
                "summary": {"maximum_voltage_v": 1.0},
                "fields": {
                    "scalar_fields": {"voltage_v": {"unit": "V", "samples": [
                        {"point_mm": [1.0, 2.0, 0.035], "value": 1.0, "layer": "F.Cu", "net": "VCC"}
                    ]}},
                    "vector_fields": {"current_density": {"unit": "A/m2", "samples": [
                        {"point_mm": [1.0, 2.0, 0.035], "value": [3.0, 4.0, 0.0], "layer": "F.Cu", "net": "VCC"}
                    ]}},
                },
                "mesh": [{"id": "cell-1", "vertices_mm": [[0, 0, 0], [1, 0, 0], [0, 1, 0]]}],
                "convergence": {"passed": True, "levels": [{"cells": 10}, {"cells": 40}]},
                "provenance": {
                    "solver_version": "sparseLizard-fixture", "adapter_version": "fixture-v1",
                    "validation_evidence": "fixture:pcb-field-v1",
                    "geometry_digest": case["provenance"]["geometry_digest"],
                    "mesh_digest": case["provenance"]["mesh_digest"],
                    "request_digest": case["provenance"]["request_digest"],
                },
            }

            def fake_process(command, **_kwargs):
                Path(command[command.index("--output") + 1]).write_text(json.dumps(payload), encoding="utf-8")
                return {"return_code": 0, "stdout": "", "stderr": "", "memory_limit_enforced": False}

            with patch("python.spike_core.sparselizard_adapter._run_adapter_process", side_effect=fake_process):
                run = run_sparselizard_case(root, executable=adapter)

        self.assertEqual(run["result"]["contract"], "spike/v1")
        visualization = run["result"]["fields"]["visualization"]
        self.assertEqual(visualization["scalar_fields"]["voltage_v"][0]["value"], 1.0)
        self.assertEqual(visualization["vector_fields"]["current_density"][0]["value"], 5.0)

    def test_process_execution_honors_cancellation(self):
        cancellation = threading.Event()
        cancellation.set()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(SparseLizardAdapterError, "cancelled"):
                _run_adapter_process(
                    [str(Path(__import__("sys").executable)), "-c", "import time; time.sleep(10)"],
                    cwd=Path(directory), timeout_s=30, memory_limit_mb=256,
                    output_limit_bytes=1024 * 1024, stream_limit_bytes=1024 * 1024,
                    cancellation_event=cancellation,
                )

    def test_run_blocks_malformed_result_before_status_is_advertised(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "case"
            prepared = prepare_sparselizard_case(fixture_design(), fixture_spec(), root)
            case = json.loads(Path(prepared["case_path"]).read_text(encoding="utf-8"))
            adapter = Path(directory) / "spike-sparselizard-adapter.exe"
            adapter.write_text("fixture", encoding="utf-8")
            malformed = materialize_result(result_fixtures()["ac-rlcg-reviewed-two-port"], case)
            malformed["ports"][1]["endpoint_reviewed"] = False

            def fake_process(command, **_kwargs):
                output = Path(command[command.index("--output") + 1])
                output.write_text(json.dumps(malformed), encoding="utf-8")
                return {"return_code": 0, "stdout": "", "stderr": "", "memory_limit_enforced": False}

            with patch("python.spike_core.sparselizard_adapter._run_adapter_process", side_effect=fake_process):
                with self.assertRaisesRegex(SparseLizardAdapterError, "failed external PI validation"):
                    run_sparselizard_case(root, executable=adapter)


if __name__ == "__main__":
    unittest.main()
