from __future__ import annotations

import copy
import json
import math
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.via_transition_geometry import AntipadSpec, build_via_transition_geometry
from python.spike_core.via_transition_mesh import (
    ViaTransitionMeshError, build_via_transition_mesh, validate_via_transition_mesh,
)


ROOT = Path(__file__).resolve().parents[2]


class ViaTransitionMeshTests(unittest.TestCase):
    def geometry(self, via_type: str = "through", layers: tuple[str, str] = ("F.Cu", "B.Cu")) -> dict:
        names = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
        legacy = DesignIR(
            design_id="mesh-via-board", name="mesh-via-board", source_format="fixture",
            layers=[{"id": index, "name": name, "type": "copper", "thickness_mm": 0.035}
                    for index, name in enumerate(names)],
            nets=[{"id": 1, "name": "SIG"}, {"id": 2, "name": "GND"}],
            vias=[{"id": "V1", "net_name": "SIG", "at": [2.0, 3.0], "diameter": 0.6,
                   "drill": 0.3, "plating_mm": 0.025, "layers": list(layers), "type": via_type}],
            zones=[{"id": f"GND:{name}", "net_name": "GND", "layer": name,
                    "polygons": [[[-5.0, -5.0], [9.0, -5.0], [9.0, 11.0], [-5.0, 11.0]]]}
                   for name in names], metadata={"source_sha256": "b" * 64},
        )
        design = DesignIRV2.from_v1(legacy)
        via = design.vias[0]
        reference_net = next(item.id for item in design.nets if item.name == "GND")
        reference_zone = next(item.id for item in design.zones
                              if item.net_id == reference_net and via.start_layer_id in item.layer_ids)
        return build_via_transition_geometry(
            design, via_id=via.id,
            antipads=[AntipadSpec(via.start_layer_id, 0.9, reference_net, reference_zone, 2.0, "antipad:V1")],
        )

    def test_mesh_is_schema_valid_deterministic_watertight_and_solver_blocked(self) -> None:
        geometry = self.geometry()
        first = build_via_transition_mesh(geometry, radial_segments=24)
        second = build_via_transition_mesh(geometry, radial_segments=24)
        self.assertEqual(first, second)
        schema = json.loads((ROOT / "schemas/pcb-via-transition-mesh-v1.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(first)
        self.assertEqual(first["topology_audit"]["nonmanifold_or_boundary_edges"], 0)
        self.assertEqual(first["topology_audit"]["reference_void_violations"], 0)
        self.assertTrue(first["topology_audit"]["passed"])
        self.assertEqual(first["boundary_loops"], [])
        self.assertFalse(first["qualification"]["native_handoff_ready"])
        self.assertFalse(first["qualification"]["si_ready"])
        self.assertFalse(first["qualification"]["solver_ready"])

    def test_all_admitted_span_classes_produce_closed_domains(self) -> None:
        cases = [("through", ("F.Cu", "B.Cu")), ("blind", ("B.Cu", "In2.Cu")),
                 ("buried", ("In1.Cu", "In2.Cu")), ("microvia", ("F.Cu", "In1.Cu"))]
        for via_type, layers in cases:
            with self.subTest(via_type=via_type):
                geometry = self.geometry(via_type, layers)
                mesh = build_via_transition_mesh(geometry, radial_segments=16)
                self.assertEqual(mesh["topology_audit"]["closed_domains"], 2)
                self.assertTrue(mesh["topology_audit"]["passed"])

    def test_void_boundaries_are_conservative_circumscribed_polygons(self) -> None:
        geometry = self.geometry()
        mesh = build_via_transition_mesh(geometry, radial_segments=8)
        reference = next(item for item in mesh["domains"] if item["kind"] == "reference_plane_local_patch")
        points = [mesh["vertices_mm"][index]
                  for triangle_id in reference["triangle_ids"]
                  for index in mesh["triangles"][int(triangle_id.split(":")[1])]["vertex_indices"]]
        minimum_vertex_radius = min(math.hypot(point[0] - mesh["center_mm"][0], point[1] - mesh["center_mm"][1]) for point in points)
        self.assertGreaterEqual(minimum_vertex_radius, reference["antipad_radius_mm"])
        self.assertEqual(mesh["tessellation"]["circle_approximation"]["drill_and_antipad_void_boundaries"], "circumscribed")

    def test_radial_deviation_accounts_for_every_signal_and_reference_circle(self) -> None:
        geometry = self.geometry()
        mesh = build_via_transition_mesh(geometry, radial_segments=8)
        cosine = math.cos(math.pi / 8)
        radii = [float(geometry["drill_diameter_mm"]) / 2.0,
                 float(geometry["drill_diameter_mm"]) / 2.0 + float(geometry["plating_mm"]),
                 *(float(item["outer_diameter_mm"]) / 2.0 for item in geometry["lands"]),
                 *(float(item[key]) / 2.0 for item in geometry["antipads"]
                   for key in ("diameter_mm", "reference_patch_outer_diameter_mm"))]
        expected = max(max(radius * (1.0 - cosine), radius * (1.0 / cosine - 1.0)) for radius in radii)
        self.assertAlmostEqual(
            mesh["tessellation"]["circle_approximation"]["max_radial_deviation_mm"], expected
        )

    def test_mutated_source_orientation_duplicate_and_index_fail_closed(self) -> None:
        geometry = self.geometry()
        mesh = build_via_transition_mesh(geometry)
        changed_source = copy.deepcopy(geometry)
        changed_source["plating_mm"] += 0.001
        with self.assertRaisesRegex(ViaTransitionMeshError, "digest"):
            validate_via_transition_mesh(mesh, source_geometry=changed_source)
        reversed_face = copy.deepcopy(mesh)
        reversed_face["triangles"][0]["vertex_indices"][1:] = reversed(reversed_face["triangles"][0]["vertex_indices"][1:])
        with self.assertRaisesRegex(ViaTransitionMeshError, "audit failed"):
            validate_via_transition_mesh(reversed_face, source_geometry=geometry)
        duplicate = copy.deepcopy(mesh)
        duplicate["triangles"][1]["vertex_indices"] = list(duplicate["triangles"][0]["vertex_indices"])
        with self.assertRaisesRegex(ViaTransitionMeshError, "audit failed"):
            validate_via_transition_mesh(duplicate, source_geometry=geometry)
        bad_index = copy.deepcopy(mesh)
        bad_index["triangles"][0]["vertex_indices"][0] = len(mesh["vertices_mm"])
        with self.assertRaisesRegex(ViaTransitionMeshError, "outside"):
            validate_via_transition_mesh(bad_index, source_geometry=geometry)

    def test_tessellation_and_local_patch_resolution_are_bounded(self) -> None:
        geometry = self.geometry()
        for value in (7, 10, 132, True):
            with self.subTest(value=value), self.assertRaisesRegex(ViaTransitionMeshError, "radial_segments"):
                build_via_transition_mesh(geometry, radial_segments=value)
        consumed = copy.deepcopy(geometry)
        consumed["antipads"][0]["reference_patch_outer_diameter_mm"] = consumed["antipads"][0]["diameter_mm"] * 1.001
        with self.assertRaisesRegex(ViaTransitionMeshError, "consumes"):
            build_via_transition_mesh(consumed, radial_segments=8)


if __name__ == "__main__":
    unittest.main()
