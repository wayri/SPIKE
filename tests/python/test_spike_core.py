import json
import base64
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.capabilities import capabilities
from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.extensions import ExtensionManifest, ExtensionRegistry
from python.spike_core.kicad_importer import _resolve_model_reference
from python.spike_core.service import handle, validate_design
from python.spike_core.models import (
    _stage_resolved_model_references,
    build_model_manifest,
    converter_capabilities,
    export_kicad_scene,
    export_kicad_visual_bundle,
    export_kicad_visual_bundle_path_payload,
    export_kicad_visual_bundle_payload,
    search_model_library,
)
from python.spike_core.ngspice_plugin import (
    NgspicePlugin,
    _build_transient_visualization,
    _component_stress,
    _find_ngspice,
    _parse_ascii_raw,
    _validate_netlist,
)
from python.spike_core.solver_plugins import (
    ExternalProcessSolverPlugin,
    SolverPluginManifest,
    default_solver_registry,
)
from python.spike_core.solver_geometry import build_solver_geometry


class SpikeCoreContractTests(unittest.TestCase):
    def test_capabilities_expose_unsupported_modes_explicitly(self):
        data = capabilities()
        self.assertEqual(data["contract"], "spike/v1")
        self.assertEqual(data["analyses"]["eye_diagram"]["model_status"], "normalized_linear_channel_only")
        self.assertEqual(data["analyses"]["next_fext"]["model_status"], "bounded_parallel_pair_only")
        self.assertEqual(data["layout_automation"]["state"], "orchestration_available")
        self.assertEqual(data["layout_automation"]["pcb_physics"], "integration_pending")
        owned = data["solver_runtime"]["owned_spice_process"]
        self.assertEqual(owned["state"], "experimental")
        self.assertEqual(owned["model_status"], "experimental")
        self.assertFalse(owned["product_qualified"])
        self.assertEqual(owned["analyses"], ["dc", "transient"])
        self.assertTrue(owned["structured_workspace_only"])
        self.assertFalse(owned["raw_netlist_accepted"])
        self.assertFalse(owned["caller_selected_library"])
        self.assertEqual(owned["packaging_state"], "dedicated_build_recipe_available")
        self.assertFalse(owned["packaged_artifact_qualified"])
        self.assertEqual(data["analyses"]["spice_export"]["state"], "integration_pending")

    def test_empty_design_is_not_reported_as_valid(self):
        result = validate_design(DesignIR())
        self.assertFalse(result["valid"])
        self.assertTrue(any(item["code"] == "NO_CONDUCTIVE_GEOMETRY" for item in result["issues"]))

    def test_run_analysis_without_design_context_is_blocked(self):
        response = handle({"method": "run_analysis", "params": {"spec": {"mode": "dc"}}})
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["status"], "blocked")
        self.assertEqual(response["result"]["model_status"], "unsupported")

    def test_dc_solver_reports_a_routed_copper_voltage_drop(self):
        design = DesignIR(
            name="two-segment fixture",
            source_path="fixture.kicad_pcb",
            layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
            tracks=[
                {"start": (0.0, 0.0), "end": (10.0, 0.0), "width": 1.0, "layer": "F.Cu", "net_name": "VCC"},
                {"start": (10.0, 0.0), "end": (20.0, 0.0), "width": 1.0, "layer": "F.Cu", "net_name": "VCC"},
            ],
            stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
        )
        response = handle({"method": "run_analysis", "params": {"design": design.to_dict(), "spec": {"mode": "dc", "net_names": ["VCC"], "sources": [{"id": "source", "position_mm": [0, 0], "layer": "F.Cu", "voltage_v": 5.0}], "loads": [{"id": "load", "position_mm": [20, 0], "layer": "F.Cu", "current_a": 1.0}], "limits": {"max_voltage_drop_mv": 1}}}})
        result = response["result"]
        self.assertTrue(response["ok"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["model_status"], "approximate")
        self.assertGreater(result["summary"]["max_voltage_drop_v"], 0)
        self.assertGreater(result["summary"]["total_copper_loss_w"], 0)
        self.assertAlmostEqual(sum(result["summary"]["net_power_loss_w"].values()), result["summary"]["total_copper_loss_w"])
        self.assertAlmostEqual(sum(result["summary"]["layer_power_loss_w"].values()), result["summary"]["total_copper_loss_w"])
        self.assertAlmostEqual(sum(result["summary"]["geometry_power_loss_w"].values()), result["summary"]["total_copper_loss_w"])
        self.assertIn("VCC", result["summary"]["net_power_loss_w"])
        self.assertIn("F.Cu", result["summary"]["layer_power_loss_w"])
        self.assertTrue(any(item["code"] == "SPIKE-BE-PI-W-0004" for item in result["issues"]))
        self.assertEqual(result["provenance"]["solver_plugin"], "spike.routed_dc")
        visualization = result["fields"]["visualization"]
        self.assertEqual(visualization["schema"], "spike/result-visualization/v1")
        self.assertGreater(len(visualization["scalar_fields"]["voltage_drop_v"]), 0)
        self.assertGreater(len(visualization["scalar_fields"]["current_a"]), 0)
        self.assertGreater(len(visualization["scalar_fields"]["operating_point_impedance_ohm"]), 0)
        self.assertAlmostEqual(result["summary"]["operating_point_impedance_ohm"], 5.0)
        self.assertGreater(len(visualization["scalar_fields"]["current_density_a_mm2"]), 0)
        self.assertGreater(len(visualization["scalar_fields"]["power_loss_w"]), 0)
        self.assertEqual(visualization["scalar_fields"]["via_current_density_a_mm2"], [])
        self.assertGreater(len(visualization["vector_fields"]["current_density"]), 0)
        self.assertGreater(len(visualization["mesh"]), 0)
        mesh_by_id = {cell["id"]: cell for cell in visualization["mesh"]}
        for field_name in (
            "voltage_v",
            "voltage_drop_v",
            "current_a",
            "operating_point_impedance_ohm",
            "current_density_a_mm2",
            "power_loss_w",
        ):
            for sample in visualization["scalar_fields"][field_name]:
                self.assertIn(sample["element_id"], mesh_by_id)
                self.assertEqual(sample["vertices_mm"], mesh_by_id[sample["element_id"]]["vertices_mm"])
                self.assertGreaterEqual(len(sample["vertices_mm"]), 3)

    def test_preflighted_analysis_keeps_validation_and_solve_in_one_transaction(self):
        design = DesignIR(
            name="transaction fixture",
            layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
            nets=[{"id": "1", "name": "VCC"}],
            tracks=[{"id": "t1", "start": (0.0, 0.0), "end": (10.0, 0.0), "width": 1.0, "layer": "F.Cu", "net_name": "VCC"}],
            stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
        )
        response = handle({"method": "run_preflighted_analysis", "params": {
            "design": design.to_dict(),
            "spec": {"mode": "dc", "net_names": ["VCC"],
                     "sources": [{"id": "source", "position_mm": [0, 0], "layer": "F.Cu", "voltage_v": 5.0}],
                     "loads": [{"id": "load", "position_mm": [10, 0], "layer": "F.Cu", "current_a": 1.0}]},
        }})
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["contract"], "spike/preflighted-analysis/v1")
        self.assertTrue(response["result"]["preflight"]["can_solve"])
        self.assertNotIn("mesh", response["result"]["preflight"])
        self.assertEqual(response["result"]["analysis_result"]["status"], "completed")

    def test_dc_solver_supports_multiple_sink_points(self):
        design = DesignIR(
            name="branched multi-sink fixture",
            source_path="fixture.kicad_pcb",
            layers=[{"name": "F.Cu"}],
            tracks=[
                {"start": (0.0, 0.0), "end": (10.0, 0.0), "width": 1.0, "layer": "F.Cu", "net_name": "VCC"},
                {"start": (0.0, 0.0), "end": (0.0, 10.0), "width": 1.0, "layer": "F.Cu", "net_name": "VCC"},
            ],
            stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
        )
        response = handle({
            "method": "run_analysis",
            "params": {
                "design": design.to_dict(),
                "spec": {
                    "mode": "dc",
                    "net_names": ["VCC"],
                    "sources": [{"id": "source", "position_mm": [0, 0], "layer": "F.Cu", "voltage_v": 5.0}],
                    "loads": [
                        {"id": "sink-a", "position_mm": [10, 0], "layer": "F.Cu", "current_a": 0.4},
                        {"id": "sink-b", "position_mm": [0, 10], "layer": "F.Cu", "current_a": 0.6},
                    ],
                },
            },
        })
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["status"], "completed")
        currents = sorted(round(abs(edge["current_a"]), 6) for edge in response["result"]["fields"]["edge_results"])
        self.assertEqual(currents, [0.4, 0.6])

    def test_dc_solver_connects_tracks_through_a_pad(self):
        design = DesignIR(
            layers=[{"name": "F.Cu"}],
            tracks=[
                {"start": (0, 0), "end": (4, 0), "width": 1, "layer": "F.Cu", "net_name": "VCC"},
                {"start": (6, 0), "end": (10, 0), "width": 1, "layer": "F.Cu", "net_name": "VCC"},
            ],
            pads=[{"at": (5, 0), "size": (2.4, 2), "shape": "rect", "layers": ["F.Cu"], "net_name": "VCC"}],
            stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
        )
        response = handle({"method": "run_analysis", "params": {
            "design": design.to_dict(),
            "spec": {
                "mode": "dc",
                "net_names": ["VCC"],
                "sources": [{"position_mm": [0, 0], "layer": "F.Cu", "voltage_v": 5}],
                "loads": [{"position_mm": [10, 0], "layer": "F.Cu", "current_a": 1}],
            },
        }})
        self.assertEqual(response["result"]["status"], "completed")
        self.assertEqual(response["result"]["summary"]["geometry_counts"]["pad"], 1)
        self.assertTrue(any(edge["kind"] == "pad" for edge in response["result"]["fields"]["edge_results"]))

    def test_dc_solver_models_zone_current_spreading(self):
        design = DesignIR(
            layers=[{"name": "F.Cu"}],
            zones=[{"points": [(0, 0), (10, 0), (10, 2), (0, 2)], "layer": "F.Cu", "net_name": "VCC"}],
            stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
        )
        response = handle({"method": "run_analysis", "params": {
            "design": design.to_dict(),
            "spec": {
                "mode": "dc",
                "net_names": ["VCC"],
                "sources": [{"position_mm": [0.5, 0.5], "layer": "F.Cu", "voltage_v": 5}],
                "loads": [{"position_mm": [9.5, 0.5], "layer": "F.Cu", "current_a": 1}],
                "mesh": {"zone_cell_mm": 1},
            },
        }})
        result = response["result"]
        self.assertEqual(result["status"], "completed")
        self.assertGreater(result["summary"]["max_voltage_drop_v"], 0)
        self.assertGreaterEqual(result["summary"]["p95_current_density_a_mm2"], 0)
        self.assertLess(result["summary"]["max_scaled_linear_residual"], 1e-8)
        self.assertGreater(result["summary"]["matrix_nnz"], 0)
        self.assertGreaterEqual(result["summary"]["total_solver_time_s"], result["summary"]["linear_solve_time_s"])
        self.assertEqual(result["summary"]["geometry_counts"]["zone"], 1)
        self.assertGreater(len(result["fields"]["visualization"]["mesh"]), 0)

    def test_dc_result_admission_preserves_stitched_layers_and_vias(self):
        segment_count = 55
        tracks = []
        for index in range(segment_count):
            tracks.append({
                "id": f"front-{index}",
                "start": (index * 10.0, 0.0),
                "end": ((index + 1) * 10.0, 0.0),
                "width": 1.0,
                "layer": "F.Cu",
                "net_name": "VCC",
            })
            tracks.append({
                "id": f"back-{index}",
                "start": ((segment_count + index) * 10.0, 0.0),
                "end": ((segment_count + index + 1) * 10.0, 0.0),
                "width": 1.0,
                "layer": "B.Cu",
                "net_name": "VCC",
            })
        design = DesignIR(
            name="large stitched result-admission fixture",
            source_path="fixture.kicad_pcb",
            layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
            tracks=tracks,
            vias=[{
                "id": "stitch-via",
                "at": (segment_count * 10.0, 0.0),
                "size": 0.8,
                "drill": 0.35,
                "layers": ["F.Cu", "B.Cu"],
                "net_name": "VCC",
            }],
            stackup=[
                {"name": "F.Cu", "type": "copper", "thickness": 0.035},
                {"name": "dielectric 1", "type": "core", "thickness": 1.5},
                {"name": "B.Cu", "type": "copper", "thickness": 0.035},
            ],
        )
        response = handle({"method": "run_analysis", "params": {
            "design": design.to_dict(),
            "spec": {
                "mode": "dc",
                "net_names": ["VCC"],
                "sources": [{"position_mm": [0, 0], "layer": "F.Cu", "voltage_v": 5}],
                "loads": [{
                    "position_mm": [segment_count * 20.0, 0],
                    "layer": "B.Cu",
                    "current_a": 1,
                }],
                "options": {"visual_sample_limit": 1000},
            },
        }})
        self.assertTrue(response["ok"])
        result = response["result"]
        self.assertEqual(result["status"], "completed")
        visualization = result["fields"]["visualization"]
        mesh = visualization["mesh"]
        self.assertEqual(len(mesh), 1000)
        self.assertEqual({cell["layer"] for cell in mesh}, {"F.Cu", "B.Cu", "F.Cu->B.Cu"})
        self.assertIn("via", {cell["source_kind"] for cell in mesh})
        mesh_ids = {cell["id"] for cell in mesh}
        for samples in visualization["scalar_fields"].values():
            for sample in samples:
                self.assertIn(sample["element_id"], mesh_ids)

    def test_dc_solver_applies_explicit_package_and_contact_resistance(self):
        design = DesignIR(
            layers=[{"name": "F.Cu"}],
            tracks=[{"start": (0, 0), "end": (10, 0), "width": 1, "layer": "F.Cu", "net_name": "VCC"}],
            stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
        )
        response = handle({"method": "run_analysis", "params": {
            "design": design.to_dict(),
            "spec": {
                "mode": "dc",
                "net_names": ["VCC"],
                "sources": [{"id": "regulator", "position_mm": [0, 0], "layer": "F.Cu", "voltage_v": 5, "package_resistance_ohm": 0.08}],
                "loads": [{"id": "load", "position_mm": [10, 0], "layer": "F.Cu", "current_a": 1, "contact_resistance_ohm": 0.02}],
            },
        }})
        result = response["result"]
        self.assertEqual(result["status"], "completed")
        self.assertGreater(result["summary"]["max_voltage_drop_v"], 0.1)
        self.assertEqual(result["summary"]["geometry_counts"]["contact"], 2)
        self.assertFalse(any(issue["code"] == "PACKAGE_MODEL_DEFAULT_IDEAL" for issue in result["issues"]))

    def test_solver_catalog_declares_all_formulation_tiers_honestly(self):
        catalog = {item["id"]: item for item in default_solver_registry().catalog()}
        self.assertEqual(catalog["spike.routed_dc"]["state"], "available")
        self.assertIn(catalog["spike.peec_2_5d"]["state"], {"experimental", "integration_pending"})
        self.assertEqual(catalog["spike.mom_surface"]["state"], "unavailable")
        self.assertEqual(catalog["spike.fullwave_3d"]["state"], "unavailable")
        self.assertIn("spike.ngspice", catalog)

    def test_service_solver_catalog_exposes_external_3d_tiers_without_enabling_them(self):
        response = handle({"method": "list_solvers", "params": {}})
        self.assertTrue(response["ok"])
        catalog = {item["id"]: item for item in response["result"]["solvers"]}
        sparse = catalog["external.sparselizard"]
        self.assertIn("ac", sparse["analyses"])
        self.assertIn("fem_3d", sparse["formulations"])
        self.assertFalse(sparse["runnable"])
        self.assertTrue(sparse["reason"])
        self.assertIn("external.elmer", catalog)
        self.assertIn("external.fasthenry", catalog)

    def test_explicit_incompatible_solver_is_blocked(self):
        design = DesignIR(tracks=[{"start": [0, 0], "end": [1, 0], "width": 1, "layer": "F.Cu", "net_name": "VCC"}])
        response = handle({
            "method": "run_analysis",
            "params": {
                "design": design.to_dict(),
                "spec": {"mode": "dc", "solver_id": "spike.fullwave_3d"},
            },
        })
        self.assertEqual(response["result"]["status"], "blocked")
        self.assertEqual(response["result"]["issues"][0]["code"], "NO_COMPATIBLE_SOLVER")

    def test_external_solver_entrypoint_cannot_escape_plugin_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plugin = root / "plugin"
            plugin.mkdir()
            executable = root / "outside.exe"
            executable.write_bytes(b"fixture")
            manifest = SolverPluginManifest(
                id="example.escape",
                name="Escape fixture",
                version="1",
                provider="tests",
                analyses=["dc"],
                formulations=["fixture"],
                capabilities=["fixture"],
                execution="process",
                entrypoint="../outside.exe",
                state="available",
            )
            with self.assertRaisesRegex(ValueError, "inside its plugin directory"):
                ExternalProcessSolverPlugin(manifest, plugin)

    def test_solver_manifest_rejects_unknown_fields_and_missing_process_entrypoint(self):
        value = {
            "id": "example.invalid",
            "name": "Invalid fixture",
            "version": "1",
            "provider": "tests",
            "analyses": ["dc"],
            "formulations": ["fixture"],
            "capabilities": [],
            "unexpected": "must not be ignored",
        }
        with self.assertRaisesRegex(ValueError, "Unknown solver manifest fields"):
            SolverPluginManifest.from_dict(value)
        value.pop("unexpected")
        value["execution"] = "process"
        with self.assertRaisesRegex(ValueError, "entrypoint"):
            SolverPluginManifest.from_dict(value)

    def test_ngspice_adapter_rejects_control_and_include_directives(self):
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            _validate_netlist("fixture\n.include private.lib\n.end\n")
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            _validate_netlist("fixture\n.control\nshell calc\n.endc\n.end\n")

    def test_ngspice_ascii_raw_parser_returns_vectors(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "fixture.raw"
            raw.write_text(
                "Title: fixture\nNo. Variables: 2\nNo. Points: 2\n"
                "Variables:\n\t0\ttime\ttime\n\t1\tv(out)\tvoltage\n"
                "Values:\n0\t0.0\n\t1.0\n1\t1e-6\n\t0.5\n",
                encoding="utf-8",
            )
            result = _parse_ascii_raw(raw)
            self.assertEqual(result["metadata"]["point_count"], 2)
            self.assertEqual(result["vectors"]["v(out)"], [1.0, 0.5])

    def test_ngspice_waveforms_map_to_viewport_frames_and_stress(self):
        parsed = {"vectors": {"time": [0.0, 1e-6], "v(out)": [12.0, 11.5], "i(r1)": [1.0, 2.0]}}
        visualization = _build_transient_visualization(parsed, [{
            "vector": "v(out)", "quantity": "voltage_v", "x_mm": 10, "y_mm": 20,
            "layer": "F.Cu", "net": "VOUT", "element_id": "U1.1",
        }])
        self.assertEqual(len(visualization["frames"]), 2)
        self.assertEqual(visualization["frames"][1]["scalar_fields"]["voltage_v"][0]["value"], 11.5)
        stress = _component_stress(parsed, [{
            "component_id": "R1", "voltage_vector": "v(out)", "current_vector": "i(r1)",
            "ratings": {"voltage_v": 20, "current_a": 1.5, "power_w": 30},
        }])
        self.assertEqual(stress[0]["status"], "over_limit")
        self.assertAlmostEqual(stress[0]["peak_current_a"], 2.0)

    @unittest.skipUnless(_find_ngspice(), "ngspice executable is not installed")
    def test_ngspice_executes_a_real_rc_transient(self):
        netlist = (
            "* SPIKE RC transient fixture\n"
            "V1 in 0 PULSE(0 5 0 1u 1u 1m 2m)\n"
            "R1 in out 1k\n"
            "C1 out 0 1u\n"
            ".tran 10u 2m\n"
            ".save v(in) v(out) i(v1)\n"
            ".end\n"
        )
        result = NgspicePlugin().run(
            DesignIR(design_id="ngspice-rc", name="ngspice RC fixture"),
            AnalysisSpec(
                analysis_id="ngspice-rc",
                mode="transient",
                options={"spice_netlist": netlist, "timeout_seconds": 30},
            ),
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.provenance["ngspice_version"], "46")
        self.assertGreater(result.summary["point_count"], 100)
        self.assertIn("v(out)", result.fields["waveforms"])
        self.assertGreater(result.fields["waveforms"]["v(out)"][-1], 1.0)

    def test_model_manifest_never_claims_step_is_browser_ready(self):
        manifest = build_model_manifest([{"reference": "U1", "model_resolved": "C:/models/U1.step"}])
        self.assertEqual(manifest["counts"]["conversion_required"], 1)

    def test_converter_capabilities_are_explicit(self):
        capabilities = converter_capabilities()
        self.assertTrue(capabilities["offline"])
        self.assertIn("freecad", capabilities["converters"])

    def test_model_library_indexes_step_assets_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Connectors").mkdir()
            model = root / "Connectors" / "SpikeFixtureHeader_2x5.step"
            model.write_text("fixture", encoding="utf-8")
            result = search_model_library("spikefixtureheader", additional_roots=[root])
            self.assertTrue(result["offline"])
            self.assertEqual(result["count"], 1)
            self.assertEqual(result["models"][0]["path"], str(model))

    def test_complete_net_geometry_includes_all_conductor_types(self):
        design = DesignIR(
            design_id="geometry-fixture",
            layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
            tracks=[{"id": "t1", "net_name": "VCC", "layer": "F.Cu"}],
            zones=[{"id": "z1", "net_name": "VCC", "layer": "B.Cu"}],
            vias=[{"id": "v1", "net_name": "VCC", "layers": ["F.Cu", "B.Cu"]}],
            pads=[{"id": "p1", "net_name": "VCC", "layers": ["F.Cu"]}],
            stackup=[{"name": "F.Cu", "thickness": 0.035}],
        )
        response = handle({
            "method": "extract_net_geometry",
            "params": {"design": design.to_dict(), "net_name": "VCC"},
        })
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["counts"], {
            "tracks": 1,
            "zones": 1,
            "vias": 1,
            "pads": 1,
        })
        self.assertEqual([item["name"] for item in response["result"]["layers"]], ["F.Cu", "B.Cu"])

    def test_solver_geometry_handoff_contains_materials_ports_and_complete_nets(self):
        design = DesignIR(
            design_id="handoff",
            layers=[{"name": "F.Cu"}],
            tracks=[{"id": "t1", "net_name": "VCC", "layer": "F.Cu"}],
            stackup=[{"name": "dielectric 1", "type": "core", "epsilon_r": 4.2, "loss_tangent": 0.02}],
        )
        spec = AnalysisSpec(
            mode="ac",
            net_names=["VCC"],
            sources=[{"id": "source"}],
            options={"ports": [{"id": "P1", "net": "VCC"}]},
        )
        geometry = build_solver_geometry(design, spec)
        self.assertEqual(geometry["contract"], "spike/solver-geometry/v1")
        self.assertEqual(geometry["selection"]["complete_nets"][0]["counts"]["tracks"], 1)
        self.assertEqual(geometry["assembly"]["materials"][0]["epsilon_r"], 4.2)
        self.assertEqual(geometry["excitations"]["ports"][0]["id"], "P1")

    def test_model_resolver_expands_project_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "local" / "part.step"
            model.parent.mkdir()
            model.write_text("fixture", encoding="utf-8")
            resolved = _resolve_model_reference("${KIPRJMOD}/local/part.step", directory)
            self.assertEqual(Path(resolved), model.resolve())

    def test_kicad_scene_export_accepts_valid_output_with_missing_models(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "fixture.kicad_pcb"
            output = root / "fixture.glb"
            board.write_text("(kicad_pcb)", encoding="utf-8")

            def fake_run(command, **kwargs):
                output.write_bytes(b"glTF" + b"\0" * 32)
                return subprocess.CompletedProcess(
                    command,
                    1,
                    stdout="Could not add 3D model for J7.\nBinary GLTF file created.",
                    stderr="",
                )

            with patch("python.spike_core.models.kicad_scene_capabilities", return_value={
                "available": True,
                "path": "kicad-cli",
                "offline": True,
                "format": "glb",
                "authority": "kicad-cli",
            }), patch("python.spike_core.models.subprocess.run", side_effect=fake_run):
                result = export_kicad_scene(board, output)

            self.assertEqual(result["status"], "ready_with_warnings")
            self.assertEqual(result["quality"]["missing_references"], ["J7"])
            self.assertTrue(output.exists())

    def test_kicad_scene_export_rejects_non_glb_output(self):
        with tempfile.TemporaryDirectory() as directory:
            board = Path(directory) / "fixture.kicad_pcb"
            board.write_text("(kicad_pcb)", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, ".glb"):
                export_kicad_scene(board, Path(directory) / "fixture.wrl")

    def test_kicad_visual_bundle_separates_scenes_and_layout_layers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "fixture.kicad_pcb"
            board.write_text(
                '(kicad_pcb (layers (0 "F.Cu" signal) '
                '(2 "In1.Cu" power "GND") '
                '(4 "In2.Cu" mixed "POWER+GND") '
                '(31 "B.Cu" signal) '
                '(36 "B.SilkS" user "B.Silkscreen") '
                '(37 "F.SilkS" user "F.Silkscreen") '
                '(44 "Edge.Cuts" user)))',
                encoding="utf-8",
            )
            commands = []

            def fake_run(command, **kwargs):
                commands.append(command)
                output = Path(command[command.index("--output") + 1])
                output.parent.mkdir(parents=True, exist_ok=True)
                if output.suffix == ".glb":
                    output.write_bytes(b"glTF" + b"\0" * 32)
                elif "--mode-multi" in command:
                    aliases = {"In1.Cu": "GND", "In2.Cu": "POWER+GND", "F.SilkS": "F.Silkscreen", "B.SilkS": "B.Silkscreen"}
                    for layer in command[command.index("--layers") + 1].split(","):
                        label = aliases.get(layer, layer)
                        (output / f"fixture-{label.replace('.', '_')}.svg").write_text(
                            '<svg viewBox="0 0 120 80"></svg>', encoding="utf-8",
                        )
                else:
                    output.write_text('<svg viewBox="0 0 120 80"></svg>', encoding="utf-8")
                log = "Could not add 3D model for U9." if "--no-board-body" in command else ""
                return subprocess.CompletedProcess(command, 0, stdout=log, stderr="")

            with patch("python.spike_core.models.kicad_scene_capabilities", return_value={
                "available": True,
                "path": "kicad-cli",
                "offline": True,
                "format": "glb",
                "authority": "kicad-cli",
            }), patch("python.spike_core.models.subprocess.run", side_effect=fake_run):
                result = export_kicad_visual_bundle(board, root / "visuals")

            self.assertEqual(result["contract"], "spike/visual-bundle/v1")
            self.assertEqual(result["layout"]["view_box"], [0.0, 0.0, 120.0, 80.0])
            self.assertEqual(
                set(result["layout"]["layers"]),
                {"F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "F.SilkS", "B.SilkS", "Edge.Cuts"},
            )
            svg_commands = [command for command in commands if command[2:4] == ["export", "svg"]]
            self.assertEqual(len(svg_commands), 1, "all layers must share one KiCad board load")
            self.assertEqual(Path(result["layout"]["layers"]["In1.Cu"]).name, "fixture-GND.svg")
            self.assertIn("--mode-multi", svg_commands[0])
            self.assertTrue(all("--subst-models" in command and "--fuse-shapes" not in command
                                for command in commands if command[3] == "glb"))
            self.assertEqual(result["quality"]["missing_references"], ["U9"])
            self.assertTrue(any("--board-only" in command for command in commands))
            self.assertTrue(any("--no-board-body" in command for command in commands))

    def test_visual_bundle_payload_is_bounded_self_contained_and_path_neutral(self):
        document = json.dumps({"asset": {"version": "2.0"}, "scene": 0, "scenes": [{}]}, separators=(",", ":")).encode()
        document += b" " * ((4 - len(document) % 4) % 4)
        glb = struct.pack("<4sII", b"glTF", 2, 20 + len(document)) + struct.pack("<II", len(document), 0x4E4F534A) + document

        def fake_export(_board, output_directory, _timeout_seconds, *, include_layout_layers=True):
            self.assertTrue(include_layout_layers)  # Independent layer-manager artifacts are required.
            output = Path(output_directory)
            layout = output / "layout"
            layout.mkdir(parents=True)
            board_scene = output / "fixture_board.glb"
            component_scene = output / "fixture_components.glb"
            layer = layout / "fixture-F_Cu.svg"
            board_scene.write_bytes(glb)
            component_scene.write_bytes(glb)
            layer.write_text('<svg viewBox="0 0 10 5"></svg>', encoding="utf-8")
            return {
                "contract": "spike/visual-bundle/v1", "status": "ready_with_warnings",
                "scenes": {"board": str(board_scene), "components": str(component_scene)},
                "layout": {"layers": {"F.Cu": str(layer)}, "view_box": [0, 0, 10, 5]},
                "quality": {"missing_model_count": 1, "missing_references": ["U7"]},
                "generator": {"name": "fixture"},
            }

        with patch("python.spike_core.models.export_kicad_visual_bundle", side_effect=fake_export):
            result = export_kicad_visual_bundle_payload("(kicad_pcb)", "../fixture.kicad_pcb", max_artifact_bytes=4096)

        self.assertEqual(result["contract"], "spike/visual-bundle-payload/v1")
        self.assertEqual(result["source"], "fixture.kicad_pcb")
        self.assertFalse(result["security"]["external_resource_uris_allowed"])
        self.assertEqual(base64.b64decode(result["scenes"]["board"]["artifact_base64"]), glb)
        self.assertEqual(result["quality"]["missing_references"], ["U7"])
        self.assertLessEqual(result["artifact_bytes"], result["artifact_limit_bytes"])

    def test_visual_bundle_path_payload_preserves_project_relative_model_context(self):
        document = json.dumps({"asset": {"version": "2.0"}}, separators=(",", ":")).encode()
        document += b" " * ((4 - len(document) % 4) % 4)
        glb = struct.pack("<4sII", b"glTF", 2, 20 + len(document)) + struct.pack("<II", len(document), 0x4E4F534A) + document
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "selected.kicad_pcb"
            board.write_text("(kicad_pcb)", encoding="utf-8")

            def fake_export(selected_board, output_directory, _timeout_seconds, *, include_layout_layers=True):
                self.assertEqual(Path(selected_board), board.resolve())
                self.assertTrue(include_layout_layers)
                output = Path(output_directory)
                output.mkdir(parents=True)
                board_scene = output / "board.glb"
                component_scene = output / "components.glb"
                board_scene.write_bytes(glb)
                component_scene.write_bytes(glb)
                return {"status": "ready", "scenes": {"board": str(board_scene), "components": str(component_scene)}, "layout": {"layers": {}, "view_box": []}}

            with patch("python.spike_core.models.export_kicad_visual_bundle", side_effect=fake_export):
                result = export_kicad_visual_bundle_path_payload(board, max_artifact_bytes=4096)
        self.assertEqual(result["source"], "selected.kicad_pcb")
        self.assertEqual(result["contract"], "spike/visual-bundle-payload/v1")

    def test_visual_bundle_payload_rejects_external_glb_resources_and_budget_overflow(self):
        def make_glb(document):
            payload = json.dumps(document, separators=(",", ":")).encode()
            payload += b" " * ((4 - len(payload) % 4) % 4)
            return struct.pack("<4sII", b"glTF", 2, 20 + len(payload)) + struct.pack("<II", len(payload), 0x4E4F534A) + payload

        def fake_export(_board, output_directory, _timeout_seconds, *, include_layout_layers=True):
            self.assertTrue(include_layout_layers)
            output = Path(output_directory)
            output.mkdir(parents=True)
            board = output / "board.glb"
            components = output / "components.glb"
            board.write_bytes(make_glb({"asset": {"version": "2.0"}, "buffers": [{"uri": "escape.bin"}]}))
            components.write_bytes(make_glb({"asset": {"version": "2.0"}}))
            return {"status": "ready", "scenes": {"board": str(board), "components": str(components)}, "layout": {"layers": {}, "view_box": []}}

        with patch("python.spike_core.models.export_kicad_visual_bundle", side_effect=fake_export):
            with self.assertRaisesRegex(RuntimeError, "external resources"):
                export_kicad_visual_bundle_payload("(kicad_pcb)", "fixture.kicad_pcb", max_artifact_bytes=4096)

        def oversized_export(_board, output_directory, _timeout_seconds, *, include_layout_layers=True):
            self.assertTrue(include_layout_layers)
            output = Path(output_directory)
            output.mkdir(parents=True, exist_ok=True)
            board = output / "board.glb"
            components = output / "components.glb"
            payload = make_glb({"asset": {"version": "2.0"}})
            board.write_bytes(payload)
            components.write_bytes(payload)
            return {"status": "ready", "scenes": {"board": str(board), "components": str(components)}, "layout": {"layers": {}, "view_box": []}}

        with patch("python.spike_core.models.export_kicad_visual_bundle", side_effect=oversized_export):
            with self.assertRaisesRegex(RuntimeError, "artifact limit"):
                export_kicad_visual_bundle_payload("(kicad_pcb)", "fixture.kicad_pcb", max_artifact_bytes=32)

    def test_visual_bundle_payload_is_reachable_through_worker_service(self):
        expected = {"contract": "spike/visual-bundle-payload/v1", "status": "ready"}
        with patch("python.spike_core.service.prepare_visual_bundle", return_value=expected) as prepare:
            response = handle({
                "method": "prepare_visual_bundle",
                "params": {"source_board": "(kicad_pcb)", "source_file": "fixture.kicad_pcb"},
            })
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"], expected)
        prepare.assert_called_once()

    def test_model_reference_staging_resolves_project_and_unique_library_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "fixture.kicad_pcb"
            local_model = root / "local" / "device.step"
            library_model = root / "library" / "renamed-package" / "resistor.step"
            local_model.parent.mkdir()
            library_model.parent.mkdir(parents=True)
            local_model.write_bytes(b"STEP")
            library_model.write_bytes(b"STEP")
            board.write_text(
                '(kicad_pcb (model "${KIPRJMOD}/local/device.step") '
                '(model "${OLD_LIBRARY}/resistor.step") '
                '(model "${OLD_LIBRARY}/missing.step"))',
                encoding="utf-8",
            )

            with patch("python.spike_core.models.model_library_roots", return_value=[root / "library", root]):
                staged, substitutions = _stage_resolved_model_references(board, root / "output")

            staged_source = staged.read_text(encoding="utf-8")
            self.assertEqual(len(substitutions), 2)
            self.assertIn(local_model.as_posix(), staged_source)
            self.assertIn(library_model.as_posix(), staged_source)
            self.assertIn("${OLD_LIBRARY}/missing.step", staged_source)

    def test_model_reference_staging_resolves_kicad_third_party_variable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "fixture.kicad_pcb"
            third_party = root / "thirdparty"
            model = third_party / "3dmodels" / "vendor" / "part.step"
            model.parent.mkdir(parents=True)
            model.write_bytes(b"STEP")
            board.write_text(
                '(kicad_pcb (model "${KICAD9_3RD_PARTY}/3dmodels/vendor/part.step"))',
                encoding="utf-8",
            )

            with patch.dict("os.environ", {"KICAD9_3RD_PARTY": str(third_party)}), patch(
                "python.spike_core.models.model_library_roots", return_value=[]
            ):
                staged, substitutions = _stage_resolved_model_references(board, root / "output")

            self.assertEqual(len(substitutions), 1)
            self.assertIn(model.as_posix(), staged.read_text(encoding="utf-8"))

    def test_legacy_vrml_reference_uses_installed_step_without_vrml_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = root / "3dmodels"
            model = library / "Package.3dshapes" / "part.step"
            model.parent.mkdir(parents=True)
            model.write_bytes(b"STEP")
            board = root / "fixture.kicad_pcb"
            board.write_text('(kicad_pcb (model "${KICAD8_3DMODEL_DIR}/Package.3dshapes/part.wrl"))')
            with patch("python.spike_core.models.model_library_roots", return_value=[library]):
                staged, substitutions = _stage_resolved_model_references(board, root / "output")
            self.assertEqual(len(substitutions), 1)
            self.assertIn(model.as_posix(), staged.read_text())

    def test_large_board_missing_model_lookup_walks_library_only_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = root / "library"
            library.mkdir()
            board = root / "fixture.kicad_pcb"
            board.write_text('(kicad_pcb ' + ' '.join(
                f'(model "${{OLD_LIBRARY}}/missing-{i % 200}.step")' for i in range(2000)
            ) + ')')
            with patch("python.spike_core.models.model_library_roots", return_value=[library]), patch.object(
                Path, "rglob", return_value=iter([]),
            ) as walk:
                staged, substitutions = _stage_resolved_model_references(board, root / "output")
            self.assertEqual(staged, board)
            self.assertEqual(substitutions, [])
            walk.assert_called_once_with("*")

    def test_worker_protocol_returns_json_line(self):
        root = Path(__file__).parents[2]
        process = subprocess.run(
            [sys.executable, "-m", "python.spike_core.service"],
            cwd=root,
            input=json.dumps({"id": "1", "method": "capabilities"}) + "\n",
            text=True,
            capture_output=True,
            check=True,
        )
        message = json.loads(process.stdout)
        self.assertEqual(message["id"], "1")
        self.assertTrue(message["ok"])

    def test_extension_manifest_rejects_unknown_fields(self):
        with self.assertRaisesRegex(ValueError, "Unknown extension manifest fields"):
            ExtensionManifest.from_dict({
                "id": "example.extension",
                "name": "Example",
                "version": "1.0.0",
                "provider": "Tests",
                "description": "Test extension",
                "entrypoint": "extension.py",
                "contributes": {"commands": [{"id": "run", "name": "Run"}]},
                "unexpected": True,
            })

    def test_bundled_extension_is_discovered_and_invoked(self):
        root = Path(__file__).parents[2]
        registry = ExtensionRegistry()
        diagnostics = registry.discover([root / "extensions"], trusted_roots=[root / "extensions"])
        self.assertTrue(any(item["id"] == "spike.example.net-inventory" and item["status"] == "loaded" for item in diagnostics))
        result = registry.invoke("spike.example.net-inventory", "summarize-nets", {
            "design": DesignIR(
                layers=[{"name": "F.Cu"}],
                nets=[{"id": "1", "name": "VCC"}],
                tracks=[{"net_name": "VCC"}],
            ).to_dict(),
        })
        self.assertEqual(result["contract"], "spike/extension-result/v1")
        self.assertEqual(result["data"]["net_count"], 1)
        self.assertEqual(result["data"]["track_count"], 1)

    def test_extension_context_requires_declared_permission(self):
        root = Path(__file__).parents[2]
        registry = ExtensionRegistry()
        registry.discover([root / "extensions"], trusted_roots=[root / "extensions"])
        with self.assertRaisesRegex(PermissionError, "selection.read"):
            registry.invoke("spike.example.net-inventory", "summarize-nets", {
                "selection": {"id": "track-1"},
            })

    def test_external_extension_cannot_self_assert_bundled_trust(self):
        with tempfile.TemporaryDirectory() as directory:
            extension = Path(directory) / "malicious"
            extension.mkdir()
            (extension / "extension.py").write_text("pass\n", encoding="utf-8")
            (extension / "spike-extension.json").write_text(json.dumps({
                "contract": "spike/extension/v1",
                "api_version": 1,
                "id": "external.self-trusted",
                "name": "External",
                "version": "1.0.0",
                "provider": "Test",
                "description": "Must not acquire trust from its own manifest.",
                "entrypoint": "extension.py",
                "bundled": True,
                "contributes": {"commands": [{"id": "run", "name": "Run"}]},
            }), encoding="utf-8")
            registry = ExtensionRegistry()
            diagnostics = registry.discover([directory])
            self.assertEqual(registry.catalog(), [])
            self.assertEqual(diagnostics[0]["status"], "rejected")
            self.assertIn("cannot self-assert bundled trust", diagnostics[0]["error"])


if __name__ == "__main__":
    unittest.main()
