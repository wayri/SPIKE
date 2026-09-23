import unittest
from math import hypot

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.dc_result_utils import stratified_sample_records
from python.spike_core.hybrid_mesh import build_hybrid_mesh, nearest_mesh_node
from python.spike_core.meshing import MeshingOptions, _edges
from python.spike_core.preflight import build_mesh_preview, preflight_analysis
from python.spike_core.solver_plugins import default_solver_registry
from python.spike_core.peec_plugin import native_available


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.design = DesignIR(
            name="preflight fixture",
            layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            tracks=[{
                "id": "track-a",
                "start": [0, 0],
                "end": [10, 0],
                "width": 0.5,
                "layer": "F.Cu",
                "net_name": "VCC",
            }],
            vias=[{
                "id": "via-a",
                "at": [10, 0],
                "size": 0.6,
                "drill": 0.3,
                "layers": ["F.Cu", "B.Cu"],
                "net_name": "VCC",
            }],
            stackup=[
                {"name": "F.Cu", "type": "copper", "thickness": 0.035},
                {"name": "dielectric 1", "type": "core", "thickness": 1.53, "epsilon_r": 4.2},
                {"name": "B.Cu", "type": "copper", "thickness": 0.035},
            ],
        )

    def test_preview_contains_track_and_via_cells(self):
        preview = build_mesh_preview(
            self.design,
            AnalysisSpec(mode="dc", net_names=["VCC"], mesh={"target_size_mm": 2}),
        )
        self.assertGreaterEqual(preview["counts"]["track"], 5)
        self.assertGreaterEqual(preview["counts"]["via"], 8)
        self.assertEqual(preview["contract"], "spike/mesh/v3")
        self.assertEqual(preview["dimension"], "surface_2_5d")
        self.assertGreater(preview["topology_counts"]["quad4"], 0)
        self.assertTrue(all(len(cell["vertices_mm"]) >= 4 for cell in preview["cells"]))
        self.assertTrue(any(cell.get("role") == "track_endpoint_cap" for cell in preview["cells"]))
        self.assertGreater(preview["quality"]["minimum_edge_mm"], 0)

    def test_preview_admission_scales_with_explicit_memory_budget(self):
        constrained = MeshingOptions.from_spec(
            AnalysisSpec(mesh={
                "max_preview_cells": 1_000_000,
                "memory_budget_mb": 8,
                "fixed_memory_estimate_bytes": 4 * 1024 * 1024,
                "estimated_resident_bytes_per_cell": 1024,
            }),
            physical_memory_bytes=64 * 1024 * 1024,
        )
        expanded = MeshingOptions.from_spec(
            AnalysisSpec(mesh={
                "max_preview_cells": 1_000_000,
                "memory_budget_mb": 32,
                "fixed_memory_estimate_bytes": 4 * 1024 * 1024,
                "estimated_resident_bytes_per_cell": 1024,
            }),
            physical_memory_bytes=64 * 1024 * 1024,
        )
        self.assertEqual(constrained.max_cells, 4096)
        self.assertEqual(expanded.max_cells, 28672)
        self.assertGreater(expanded.max_cells, constrained.max_cells)
        self.assertLessEqual(expanded.memory_budget_bytes, int(64 * 1024 * 1024 * 0.75))

    def test_ac_branch_admission_is_derived_from_solver_ram_not_legacy_cap(self):
        design = DesignIR(
            name="resource admission fixture",
            layers=[{"name": "F.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            tracks=[{
                "id": "long-track",
                "start": [0, 0],
                "end": [70, 0],
                "width": 0.2,
                "layer": "F.Cu",
                "net_name": "VCC",
            }],
            stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
        )
        mesh = build_hybrid_mesh(design, AnalysisSpec(
            mode="ac",
            net_names=["VCC"],
            mesh={"target_size_mm": 0.05, "solver_memory_limit_gb": 2.0},
        ))

        self.assertGreater(len(mesh.branches), 1200)
        self.assertGreater(mesh.branch_admission["effective_branch_limit"], 1200)
        self.assertEqual(mesh.branch_admission["configured_memory_gb"], 2.0)
        self.assertFalse(mesh.truncated)

    def test_preflight_rejects_solver_memory_below_two_gb(self):
        spec = AnalysisSpec(
            mode="dc",
            net_names=["VCC"],
            sources=[{"id": "S1", "net": "VCC", "x_mm": 0, "y_mm": 0, "layer": "F.Cu"}],
            loads=[{"id": "L1", "net": "VCC", "x_mm": 10, "y_mm": 0, "layer": "F.Cu"}],
            mesh={"target_size_mm": 1, "solver_memory_limit_gb": 1.5},
        )
        result = preflight_analysis(self.design, spec, default_solver_registry().catalog())

        self.assertIn("SOLVER_MEMORY_LIMIT_INVALID", {issue["code"] for issue in result["issues"]})
        self.assertFalse(result["can_solve"])
        self.assertEqual(result["status"], "blocked")

    def test_spatial_sampling_is_order_invariant_and_retains_extrema(self):
        records = [
            {
                "id": f"F-{x}-{y}",
                "source_id": "front-plane",
                "source_kind": "zone",
                "net": "VCC",
                "layer": "F.Cu",
                "vertices_mm": [[x, y], [x + 0.8, y], [x + 0.8, y + 0.8], [x, y + 0.8]],
                "value": x * 10 + y,
            }
            for x in range(12)
            for y in range(12)
        ]
        records.extend([
            {
                "id": f"B-via-{index}",
                "source_id": f"via-{index}",
                "source_kind": "via",
                "net": "VCC",
                "layer": "B.Cu",
                "position_mm": [index * 2, 30],
                "value": 1000 + index,
            }
            for index in range(4)
        ])
        shuffled = list(reversed(records[::2])) + list(reversed(records[1::2]))
        selected = stratified_sample_records(records, 20, value_key="value")
        shuffled_selected = stratified_sample_records(shuffled, 20, value_key="value")

        self.assertEqual(len(selected), 20)
        self.assertEqual(
            [record["id"] for record in selected],
            [record["id"] for record in shuffled_selected],
        )
        self.assertIn("F-0-0", {record["id"] for record in selected})
        self.assertIn("B-via-3", {record["id"] for record in selected})
        self.assertEqual(
            {(record["layer"], record["source_kind"]) for record in selected},
            {("F.Cu", "zone"), ("B.Cu", "via")},
        )

    def test_spatial_sampling_preserves_component_representatives(self):
        records = [
            {
                "id": f"bond-{component}-{index}",
                "source_id": "shared-bond",
                "source_kind": "component_bond",
                "component_ref": component,
                "net": "VCC",
                "layer": "F.Cu",
                "position_mm": [index, 0],
            }
            for component in ("C1", "C2", "C3")
            for index in range(4)
        ]
        selected = stratified_sample_records(records, 3)
        self.assertEqual({record["component_ref"] for record in selected}, {"C1", "C2", "C3"})

    def test_preview_admission_is_spatial_and_not_a_builder_prefix(self):
        design = DesignIR(
            layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            tracks=[
                {
                    "id": f"track-{index}",
                    "start": [index * 2, 0],
                    "end": [index * 2 + 1.5, 0],
                    "width": 0.2,
                    "layer": "F.Cu",
                    "net_name": "VCC",
                }
                for index in range(30)
            ],
            vias=[
                {
                    "id": f"via-{index}",
                    "at": [index * 2, 2],
                    "size": 0.6,
                    "drill": 0.3,
                    "layers": ["F.Cu", "B.Cu"],
                    "net_name": "VCC",
                }
                for index in range(10)
            ],
        )
        preview = build_mesh_preview(
            design,
            AnalysisSpec(
                mode="dc",
                net_names=["VCC"],
                mesh={"target_size_mm": 0.2, "max_preview_cells": 100},
            ),
        )
        self.assertLessEqual(preview["cell_count"], 100)
        self.assertGreater(preview["counts"]["via"], 0)
        track_x = {
            round(sum(vertex[0] for vertex in cell["vertices_mm"]) / len(cell["vertices_mm"]), 1)
            for cell in preview["cells"]
            if cell.get("source_kind") == "track"
        }
        self.assertGreater(len(track_x), 12)

    def test_track_preview_caps_overlap_at_an_angled_route_joint(self):
        design = DesignIR(
            layers=[{"name": "F.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            tracks=[
                {"id": "left", "start": [0, 0], "end": [10, 0], "width": 1, "layer": "F.Cu", "net_name": "VCC"},
                {"id": "right", "start": [10, 0], "end": [15, 5], "width": 1, "layer": "F.Cu", "net_name": "VCC"},
            ],
        )
        preview = build_mesh_preview(
            design,
            AnalysisSpec(
                mode="dc",
                net_names=["VCC"],
                mesh={"target_size_mm": 20, "feature_aware": False},
            ),
        )
        bodies = [cell for cell in preview["cells"] if cell.get("role") != "track_endpoint_cap"]
        cells = {cell["source_id"]: cell for cell in bodies}
        self.assertEqual(set(cells), {"left", "right"})
        left_x = [point[0] for point in cells["left"]["vertices_mm"]]
        self.assertGreaterEqual(min(left_x), -1e-9)
        self.assertLessEqual(max(left_x), 10 + 1e-9)
        for cell in cells.values():
            xs = [point[0] for point in cell["vertices_mm"]]
            ys = [point[1] for point in cell["vertices_mm"]]
            self.assertLessEqual(min(xs), 10)
            self.assertGreaterEqual(max(xs), 10)
            self.assertLessEqual(min(ys), 0)
            self.assertGreaterEqual(max(ys), 0)
        joint_caps = [
            cell for cell in preview["cells"]
            if cell.get("role") == "track_endpoint_cap"
            and abs(sum(point[0] for point in cell["vertices_mm"]) / len(cell["vertices_mm"]) - 10) < 1e-9
            and abs(sum(point[1] for point in cell["vertices_mm"]) / len(cell["vertices_mm"])) < 1e-9
        ]
        self.assertEqual(len(joint_caps), 1)
        radii = [hypot(point[0] - 10, point[1]) for point in joint_caps[0]["vertices_mm"]]
        self.assertTrue(all(abs(radius - 0.5) < 1e-9 for radius in radii))

    def test_narrow_tracks_receive_width_aware_longitudinal_refinement(self):
        design = DesignIR(
            layers=[{"name": "F.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            tracks=[{
                "id": "narrow-track",
                "start": [0, 0],
                "end": [2, 0],
                "width": 0.1,
                "layer": "F.Cu",
                "net_name": "VCC",
            }],
        )
        mesh = build_hybrid_mesh(
            design,
            AnalysisSpec(mode="dc", net_names=["VCC"], mesh={"target_size_mm": 1.0}),
        )
        branches = [branch for branch in mesh.branches if branch.source_id == "narrow-track"]
        self.assertEqual(len(branches), 10)
        self.assertLessEqual(max(branch.length_mm for branch in branches), 0.2 + 1e-9)
        self.assertEqual(mesh.feature_refined_track_count, 1)
        self.assertAlmostEqual(mesh.minimum_local_target_mm, 0.2)

    def test_zone_boundary_cells_are_clipped_to_narrow_diagonal_copper(self):
        design = DesignIR(
            layers=[{"name": "F.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            zones=[{
                "id": "diagonal-zone",
                "points": [(0, 0), (10, 10), (10.4, 10), (0.4, 0)],
                "layer": "F.Cu",
                "net_name": "VCC",
            }],
        )
        preview = build_mesh_preview(
            design,
            AnalysisSpec(mode="dc", net_names=["VCC"], mesh={"target_size_mm": 1, "zone_cell_mm": 1}),
        )
        cells = [cell for cell in preview["cells"] if cell["source_id"] == "diagonal-zone"]
        self.assertGreater(len(cells), 5)
        for cell in cells:
            edges = list(_edges(cell))
            self.assertTrue(all(hypot(end[0] - start[0], end[1] - start[1]) > 1e-9 for start, end in edges))
            for x, y, _ in cell["vertices_mm"]:
                self.assertGreaterEqual(x - y, -1e-9)
                self.assertLessEqual(x - y, 0.4 + 1e-9)
        self.assertEqual(preview["quality"]["zero_length_edges"], 0)

    def test_concave_zone_does_not_create_attachment_across_void(self):
        design = DesignIR(
            layers=[{"name": "F.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            tracks=[{
                "id": "inside-left-arm",
                "start": [0.25, 3.5],
                "end": [0.75, 3.5],
                "width": 0.25,
                "layer": "F.Cu",
                "net_name": "VCC",
            }],
            zones=[{
                "id": "u-zone",
                "points": [(0, 0), (4, 0), (4, 4), (3, 4), (3, 1), (1, 1), (1, 4), (0, 4)],
                "layer": "F.Cu",
                "net_name": "VCC",
            }],
        )
        mesh = build_hybrid_mesh(
            design,
            AnalysisSpec(mode="dc", net_names=["VCC"], mesh={"target_size_mm": 2, "zone_cell_mm": 2}),
        )
        attachments = [branch for branch in mesh.branches if branch.kind == "zone_attachment"]
        for branch in attachments:
            midpoint = (
                (branch.start_mm[0] + branch.end_mm[0]) / 2,
                (branch.start_mm[1] + branch.end_mm[1]) / 2,
            )
            self.assertFalse(1 < midpoint[0] < 3 and 1 < midpoint[1] < 4)

    def test_concave_zone_cells_do_not_bridge_disconnected_copper_fragments(self):
        polygon = [(0, 0), (4, 0), (4, 10), (3, 10), (3, 1), (1, 1), (1, 10), (0, 10)]
        design = DesignIR(
            layers=[{"name": "F.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            zones=[{
                "id": "u-zone",
                "points": polygon,
                "layer": "F.Cu",
                "net_name": "VCC",
            }],
        )
        preview = build_mesh_preview(
            design,
            AnalysisSpec(
                mode="dc",
                net_names=["VCC"],
                mesh={"target_size_mm": 5, "zone_cell_mm": 5},
            ),
        )
        cells = [cell for cell in preview["cells"] if cell["source_id"] == "u-zone"]
        self.assertGreaterEqual(len(cells), 3)
        for cell in cells:
            for start, end in _edges(cell):
                midpoint = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
                self.assertFalse(1 < midpoint[0] < 3 and 1 < midpoint[1] < 10)

    def test_topology_attachments_are_not_exported_as_physical_result_samples(self):
        design = DesignIR(
            layers=[{"name": "F.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            tracks=[{
                "id": "feed",
                "start": [0, 0],
                "end": [10, 0],
                "width": 0.5,
                "layer": "F.Cu",
                "net_name": "VCC",
            }],
            zones=[{
                "id": "plane",
                "points": [(-1, -2), (11, -2), (11, 2), (-1, 2)],
                "layer": "F.Cu",
                "net_name": "VCC",
            }],
        )
        result = default_solver_registry().run(
            design,
            AnalysisSpec(
                mode="dc",
                net_names=["VCC"],
                sources=[{"position_mm": [0, 0], "layer": "F.Cu", "voltage_v": 5}],
                loads=[{"position_mm": [10, 0], "layer": "F.Cu", "current_a": 1}],
                mesh={"target_size_mm": 1, "zone_cell_mm": 1},
            ),
        )
        self.assertEqual(result.status, "completed")
        kind_by_id = {edge["id"]: edge["kind"] for edge in result.fields["edge_results"]}
        self.assertIn("zone_attachment", set(kind_by_id.values()))
        topology_kinds = {"zone_attachment", "pad_attachment", "pad_zone_attachment"}
        visualization = result.fields["visualization"]["scalar_fields"]
        for field in ("current_a", "current_density_a_mm2", "power_loss_w"):
            self.assertTrue(all(
                kind_by_id.get(sample.get("element_id")) not in topology_kinds
                for sample in visualization[field]
            ))

    def test_volume_zone_prisms_use_face_and_vertical_edges_only(self):
        design = DesignIR(
            layers=[{"name": "F.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            zones=[{
                "id": "diagonal-zone",
                "points": [(0, 0), (10, 10), (10.4, 10), (0.4, 0)],
                "layer": "F.Cu",
                "net_name": "VCC",
            }],
        )
        preview = build_mesh_preview(
            design,
            AnalysisSpec(
                mode="dc",
                net_names=["VCC"],
                mesh={"target_size_mm": 1, "zone_cell_mm": 1, "dimension": "volume_3d"},
            ),
        )
        prism_cells = [cell for cell in preview["cells"] if cell["topology"].startswith("prism")]
        self.assertGreater(len(prism_cells), 0)
        for cell in prism_cells:
            face_vertices = len(cell["vertices_mm"]) // 2
            edges = list(_edges(cell))
            self.assertEqual(len(edges), face_vertices * 3)
            for start, end in edges[-face_vertices:]:
                self.assertAlmostEqual(start[0], end[0])
                self.assertAlmostEqual(start[1], end[1])

    def test_mesh_preview_contains_only_requested_net(self):
        design = DesignIR(
            layers=[{"name": "F.Cu"}],
            tracks=[
                {"id": "vcc", "start": [0, 0], "end": [10, 0], "width": 1, "layer": "F.Cu", "net_name": "VCC"},
                {"id": "gnd", "start": [0, 5], "end": [10, 5], "width": 1, "layer": "F.Cu", "net_name": "GND"},
            ],
        )
        preview = build_mesh_preview(design, AnalysisSpec(mode="dc", net_names=["VCC"]))
        self.assertGreater(preview["cell_count"], 0)
        self.assertEqual({cell["net"] for cell in preview["cells"]}, {"VCC"})

    def test_custom_pad_without_exact_geometry_is_solver_blocked(self):
        design = DesignIR(
            layers=[{"name": "F.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            pads=[{
                "id": "custom-pad",
                "at": [0, 0],
                "size": [2, 1],
                "shape": "custom",
                "layers": ["F.Cu"],
                "net_name": "VCC",
            }],
        )
        mesh = build_hybrid_mesh(design, AnalysisSpec(mode="dc", net_names=["VCC"]))
        self.assertIn("SPIKE-BE-MESH-E-0016", {issue.code for issue in mesh.issues})
        self.assertFalse([cell for cell in mesh.cells if cell.source_id == "custom-pad"])

    def test_volume_preview_extrudes_tracks_and_via_barrels(self):
        preview = build_mesh_preview(
            self.design,
            AnalysisSpec(
                mode="dc",
                net_names=["VCC"],
                mesh={"target_size_mm": 2, "dimension": "volume_3d"},
            ),
        )
        self.assertEqual(preview["dimension"], "volume_3d")
        self.assertEqual(preview["cell_count"], sum(preview["topology_counts"].values()))
        self.assertTrue(all(cell["kind"] == "volume" for cell in preview["cells"]))
        self.assertTrue(all(len(cell["vertices_mm"]) >= 8 and len(cell["vertices_mm"]) % 2 == 0 for cell in preview["cells"]))
        self.assertGreater(preview["topology_counts"]["hex8"], 0)
        self.assertGreater(preview["topology_counts"]["hex8_barrel"], 0)
        self.assertTrue(any(topology.startswith("prism") for topology in preview["topology_counts"]))

    def test_dc_preflight_reports_ready(self):
        spec = AnalysisSpec(
            mode="dc",
            net_names=["VCC"],
            sources=[{"position_mm": [0, 0], "layer": "F.Cu", "voltage_v": 5}],
            loads=[{"position_mm": [10, 0], "layer": "F.Cu", "current_a": 1}],
        )
        result = preflight_analysis(self.design, spec, default_solver_registry().catalog())
        self.assertTrue(result["can_solve"])
        self.assertEqual(result["status"], "ready")
        self.assertGreater(result["summary"]["mesh_cell_count"], 0)

    def test_dc_probe_is_mapped_to_solved_copper(self):
        result = default_solver_registry().run(
            self.design,
            AnalysisSpec(
                mode="dc",
                net_names=["VCC"],
                sources=[{"position_mm": [0, 0], "layer": "F.Cu", "voltage_v": 5}],
                loads=[{"position_mm": [10, 0], "layer": "F.Cu", "current_a": 1}],
                probes=[{"id": "mid", "name": "Midpoint", "position_mm": [5, 0], "layer": "F.Cu", "snap_distance_mm": 6}],
            ),
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.probes[0]["status"], "mapped")
        self.assertGreater(result.probes[0]["voltage_v"], 0)
        self.assertGreaterEqual(result.probes[0]["voltage_drop_v"], 0)

    def test_preflight_blocks_terminal_that_cannot_snap_to_copper(self):
        result = preflight_analysis(
            self.design,
            AnalysisSpec(
                mode="dc",
                net_names=["VCC"],
                sources=[{"id": "source", "position_mm": [0, 0], "layer": "F.Cu", "voltage_v": 5}],
                loads=[{"id": "load", "position_mm": [100, 100], "layer": "F.Cu", "current_a": 1}],
            ),
            default_solver_registry().catalog(),
        )
        self.assertFalse(result["can_solve"])
        self.assertIn("SPIKE-BE-PI-E-0001", {issue["code"] for issue in result["issues"]})

    def test_through_hole_wildcard_pad_accepts_a_copper_layer_terminal(self):
        self.design.pads.append({
            "id": "pad-tht",
            "at": [20, 20],
            "size": [1, 1],
            "layers": ["*.Cu", "*.Mask"],
            "net_name": "VCC",
        })
        result = preflight_analysis(
            self.design,
            AnalysisSpec(
                mode="dc",
                net_names=["VCC"],
                sources=[{"position_mm": [0, 0], "layer": "F.Cu", "voltage_v": 5}],
                loads=[{"position_mm": [20, 20], "layer": "F.Cu", "current_a": 1}],
            ),
            default_solver_registry().catalog(),
        )
        self.assertNotIn(
            "SPIKE-BE-PI-E-0001",
            {issue["code"] for issue in result["issues"]},
        )

    def test_geometry_anchor_selects_the_intended_layer_when_copper_overlaps(self):
        design = DesignIR(
            layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
            tracks=[
                {"id": "front", "start": [0, 0], "end": [10, 0], "width": 1, "layer": "F.Cu", "net_name": "VCC"},
                {"id": "back", "start": [0, 0], "end": [10, 0], "width": 1, "layer": "B.Cu", "net_name": "VCC"},
            ],
            stackup=[
                {"name": "F.Cu", "type": "copper", "thickness": 0.035},
                {"name": "dielectric 1", "type": "core", "thickness": 1.53},
                {"name": "B.Cu", "type": "copper", "thickness": 0.035},
            ],
        )
        mesh = build_hybrid_mesh(design, AnalysisSpec(mode="dc", net_names=["VCC"]))
        node_id = nearest_mesh_node(mesh, {
            "position_mm": [5, 0],
            "layer_scope": "connected_conductor",
            "layer_candidates": ["F.Cu", "B.Cu"],
            "geometry_anchor": {"id": "back", "type": "track"},
        }, "VCC")
        self.assertIsNotNone(node_id)
        self.assertEqual(mesh.nodes[node_id].layer, "B.Cu")

    def test_dc_connected_conductor_terminals_solve_across_a_through_via(self):
        design = DesignIR(
            layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
            tracks=[
                {"id": "front", "start": [0, 0], "end": [5, 0], "width": 1, "layer": "F.Cu", "net_name": "VCC"},
                {"id": "back", "start": [5, 0], "end": [10, 0], "width": 1, "layer": "B.Cu", "net_name": "VCC"},
            ],
            vias=[{"id": "via-a", "at": [5, 0], "size": 0.8, "drill": 0.4, "layers": ["F.Cu", "B.Cu"], "net_name": "VCC"}],
            stackup=[
                {"name": "F.Cu", "type": "copper", "thickness": 0.035},
                {"name": "dielectric 1", "type": "core", "thickness": 1.53},
                {"name": "B.Cu", "type": "copper", "thickness": 0.035},
            ],
        )
        result = default_solver_registry().run(design, AnalysisSpec(
            mode="dc",
            net_names=["VCC"],
            sources=[{
                "position_mm": [0, 0],
                "voltage_v": 5,
                "layer_scope": "connected_conductor",
                "layer_candidates": ["F.Cu", "B.Cu"],
                "geometry_anchor": {"id": "front", "type": "track"},
            }],
            loads=[{
                "position_mm": [10, 0],
                "current_a": 1,
                "layer_scope": "connected_conductor",
                "layer_candidates": ["F.Cu", "B.Cu"],
                "geometry_anchor": {"id": "back", "type": "track"},
            }],
        ))
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.summary["geometry_counts"]["via"], 1)
        self.assertTrue(any(edge["kind"] == "via" and abs(edge["current_a"]) > 0 for edge in result.fields["edge_results"]))

    def test_explicit_return_path_solves_supply_and_return_loop(self):
        design = DesignIR(
            layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
            nets=[{"id": 1, "name": "VCC"}, {"id": 2, "name": "ISO_GND"}],
            tracks=[
                {"id": "supply", "start": [0, 0], "end": [10, 0], "width": 0.5, "layer": "F.Cu", "net_name": "VCC"},
                {"id": "return", "start": [0, 2], "end": [10, 2], "width": 0.5, "layer": "B.Cu", "net_name": "ISO_GND"},
            ],
            stackup=[
                {"name": "F.Cu", "type": "copper", "thickness": 0.035},
                {"name": "dielectric 1", "type": "core", "thickness": 1.53},
                {"name": "B.Cu", "type": "copper", "thickness": 0.035},
            ],
        )
        spec = AnalysisSpec(
            mode="dc",
            required_capabilities=["explicit_return_path", "isolated_power_domain"],
            net_names=["VCC", "ISO_GND"],
            sources=[
                {"id": "secondary-positive", "position_mm": [0, 0], "layer": "F.Cu", "net": "VCC", "voltage_v": 5, "terminal_role": "source_positive", "domain_id": "secondary-1"},
                {"id": "secondary-return", "position_mm": [0, 2], "layer": "B.Cu", "net": "ISO_GND", "voltage_v": 0, "terminal_role": "source_return", "domain_id": "secondary-1"},
            ],
            loads=[
                {"id": "load-positive", "position_mm": [10, 0], "layer": "F.Cu", "net": "VCC", "current_a": 1, "terminal_role": "load_positive", "pair_id": "load-1", "domain_id": "secondary-1"},
                {"id": "load-return", "position_mm": [10, 2], "layer": "B.Cu", "net": "ISO_GND", "current_a": -1, "terminal_role": "load_return", "pair_id": "load-1", "domain_id": "secondary-1"},
            ],
            return_path={"mode": "isolated_secondary", "net": "ISO_GND", "domain_id": "secondary-1"},
        )
        preflight = preflight_analysis(design, spec, default_solver_registry().catalog())
        self.assertTrue(preflight["can_solve"])
        result = default_solver_registry().run(design, spec)
        self.assertEqual(result.status, "completed")
        self.assertAlmostEqual(result.summary["total_load_current_a"], 1.0)
        self.assertGreater(result.summary["max_supply_drop_v"], 0)
        self.assertGreater(result.summary["max_return_rise_v"], 0)
        self.assertAlmostEqual(
            result.summary["max_loop_drop_v"],
            result.summary["max_supply_drop_v"] + result.summary["max_return_rise_v"],
            places=8,
        )
        self.assertEqual(result.summary["return_path_count"], 1)
        self.assertTrue(result.networks["return_path"]["galvanically_isolated"])
        self.assertTrue(any(edge["net"] == "ISO_GND" and abs(edge["current_a"]) > 0 for edge in result.fields["edge_results"]))

    def test_explicit_return_path_requires_paired_terminals(self):
        spec = AnalysisSpec(
            mode="dc",
            net_names=["VCC"],
            sources=[{"id": "source", "position_mm": [0, 0], "layer": "F.Cu", "voltage_v": 5}],
            loads=[{"id": "load", "position_mm": [10, 0], "layer": "F.Cu", "current_a": 1}],
            return_path={"mode": "explicit", "net": "GND", "domain_id": "main"},
        )
        result = preflight_analysis(self.design, spec, default_solver_registry().catalog())
        self.assertFalse(result["can_solve"])
        codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("RETURN_NET_REQUIRED", codes)
        self.assertIn("RETURN_SOURCE_REQUIRED", codes)
        self.assertIn("RETURN_LOAD_PAIR_REQUIRED", codes)

    def test_preflight_blocks_a_truncated_solver_mesh(self):
        result = preflight_analysis(
            self.design,
            AnalysisSpec(
                mode="dc",
                net_names=["VCC"],
                sources=[{"position_mm": [0, 0], "layer": "F.Cu", "voltage_v": 5}],
                loads=[{"position_mm": [10, 0], "layer": "F.Cu", "current_a": 1}],
                mesh={"target_size_mm": 0.1, "max_conductors": 16},
            ),
            default_solver_registry().catalog(),
        )
        self.assertFalse(result["can_solve"])
        self.assertIn("HYBRID_MESH_BRANCH_LIMIT", {issue["code"] for issue in result["issues"]})

    def test_planar_rigid_flex_dc_is_explicitly_approximate(self):
        self.design.technology = "rigid-flex"
        self.design.regions = [
            {"id": "rigid", "kind": "rigid", "outline": [[0, -2], [5, -2], [5, 2], [0, 2]]},
            {"id": "flex", "kind": "flex", "outline": [[5, -1], [10, -1], [10, 1], [5, 1]]},
        ]
        self.design.bends = [{"id": "bend", "points": [[7, -1], [7, 1]], "radius_mm": 1.5}]
        result = preflight_analysis(
            self.design,
            AnalysisSpec(
                mode="dc",
                net_names=["VCC"],
                sources=[{"id": "source", "position_mm": [0, 0], "layer": "F.Cu", "voltage_v": 5}],
                loads=[{"id": "load", "position_mm": [10, 0], "layer": "F.Cu", "current_a": 1}],
                mesh={"target_size_mm": 2},
            ),
            default_solver_registry().catalog(),
        )
        self.assertTrue(result["can_solve"])
        codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("RIGID_FLEX_FLAT_REFERENCE", codes)
        self.assertIn("RIGID_FLEX_PLANAR_COPPER_MODEL", codes)

    def test_deformed_rigid_flex_requires_declared_solver_capability(self):
        self.design.technology = "rigid-flex"
        self.design.regions = [{"id": "flex", "kind": "flex", "outline": [[0, -1], [10, -1], [10, 1], [0, 1]]}]
        self.design.bends = [{"id": "bend", "points": [[5, -1], [5, 1]], "angle_deg": 90}]
        result = preflight_analysis(
            self.design,
            AnalysisSpec(
                mode="dc",
                net_names=["VCC"],
                sources=[{"position_mm": [0, 0], "layer": "F.Cu", "voltage_v": 5}],
                loads=[{"position_mm": [10, 0], "layer": "F.Cu", "current_a": 1}],
                mesh={"target_size_mm": 2},
                options={"geometry_state": "deformed"},
            ),
            default_solver_registry().catalog(),
        )
        self.assertFalse(result["can_solve"])
        self.assertIn("DEFORMED_RIGID_FLEX_UNSUPPORTED", {issue["code"] for issue in result["issues"]})

    def test_rigid_flex_ac_requires_regional_stackup(self):
        self.design.technology = "rigid-flex"
        self.design.regions = [{"id": "flex", "kind": "flex", "outline": [[0, -1], [10, -1], [10, 1], [0, 1]]}]
        result = preflight_analysis(
            self.design,
            AnalysisSpec(
                mode="ac",
                net_names=["VCC"],
                frequency_start_hz=1e3,
                frequency_stop_hz=1e6,
                mesh={"target_size_mm": 2},
            ),
            default_solver_registry().catalog(),
        )
        self.assertFalse(result["can_solve"])
        self.assertIn("RIGID_FLEX_REGIONAL_STACKUP_REQUIRED", {issue["code"] for issue in result["issues"]})

    def test_unavailable_fullwave_is_blocked(self):
        result = preflight_analysis(
            self.design,
            AnalysisSpec(
                mode="broadband_hf",
                solver_id="spike.fullwave_3d",
                formulation="fem_3d",
                net_names=["VCC"],
                frequency_start_hz=1e6,
                frequency_stop_hz=1e9,
            ),
            default_solver_registry().catalog(),
        )
        self.assertFalse(result["can_solve"])
        self.assertIn("SOLVER_NOT_RUNNABLE", {issue["code"] for issue in result["issues"]})

    @unittest.skipUnless(native_available(), "Native PEEC extension is not built")
    def test_native_peec_runs_frequency_dependent_rl_extraction(self):
        spec = AnalysisSpec(
            mode="ac",
            solver_id="spike.peec_2_5d",
            formulation="peec_2_5d",
            required_capabilities=["frequency_dependent_impedance", "partial_inductance", "skin_effect"],
            net_names=["VCC"],
            frequency_start_hz=1e3,
            frequency_stop_hz=1e7,
            frequency_points=11,
            mesh={"target_size_mm": 2},
        )
        result = default_solver_registry().run(self.design, spec)
        self.assertEqual(result.status, "completed")
        self.assertGreater(result.summary["partial_inductance_h"], 0)
        self.assertGreater(result.summary["resistance_start_ohm"], 0)
        parasitic = result.networks["parasitics"][0]
        self.assertEqual(len(parasitic["impedance"]), 11)
        self.assertEqual(parasitic["contract"], "spike/rlgc-network/v1")
        self.assertEqual(parasitic["parameter_availability"]["capacitance"], "approximate_single_reference")
        self.assertGreater(parasitic["capacitance_f"], 0)
        self.assertLess(parasitic["quality"]["maximum_relative_residual"], 1e-8)
        self.assertIn("inductance_passivity", parasitic["quality"])
        self.assertIn("transmission_line_s_parameters", parasitic["blocked_uses"])
        admission = result.provenance["branch_admission"]
        self.assertGreater(admission["effective_branch_limit"], 1200)
        self.assertGreaterEqual(admission["configured_memory_gb"], 2.0)
        self.assertEqual(admission["workload_class"], "dense")


if __name__ == "__main__":
    unittest.main()
