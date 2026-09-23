import unittest

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.meshing import build_mesh
from python.spike_core.pi_path import PI_PATH_CONTRACT, validate_pi_path
from python.spike_core.service import handle
from python.spike_core.solver_plugins import default_solver_registry


def two_net_design() -> DesignIR:
    return DesignIR(
        design_id="two-net-series-r",
        name="VIN through R1 to VOUT",
        layers=[{"name": "F.Cu"}],
        nets=[{"id": 1, "name": "VIN"}, {"id": 2, "name": "VOUT"}],
        tracks=[
            {"id": "vin-track", "start": [0, 0], "end": [4, 0], "width": 1, "layer": "F.Cu", "net_name": "VIN"},
            {"id": "vout-track", "start": [6, 0], "end": [10, 0], "width": 1, "layer": "F.Cu", "net_name": "VOUT"},
        ],
        pads=[
            {"id": "source-pad", "ref": "J1", "name": "1", "at": [0, 0], "size": [1, 1], "layers": ["F.Cu"], "layer": "F.Cu", "net_name": "VIN"},
            {"id": "r1-in", "ref": "R1", "name": "1", "at": [4, 0], "size": [1, 1], "layers": ["F.Cu"], "layer": "F.Cu", "net_name": "VIN"},
            {"id": "r1-out", "ref": "R1", "name": "2", "at": [6, 0], "size": [1, 1], "layers": ["F.Cu"], "layer": "F.Cu", "net_name": "VOUT"},
            {"id": "load-pad", "ref": "J2", "name": "1", "at": [10, 0], "size": [1, 1], "layers": ["F.Cu"], "layer": "F.Cu", "net_name": "VOUT"},
        ],
        components=[{"id": "r1", "reference": "R1", "ref": "R1", "value": "100m"}],
        stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
    )


def series_path() -> dict:
    return {
        "contract": PI_PATH_CONTRACT,
        "id": "vin-r1-vout",
        "label": "VIN through R1 to VOUT",
        "source_terminal": {"net": "VIN", "pad_id": "source-pad"},
        "load_terminal": {"net": "VOUT", "pad_id": "load-pad"},
        "segments": [
            {"id": "vin-segment", "net": "VIN"},
            {"id": "vout-segment", "net": "VOUT"},
        ],
        "transitions": [{
            "id": "r1-interface",
            "component_ref": "R1",
            "from_segment_id": "vin-segment",
            "to_segment_id": "vout-segment",
            "input_pad_id": "r1-in",
            "output_pad_id": "r1-out",
            "model": {"primitive": "resistor", "value": "100m"},
        }],
    }


class PiPathTests(unittest.TestCase):
    def test_validates_ordered_cross_net_component_interface(self):
        result = validate_pi_path(series_path(), two_net_design(), "dc")
        self.assertTrue(result["can_execute"])
        self.assertEqual(result["counts"], {"segments": 2, "transitions": 1})
        self.assertAlmostEqual(result["interfaces"][0]["dc_resistance_ohm"], 0.1)
        self.assertEqual(result["interfaces"][0]["resistance_source"], "transition.model.value")

    def test_user_connection_resistance_override_is_auditable(self):
        path = series_path()
        path["transitions"][0]["model"] = {
            "primitive": "linearized_component",
            "connection_resistance_ohm": 0.025,
        }
        result = validate_pi_path(path, two_net_design(), "dc")
        self.assertTrue(result["can_execute"])
        self.assertAlmostEqual(result["interfaces"][0]["dc_resistance_ohm"], 0.025)
        self.assertEqual(
            result["interfaces"][0]["resistance_source"],
            "transition.model.connection_resistance_ohm",
        )

    def test_explicit_imported_resistor_value_can_supply_bridge_resistance(self):
        path = series_path()
        path["transitions"][0]["model"] = {"primitive": "resistor"}
        result = validate_pi_path(path, two_net_design(), "dc")
        self.assertTrue(result["can_execute"])
        self.assertAlmostEqual(result["interfaces"][0]["dc_resistance_ohm"], 0.1)
        self.assertEqual(result["interfaces"][0]["resistance_source"], "design.component.value")

    def test_rejects_a_transition_pin_on_the_wrong_net(self):
        path = series_path()
        path["transitions"][0]["input_pad_id"] = "load-pad"
        result = validate_pi_path(path, two_net_design(), "dc")
        self.assertFalse(result["can_execute"])
        self.assertIn("PI_PATH_TRANSITION_NET_MISMATCH", {issue["code"] for issue in result["issues"]})

    def test_worker_exposes_path_validation(self):
        response = handle({"method": "validate_pi_path", "params": {
            "design": two_net_design().to_dict(), "path": series_path(), "mode": "dc",
        }})
        self.assertTrue(response["ok"])
        self.assertTrue(response["result"]["can_execute"])

    def test_rejects_terminal_pad_outside_the_terminal_net(self):
        path = series_path()
        path["load_terminal"]["pad_id"] = "source-pad"
        result = validate_pi_path(path, two_net_design(), "dc")
        self.assertFalse(result["can_execute"])
        self.assertIn("PI_PATH_TERMINAL_PAD_NET_MISMATCH", {issue["code"] for issue in result["issues"]})

    def test_dc_solver_stamps_series_component_between_copper_meshes(self):
        design = two_net_design()
        spec = AnalysisSpec(
            analysis_id="cross-net-dc",
            mode="dc",
            net_names=["VIN", "VOUT"],
            sources=[{"id": "source", "position_mm": [0, 0], "net": "VIN", "voltage_v": 12, "geometry_anchor": {"id": "source-pad", "type": "pad"}}],
            loads=[{"id": "load", "position_mm": [10, 0], "net": "VOUT", "current_a": 1, "geometry_anchor": {"id": "load-pad", "type": "pad"}}],
            mesh={"target_size_mm": 1},
            options={"pi_path": series_path()},
        )
        result = default_solver_registry().run(design, spec)
        self.assertEqual(result.status, "completed", [issue.message for issue in result.issues])
        interface = next(edge for edge in result.fields["edge_results"] if edge["kind"] == "series_component")
        self.assertAlmostEqual(abs(interface["current_a"]), 1.0, places=6)
        self.assertAlmostEqual(interface["power_loss_w"], 0.1, places=6)
        self.assertEqual(interface["component_ref"], "R1")
        self.assertEqual(interface["input_pad_id"], "r1-in")
        self.assertEqual(interface["output_pad_id"], "r1-out")
        self.assertEqual(interface["resistance_source"], "transition.model.value")
        bridge = result.fields["visualization"]["component_bridges"][0]
        self.assertEqual(bridge["topology"], "line2")
        self.assertEqual(bridge["geometry_model"], "pad_center_equivalent_branch")
        self.assertFalse(bridge["current_density_supported"])
        self.assertAlmostEqual(abs(bridge["current_a"]), 1.0, places=6)
        self.assertAlmostEqual(bridge["voltage_drop_v"], 0.1, places=6)
        self.assertAlmostEqual(bridge["power_loss_w"], 0.1, places=6)
        self.assertEqual(result.summary["series_component_count"], 1)
        self.assertAlmostEqual(result.summary["series_component_loss_w"], 0.1, places=6)
        self.assertAlmostEqual(result.summary["component_power_loss_w"]["R1"], 0.1, places=6)
        self.assertAlmostEqual(
            result.summary["total_network_loss_w"],
            result.summary["total_copper_loss_w"] + result.summary["series_component_loss_w"],
            places=6,
        )

    def test_mesh_preview_exposes_cross_layer_component_bridge_at_exact_pad_z(self):
        design = two_net_design()
        design.layers = [
            {"name": "F.Cu", "type": "signal"},
            {"name": "B.Cu", "type": "signal"},
        ]
        design.stackup = [
            {"name": "F.Cu", "type": "copper", "thickness": 0.035},
            {"name": "core", "type": "core", "thickness": 1.0},
            {"name": "B.Cu", "type": "copper", "thickness": 0.035},
        ]
        design.tracks[1]["layer"] = "B.Cu"
        for pad in design.pads:
            if pad["id"] in {"r1-out", "load-pad"}:
                pad["layer"] = "B.Cu"
                pad["layers"] = ["B.Cu"]
        spec = AnalysisSpec(
            analysis_id="cross-layer-preview",
            mode="dc",
            net_names=["VIN", "VOUT"],
            mesh={"target_size_mm": 1},
            options={"pi_path": series_path()},
        )
        preview = build_mesh(design, spec)
        self.assertEqual(preview["component_bridge_count"], 1)
        bridge = preview["component_bridges"][0]
        self.assertEqual(bridge["from_layer"], "F.Cu")
        self.assertEqual(bridge["to_layer"], "B.Cu")
        self.assertNotEqual(bridge["start_z_mm"], bridge["end_z_mm"])
        self.assertEqual(bridge["vertices_mm"][0][2], bridge["start_z_mm"])
        self.assertEqual(bridge["vertices_mm"][1][2], bridge["end_z_mm"])
        self.assertEqual(
            bridge["spatial_material_model"],
            "unavailable_without_package_and_bond_geometry",
        )

    def test_worker_run_analysis_preserves_all_path_segments_and_bridge_metadata(self):
        design = two_net_design()
        path = series_path()
        path["transitions"][0]["model"] = {
            "primitive": "linearized_component",
            "connection_resistance_ohm": 0.025,
            "model_ref": "reviewed:R1:dc",
        }
        spec = AnalysisSpec(
            analysis_id="worker-cross-net-dc",
            mode="dc",
            net_names=["VIN", "VOUT"],
            sources=[{"id": "source", "position_mm": [0, 0], "net": "VIN", "voltage_v": 12, "geometry_anchor": {"id": "source-pad", "type": "pad"}}],
            loads=[{"id": "load", "position_mm": [10, 0], "net": "VOUT", "current_a": 1, "geometry_anchor": {"id": "load-pad", "type": "pad"}}],
            mesh={"target_size_mm": 1},
            options={"pi_path": path},
        )
        response = handle({
            "method": "run_analysis",
            "params": {"design": design.to_dict(), "spec": spec.to_dict()},
        })
        self.assertTrue(response["ok"])
        result = response["result"]
        self.assertEqual(result["status"], "completed", result["issues"])
        interface = next(
            edge for edge in result["fields"]["edge_results"]
            if edge["kind"] == "series_component"
        )
        self.assertEqual(interface["from_net"], "VIN")
        self.assertEqual(interface["to_net"], "VOUT")
        self.assertEqual(interface["model_ref"], "reviewed:R1:dc")
        self.assertEqual(
            interface["resistance_source"],
            "transition.model.connection_resistance_ohm",
        )
        self.assertAlmostEqual(interface["requested_resistance_ohm"], 0.025)

    def test_dc_solver_executes_multiple_series_interfaces_across_three_nets(self):
        design = two_net_design()
        design.nets.insert(1, {"id": 3, "name": "VMID"})
        design.tracks = [
            {"id": "vin-track", "start": [0, 0], "end": [3, 0], "width": 1, "layer": "F.Cu", "net_name": "VIN"},
            {"id": "mid-track", "start": [4, 0], "end": [7, 0], "width": 1, "layer": "F.Cu", "net_name": "VMID"},
            {"id": "vout-track", "start": [8, 0], "end": [11, 0], "width": 1, "layer": "F.Cu", "net_name": "VOUT"},
        ]
        design.pads = [
            {"id": "source-pad", "ref": "J1", "name": "1", "at": [0, 0], "size": [1, 1], "layers": ["F.Cu"], "layer": "F.Cu", "net_name": "VIN"},
            {"id": "r1-in", "ref": "R1", "name": "1", "at": [3, 0], "size": [1, 1], "layers": ["F.Cu"], "layer": "F.Cu", "net_name": "VIN"},
            {"id": "r1-out", "ref": "R1", "name": "2", "at": [4, 0], "size": [1, 1], "layers": ["F.Cu"], "layer": "F.Cu", "net_name": "VMID"},
            {"id": "r2-in", "ref": "R2", "name": "1", "at": [7, 0], "size": [1, 1], "layers": ["F.Cu"], "layer": "F.Cu", "net_name": "VMID"},
            {"id": "r2-out", "ref": "R2", "name": "2", "at": [8, 0], "size": [1, 1], "layers": ["F.Cu"], "layer": "F.Cu", "net_name": "VOUT"},
            {"id": "load-pad", "ref": "J2", "name": "1", "at": [11, 0], "size": [1, 1], "layers": ["F.Cu"], "layer": "F.Cu", "net_name": "VOUT"},
        ]
        design.components.append({"id": "r2", "reference": "R2", "ref": "R2", "value": "200m"})
        path = series_path()
        path["segments"] = [
            {"id": "vin-segment", "net": "VIN"},
            {"id": "mid-segment", "net": "VMID"},
            {"id": "vout-segment", "net": "VOUT"},
        ]
        path["transitions"] = [
            {**path["transitions"][0], "to_segment_id": "mid-segment", "output_pad_id": "r1-out"},
            {"id": "r2-interface", "component_ref": "R2", "from_segment_id": "mid-segment", "to_segment_id": "vout-segment", "input_pad_id": "r2-in", "output_pad_id": "r2-out", "model": {"primitive": "resistor", "value": "200m"}},
        ]
        spec = AnalysisSpec(
            analysis_id="three-net-dc", mode="dc", net_names=["VIN", "VMID", "VOUT"],
            sources=[{"id": "source", "position_mm": [0, 0], "net": "VIN", "voltage_v": 12, "geometry_anchor": {"id": "source-pad", "type": "pad"}}],
            loads=[{"id": "load", "position_mm": [11, 0], "net": "VOUT", "current_a": 1, "geometry_anchor": {"id": "load-pad", "type": "pad"}}],
            mesh={"target_size_mm": 1}, options={"pi_path": path},
        )
        result = default_solver_registry().run(design, spec)
        self.assertEqual(result.status, "completed", [issue.message for issue in result.issues])
        interfaces = [edge for edge in result.fields["edge_results"] if edge["kind"] == "series_component"]
        self.assertEqual([edge["component_ref"] for edge in interfaces], ["R1", "R2"])
        self.assertAlmostEqual(sum(edge["power_loss_w"] for edge in interfaces), 0.3, places=6)
        self.assertEqual(result.summary["series_component_count"], 2)
        self.assertEqual(len(result.fields["visualization"]["component_bridges"]), 2)


if __name__ == "__main__":
    unittest.main()
