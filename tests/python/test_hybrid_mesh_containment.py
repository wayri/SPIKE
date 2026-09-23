"""Containment regressions for physical hybrid-mesh faces and result samples."""

import json
from math import ceil, cos, hypot, radians, sin
from pathlib import Path
import unittest

from python.core.board_parser import KicadParser
from python.spike_core.hybrid_mesh import HybridMesh

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.hybrid_mesh import (
    _PolygonContainmentCache,
    _clip_polygon_to_rect_fragments,
    _point_in_polygon,
    _clean_polygon,
    _normalize_filled_zone_polygon,
    _polygon_area,
    _polygon_is_contained_in,
    _polygon_is_simple,
    _point_in_capsule_local,
    _segment_inside_polygon,
    _triangulate_polygon,
    build_hybrid_mesh,
)
from python.spike_core.solver_plugins import default_solver_registry
from python.spike_core.mesh_ownership import audit_dc_conductor_volume_ownership
from python.spike_core.meshing import VOLUME_3D, build_mesh


def _xy(vertices):
    return [(float(vertex[0]), float(vertex[1])) for vertex in vertices]


def _cell_is_inside_polygon(cell, polygon, tolerance=1e-6):
    return _polygon_is_contained_in(_xy(cell["vertices_mm"]), polygon, tolerance)


def _distance_to_segment(point, start, end):
    delta_x = end[0] - start[0]
    delta_y = end[1] - start[1]
    length_squared = delta_x * delta_x + delta_y * delta_y
    if length_squared <= 1e-18:
        return hypot(point[0] - start[0], point[1] - start[1])
    ratio = max(
        0.0,
        min(1.0, ((point[0] - start[0]) * delta_x + (point[1] - start[1]) * delta_y) / length_squared),
    )
    return hypot(point[0] - (start[0] + ratio * delta_x), point[1] - (start[1] + ratio * delta_y))


def _inside_track_union(point, tracks, tolerance=1e-7):
    return any(
        _distance_to_segment(point, tuple(track["start"]), tuple(track["end"]))
        <= float(track["width"]) / 2 + tolerance
        for track in tracks
    )


class HybridMeshContainmentTests(unittest.TestCase):

    def test_bounded_zone_containment_cache_preserves_concave_fragments(self):
        polygon = [
            (0, 0), (8, 0), (8, 8), (5, 8),
            (5, 2), (3, 2), (3, 8), (0, 8),
        ]
        triangles = _triangulate_polygon(polygon)
        bounds = [
            (column * 2, row * 2, (column + 1) * 2, (row + 1) * 2)
            for row in range(4)
            for column in range(4)
        ]
        baseline = [
            _clip_polygon_to_rect_fragments(polygon, triangles, *cell, 1e-6)
            for cell in bounds
        ]
        cache = _PolygonContainmentCache(polygon, 1e-6, maximum_entries=3)
        cached = [
            _clip_polygon_to_rect_fragments(polygon, triangles, *cell, 1e-6, cache)
            for cell in bounds
        ]

        self.assertEqual(cached, baseline)
        self.assertLessEqual(len(cache.point_results), 3)
        self.assertLessEqual(len(cache.segment_results), 3)
        self.assertEqual(len(cache.point_results), 3)
        self.assertEqual(len(cache.segment_results), 3)

    def test_checked_in_filled_polygon_cache_preserves_exact_fragments(self):
        fixture = Path(__file__).parents[2] / "docs/validation/modular-bus-nib-design.json"
        raw = json.loads(fixture.read_text(encoding="utf-8"))
        zone = max(
            (
                item for item in raw["zones"]
                if item.get("net_name") == "/12Vout" and item.get("layer") == "F.Cu"
            ),
            key=lambda item: len(item["points"]),
        )
        polygon = _normalize_filled_zone_polygon([
            (float(point[0]), float(point[1])) for point in zone["points"]
        ])
        triangles = _triangulate_polygon(polygon)
        min_x, max_x = min(x for x, _ in polygon), max(x for x, _ in polygon)
        min_y, max_y = min(y for _, y in polygon), max(y for _, y in polygon)
        cell = 0.5
        columns = ceil((max_x - min_x) / cell)
        rows = ceil((max_y - min_y) / cell)
        bounds = [
            (
                min_x + column * cell,
                min_y + row * cell,
                min(min_x + (column + 1) * cell, max_x),
                min(min_y + (row + 1) * cell, max_y),
            )
            for row in range(rows)
            for column in range(columns)
        ]
        baseline = [
            _clip_polygon_to_rect_fragments(polygon, triangles, *item, 1e-4)
            for item in bounds
        ]
        cache = _PolygonContainmentCache(polygon, 1e-4)
        cached = [
            _clip_polygon_to_rect_fragments(polygon, triangles, *item, 1e-4, cache)
            for item in bounds
        ]

        self.assertEqual(cached, baseline)
        self.assertGreater(sum(bool(item) for item in cached), 0)

    def test_triangle_bounds_halo_preserves_near_cell_boundary_fragment(self):
        tolerance = 1e-4
        polygon = [
            (-1, -1), (2, -1), (2, -0.6), (0, -0.6),
            (0, 0.6), (2, 0.6), (2, 1), (-1, 1),
        ]
        triangles = _triangulate_polygon(polygon)
        cell = (0.5 + tolerance / 2, -1.0, 1.5, 1.0)
        triangle_bounds = [
            (
                min(x for x, _ in triangle),
                min(y for _, y in triangle),
                max(x for x, _ in triangle),
                max(y for _, y in triangle),
            )
            for triangle in triangles
        ]
        baseline = _clip_polygon_to_rect_fragments(
            polygon, triangles, *cell, tolerance
        )
        cache = _PolygonContainmentCache(polygon, tolerance)
        cached = _clip_polygon_to_rect_fragments(
            polygon,
            triangles,
            *cell,
            tolerance,
            cache,
            triangle_bounds,
        )

        self.assertEqual(cached, baseline)
        self.assertGreater(len(cached), 1)

    def test_drilled_pad_cells_are_annular_and_never_cross_the_hole(self):
        pad = {
            "id": "slotted-pad",
            "at": [3.0, 2.0],
            "size": [4.0, 2.0],
            "rotation": 31.0,
            "shape": "oval",
            "drill": 0.8,
            "drill_size": [1.6, 0.8],
            "drill_shape": "oval",
            "layers": ["F.Cu", "B.Cu"],
            "net_name": "VCC",
        }
        mesh = build_hybrid_mesh(
            DesignIR(
                layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
                nets=[{"id": 1, "name": "VCC"}],
                pads=[pad],
            ),
            AnalysisSpec(mode="dc", net_names=["VCC"], mesh={"target_size_mm": 0.2}),
        )

        cells = [cell for cell in mesh.cells if cell["source_id"] == "slotted-pad"]
        self.assertGreater(len(cells), 0)
        angle = -radians(pad["rotation"])
        for cell in cells:
            points = _xy(cell["vertices_mm"])
            local = []
            for world_x, world_y in points:
                delta_x, delta_y = world_x - pad["at"][0], world_y - pad["at"][1]
                local.append((
                    delta_x * cos(angle) - delta_y * sin(angle),
                    delta_x * sin(angle) + delta_y * cos(angle),
                ))
            for start, end in zip(local, local[1:] + local[:1]):
                for sample in range(17):
                    ratio = sample / 16
                    point = (
                        start[0] + ratio * (end[0] - start[0]),
                        start[1] + ratio * (end[1] - start[1]),
                    )
                    self.assertFalse(_point_in_capsule_local(
                        point, pad["drill_size"][0], pad["drill_size"][1], -1e-8
                    ))
        self.assertFalse(any(
            hypot(node.x_mm - pad["at"][0], node.y_mm - pad["at"][1]) < 1e-8
            for node in mesh.nodes
        ))
        self.assertTrue(any(branch.kind == "pad_barrel" for branch in mesh.branches))
        barrel_cells = [cell for cell in cells if cell["source_kind"] == "pad_barrel"]
        self.assertGreater(len(barrel_cells), 0)
        self.assertTrue(all(len(cell["inner_vertices_mm"]) == 4 for cell in barrel_cells))

    def test_rotated_oval_pad_cells_remain_inside_pad_boundary(self):
        pad = {
            "id": "oval-pad",
            "at": [3.0, 2.0],
            "size": [4.0, 1.5],
            "rotation": 37.0,
            "shape": "oval",
            "layers": ["F.Cu"],
            "net_name": "VCC",
        }
        mesh = build_hybrid_mesh(
            DesignIR(
                layers=[{"name": "F.Cu"}],
                nets=[{"id": 1, "name": "VCC"}],
                pads=[pad],
            ),
            AnalysisSpec(
                mode="dc",
                net_names=["VCC"],
                mesh={"target_size_mm": 0.25},
            ),
        )

        cells = [cell for cell in mesh.cells if cell["source_id"] == "oval-pad"]
        self.assertGreater(len(cells), 0)
        angle = -radians(pad["rotation"])
        for cell in cells:
            for world_x, world_y in _xy(cell["vertices_mm"]):
                delta_x, delta_y = world_x - pad["at"][0], world_y - pad["at"][1]
                local_x = delta_x * cos(angle) - delta_y * sin(angle)
                local_y = delta_x * sin(angle) + delta_y * cos(angle)
                self.assertTrue(
                    _point_in_capsule_local(
                        (local_x, local_y), pad["size"][0], pad["size"][1], 1e-9
                    ),
                )

        # A true oval has a straight center section. This point is inside the
        # capsule but outside the old ellipse approximation.
        self.assertTrue(_point_in_capsule_local((1.0, 0.7), 4.0, 1.5))
        self.assertGreater((1.0 / 2.0) ** 2 + (0.7 / 0.75) ** 2, 1.0)

    def test_rotated_slot_barrel_is_an_owned_annular_volume(self):
        pad = {
            "id": "slot-barrel", "at": [4.0, 3.0], "size": [3.0, 1.8],
            "rotation": 29.0, "shape": "oval", "drill_size": [1.4, 0.6],
            "drill_shape": "oval", "plating_thickness_mm": 0.03,
            "layers": ["F.Cu", "B.Cu"], "net_name": "VCC",
        }
        design = DesignIR(
            layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
            stackup=[
                {"name": "F.Cu", "type": "copper", "thickness": 0.035},
                {"name": "dielectric 1", "type": "core", "thickness": 1.0},
                {"name": "B.Cu", "type": "copper", "thickness": 0.035},
            ],
            nets=[{"id": 1, "name": "VCC"}],
            pads=[pad],
        )
        preview = build_mesh(
            design,
            AnalysisSpec(
                mode="dc", net_names=["VCC"],
                mesh={"dimension": VOLUME_3D, "target_size_mm": 0.15, "max_preview_cells": 10000},
            ),
        )
        barrels = [cell for cell in preview["cells"] if cell["source_kind"] == "pad_barrel"]

        self.assertGreater(len(barrels), 0)
        self.assertTrue(all(cell["topology"] == "hex8_barrel" for cell in barrels))
        self.assertTrue(all(len(cell["vertices_mm"]) == 8 for cell in barrels))
        audit = audit_dc_conductor_volume_ownership(design, preview["cells"])
        self.assertEqual(audit["by_source_kind"]["pad_barrel"], len(barrels))

    def test_modular_12vout_zone_normalizes_only_a_numerical_jog(self):
        board = (
            Path(__file__).resolve().parents[2]
            / "app"
            / "public"
            / "demo"
            / "MODULAR-BUS-NIB.kicad_pcb"
        )
        parser = KicadParser(board)
        zone = next(
            item for item in parser.zones
            if item["net_name"] == "/12Vout" and item["layer"] == "F.Cu"
        )
        raw = _clean_polygon(
            [(float(point[0]), float(point[1])) for point in zone["points"]],
            tolerance=1e-9,
        )
        normalized = _normalize_filled_zone_polygon(raw)

        # The KiCad fill contains a 1 nm zero-length arc jog. It is not a
        # copper feature and must not discard the otherwise valid filled area.
        self.assertFalse(_polygon_is_simple(raw, 1e-6))
        self.assertTrue(_polygon_is_simple(normalized, 1e-6))
        self.assertLess(len(normalized), len(raw))
        self.assertLess(abs(_polygon_area(normalized) - _polygon_area(raw)), 1e-8)

        mesh = build_hybrid_mesh(
            DesignIR(
                layers=[{"name": "F.Cu"}],
                nets=[{"id": 1, "name": "/12Vout"}],
                zones=[zone],
            ),
            AnalysisSpec(
                mode="dc",
                net_names=["/12Vout"],
                mesh={"zone_cell_mm": 1.0, "containment_tolerance_mm": 1e-6},
            ),
        )
        cells = [cell for cell in mesh.cells if cell["source_id"] == zone["id"]]
        self.assertGreater(len(cells), 0)
        self.assertTrue(all(_cell_is_inside_polygon(cell, normalized) for cell in cells))
        self.assertNotIn("SPIKE-BE-MESH-W-0002", {issue.code for issue in mesh.issues})

    def test_genuine_self_crossing_zone_remains_rejected(self):
        mesh = build_hybrid_mesh(
            DesignIR(
                layers=[{"name": "F.Cu"}],
                nets=[{"id": 1, "name": "VCC"}],
                zones=[{
                    "id": "bow-tie-zone",
                    "points": [(0, 0), (2, 2), (0, 2), (2, 0)],
                    "layer": "F.Cu",
                    "net_name": "VCC",
                }],
            ),
            AnalysisSpec(mode="dc", net_names=["VCC"], mesh={"zone_cell_mm": 1.0}),
        )
        self.assertFalse([cell for cell in mesh.cells if cell["source_id"] == "bow-tie-zone"])
        self.assertIn("SPIKE-BE-MESH-W-0002", {issue.code for issue in mesh.issues})

    def test_preview_sampling_is_order_independent_and_preserves_geometry_kinds(self):
        records = []
        for source_kind, x_offset in (("track", 0.0), ("via", 100.0), ("zone", 200.0), ("pad", 300.0)):
            for index in range(40):
                records.append({
                    "id": f"{source_kind}-{index}",
                    "source_id": f"{source_kind}-{index}",
                    "source_kind": source_kind,
                    "net": "VCC",
                    "layer": "F.Cu",
                    "vertices_mm": [
                        [x_offset + index, 0.0, 0.0],
                        [x_offset + index + 0.5, 0.0, 0.0],
                        [x_offset + index + 0.5, 0.5, 0.0],
                    ],
                })

        forward = HybridMesh(cells=records).to_preview(24)
        reverse = HybridMesh(cells=list(reversed(records))).to_preview(24)

        self.assertEqual(
            [cell["id"] for cell in forward["cells"]],
            [cell["id"] for cell in reverse["cells"]],
        )
        self.assertEqual(set(forward["counts"]), {"track", "zone", "via", "pad", "dielectric"})
        self.assertTrue(all(forward["counts"][kind] > 0 for kind in ("track", "via", "zone", "pad")))
        self.assertTrue(forward["truncated"])
    def test_coarse_pad_zone_edge_overlap_gets_a_topology_attachment(self):
        # The narrow zone crosses only the right edge of this coarse pad. No
        # pad center/corner or zone vertex is inside the other shape.
        polygon = [(1.5, -5), (1.7, -5), (1.7, 5), (1.5, 5)]
        design = DesignIR(
            layers=[{"name": "F.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            zones=[{
                "id": "edge-zone", "points": polygon, "layer": "F.Cu", "net_name": "VCC",
                "source_zone_id": "edge-zone-source", "filled_copper_id": "edge-zone",
                "zone_kind": "copper", "filled_copper_state": "source_filled",
                "zone_connection_default": "solid", "zone_connection_declared": True,
                "clearance_mm": 0.2, "thermal_gap_mm": 0.2,
                "thermal_spoke_width_mm": 0.2, "fill_mode": "solid",
                "thermal_settings_valid": True,
            }],
            pads=[{
                "id": "edge-pad",
                "at": [0, 0],
                "size": [4, 4],
                "shape": "rect",
                "layers": ["F.Cu"],
                "net_name": "VCC",
                "pad_kind": "smd", "zone_connection_override": "inherit",
                "zone_connection_declared": False, "zone_connection_layer_overrides": {},
                "thermal_settings_valid": True,
            }],
        )
        mesh = build_hybrid_mesh(
            design,
            AnalysisSpec(
                mode="dc",
                net_names=["VCC"],
                mesh={"target_size_mm": 5, "zone_cell_mm": 1},
            ),
        )

        attachments = [
            branch for branch in mesh.branches
            if branch.kind == "pad_zone_attachment" and branch.source_id == "edge-pad"
        ]
        self.assertEqual(len(attachments), 1)
        self.assertTrue(attachments[0].evidence_id)
        self.assertFalse(mesh.zone_pad_connection_evidence["qualification"]["solver_ready"])
        self.assertNotIn(
            "ZONE_ATTACHMENT_UNRESOLVED",
            {issue.code for issue in mesh.issues},
        )

    def test_explicit_none_policy_blocks_geometric_pad_zone_attachment(self):
        zone = {
            "id": "none-zone", "points": [[-2, -2], [2, -2], [2, 2], [-2, 2]],
            "layer": "F.Cu", "net_name": "VCC", "source_zone_id": "none-source",
            "filled_copper_id": "none-zone", "zone_kind": "copper",
            "filled_copper_state": "source_filled", "zone_connection_default": "solid",
            "zone_connection_declared": True, "clearance_mm": 0.2, "thermal_gap_mm": 0.2,
            "thermal_spoke_width_mm": 0.2, "fill_mode": "solid", "thermal_settings_valid": True,
        }
        pad = {
            "id": "none-pad", "at": [0, 0], "size": [1, 1], "shape": "rect",
            "layers": ["F.Cu"], "net_name": "VCC", "pad_kind": "smd",
            "zone_connection_override": "none", "zone_connection_declared": True,
            "zone_connection_layer_overrides": {}, "thermal_settings_valid": True,
        }
        mesh = build_hybrid_mesh(
            DesignIR(layers=[{"name": "F.Cu"}], nets=[{"id": 1, "name": "VCC"}], zones=[zone], pads=[pad]),
            AnalysisSpec(mode="dc", net_names=["VCC"], mesh={"target_size_mm": 1, "zone_cell_mm": 1}),
        )
        self.assertFalse(any(branch.kind == "pad_zone_attachment" for branch in mesh.branches))
        record = mesh.zone_pad_connection_evidence["records"][0]
        self.assertEqual(record["resolved_mode"], "none")
        self.assertEqual(record["observation"], "source_filled_copper_contact")

    def test_concave_zone_cells_and_dc_result_faces_remain_in_copper(self):
        # The narrow central void must not become a cell or projected result
        # face even with a topology node tolerance wider than that void.
        polygon = [
            (0, 0), (8, 0), (8, 10), (5.002, 10), (5.002, 1),
            (2.998, 1), (2.998, 10), (0, 10),
        ]
        design = DesignIR(
            layers=[{"name": "F.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            zones=[{"id": "concave-zone", "points": polygon, "layer": "F.Cu", "net_name": "VCC"}],
        )
        spec = AnalysisSpec(
            mode="dc",
            net_names=["VCC"],
            sources=[{"position_mm": [0.75, 5], "layer": "F.Cu", "voltage_v": 5}],
            loads=[{"position_mm": [7.25, 5], "layer": "F.Cu", "current_a": 0.1}],
            mesh={"zone_cell_mm": 2, "node_tolerance_mm": 0.01},
        )

        mesh = build_hybrid_mesh(design, spec)
        zone_cells = [cell for cell in mesh.cells if cell["source_id"] == "concave-zone"]
        self.assertGreater(len(zone_cells), 0)
        self.assertTrue(all(_cell_is_inside_polygon(cell, polygon) for cell in zone_cells))
        self.assertTrue(all(
            _point_in_polygon((node.x_mm, node.y_mm), polygon, 1e-6)
            for node in mesh.nodes
        ))

        result = default_solver_registry().run(design, spec)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.model_status, "approximate")
        physical_cells = {
            cell["id"]: cell
            for cell in mesh.cells
            if cell["source_id"] == "concave-zone"
        }
        samples = result.fields["visualization"]["scalar_fields"]["current_density_a_mm2"]
        zone_samples = [sample for sample in samples if sample.get("element_id") in physical_cells]
        self.assertGreater(len(zone_samples), 0)
        self.assertTrue(all(
            _polygon_is_contained_in(_xy(sample["vertices_mm"]), polygon, 1e-6)
            for sample in zone_samples
        ))

    def test_exact_concave_custom_pad_cells_are_contained_and_owned(self):
        # The top-center notch catches any fallback to the custom pad's 4 mm
        # bounding rectangle.  The primitive itself is the authoritative land.
        polygon = [
            (-2, -2), (2, -2), (2, 2), (0.5, 2),
            (0.5, -0.5), (-0.5, -0.5), (-0.5, 2), (-2, 2),
        ]
        pad = {
            "id": "concave-custom-pad",
            "at": [10, 20],
            "size": [4, 4],
            "shape": "custom",
            "layers": ["F.Cu"],
            "net_name": "VCC",
            "custom_geometry": {
                "status": "supported",
                "coordinate_space": "pad_local_mm",
                "mirror_x": False,
                "positive_filled_polygon": [list(point) for point in polygon],
            },
        }
        design = DesignIR(
            layers=[{"name": "F.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            pads=[pad],
        )
        spec = AnalysisSpec(
            mode="dc",
            net_names=["VCC"],
            mesh={"dimension": VOLUME_3D, "target_size_mm": 0.5, "max_preview_cells": 10000},
        )

        hybrid = build_hybrid_mesh(design, spec)
        pad_cells = [cell for cell in hybrid.cells if cell["source_id"] == pad["id"]]
        world_polygon = [(x + pad["at"][0], y + pad["at"][1]) for x, y in polygon]
        self.assertGreater(len(pad_cells), 0)
        self.assertTrue(all(_cell_is_inside_polygon(cell, world_polygon) for cell in pad_cells))

        preview = build_mesh(design, spec)
        volumes = [cell for cell in preview["cells"] if cell["source_id"] == pad["id"]]
        audit = audit_dc_conductor_volume_ownership(design, volumes)
        self.assertEqual(audit["checked_volumes"], len(volumes))
        self.assertEqual(audit["by_source_kind"], {"pad": len(volumes)})

    def test_unsupported_custom_pad_emits_no_fallback_copper(self):
        pad = {
            "id": "unsupported-custom-pad",
            "at": [0, 0],
            "size": [4, 4],
            "shape": "custom",
            "layers": ["F.Cu"],
            "net_name": "VCC",
            "custom_geometry": {"status": "unsupported", "reason": "primitive_gr_circle"},
        }
        mesh = build_hybrid_mesh(
            DesignIR(
                layers=[{"name": "F.Cu"}],
                nets=[{"id": 1, "name": "VCC"}],
                pads=[pad],
            ),
            AnalysisSpec(mode="dc", net_names=["VCC"], mesh={"target_size_mm": 0.5}),
        )

        self.assertFalse([cell for cell in mesh.cells if cell["source_id"] == pad["id"]])
        self.assertTrue(any(issue.status == "unsupported" for issue in mesh.issues))

    def test_zone_neighbor_links_do_not_cross_a_narrow_concave_void(self):
        polygon = [
            (0, 0), (4, 0), (4, 8), (2.004, 8), (2.004, 1),
            (1.996, 1), (1.996, 8), (0, 8),
        ]
        mesh = build_hybrid_mesh(
            DesignIR(
                layers=[{"name": "F.Cu"}],
                nets=[{"id": 1, "name": "VCC"}],
                zones=[{"id": "narrow-void", "points": polygon, "layer": "F.Cu", "net_name": "VCC"}],
            ),
            AnalysisSpec(
                mode="dc",
                net_names=["VCC"],
                mesh={"zone_cell_mm": 2, "node_tolerance_mm": 0.02},
            ),
        )

        zone_links = [branch for branch in mesh.branches if branch.source_id == "narrow-void"]
        self.assertGreater(len(zone_links), 0)
        self.assertTrue(all(
            _segment_inside_polygon(branch.start_mm[:2], branch.end_mm[:2], polygon, 1e-6)
            for branch in zone_links
        ))

    def test_angled_trace_joint_faces_stay_inside_the_track_stroke_union(self):
        tracks = [
            {"id": "left", "start": [0, 0], "end": [4, 0], "width": 0.4, "layer": "F.Cu", "net_name": "VCC", "path_id": "route", "path_step_index": 0, "path_step_count": 3, "path_end_cap": "round", "path_join_style": "round"},
            {"id": "joint", "start": [4, 0], "end": [4.6, 1.5], "width": 0.4, "layer": "F.Cu", "net_name": "VCC", "path_id": "route", "path_step_index": 1, "path_step_count": 3, "path_end_cap": "round", "path_join_style": "round"},
            {"id": "right", "start": [4.6, 1.5], "end": [7, 1.5], "width": 0.4, "layer": "F.Cu", "net_name": "VCC", "path_id": "route", "path_step_index": 2, "path_step_count": 3, "path_end_cap": "round", "path_join_style": "round"},
        ]
        mesh = build_hybrid_mesh(
            DesignIR(layers=[{"name": "F.Cu"}], nets=[{"id": 1, "name": "VCC"}], tracks=tracks),
            AnalysisSpec(mode="dc", net_names=["VCC"], mesh={"target_size_mm": 5, "feature_aware": False}),
        )

        cells = [cell for cell in mesh.cells if cell["source_kind"] == "track"]
        self.assertGreater(len(cells), len(tracks))
        for cell in cells:
            points = _xy(cell["vertices_mm"])
            samples = points + [
                ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
                for start, end in zip(points, points[1:] + points[:1])
            ]
            self.assertTrue(all(_inside_track_union(point, tracks) for point in samples))


if __name__ == "__main__":
    unittest.main()
