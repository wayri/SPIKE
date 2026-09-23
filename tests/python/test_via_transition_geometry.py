from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.reference_plane_antipad_geometry import (
    ReferencePlaneAntipadGeometryError,
    build_reference_plane_antipad_geometry,
    validate_reference_plane_antipad_geometry,
)
from python.spike_core.reference_plane_antipad_mesh import (
    ReferencePlaneAntipadMeshError,
    build_reference_plane_antipad_mesh,
    validate_reference_plane_antipad_mesh,
)
from python.spike_core.via_transition_geometry import AntipadSpec, ViaTransitionGeometryError, build_via_transition_geometry


ROOT = Path(__file__).resolve().parents[2]


class ViaTransitionGeometryTests(unittest.TestCase):
    def design(self, via_type: str = "through", layers: tuple[str, str] = ("F.Cu", "B.Cu"),
               *, plating: float | None = 0.025, profiles: list[dict] | None = None) -> DesignIRV2:
        names = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
        via = {"id": "V1", "net_name": "SIG", "at": [2.0, 3.0], "diameter": 0.6,
               "drill": 0.3, "layers": list(layers), "type": via_type}
        if plating is not None:
            via["plating_mm"] = plating
        if profiles is not None:
            via["land_profiles"] = profiles
        legacy = DesignIR(
            design_id="via-board", name="via-board", source_format="fixture",
            layers=[{"id": index, "name": name, "type": "copper", "thickness_mm": 0.035}
                    for index, name in enumerate(names)],
            nets=[{"id": 1, "name": "SIG"}, {"id": 2, "name": "GND"}], vias=[via],
            zones=[{"id": f"GND:{name}", "net_name": "GND", "layer": name,
                    "polygons": [[[-5.0, -5.0], [9.0, -5.0], [9.0, 11.0], [-5.0, 11.0]]]}
                   for name in names],
            metadata={"source_sha256": "a" * 64},
        )
        return DesignIRV2.from_v1(legacy)

    @staticmethod
    def ids(design: DesignIRV2, layer_name: str = "In1.Cu") -> tuple[str, str, str]:
        layer = next(item.id for item in design.layers if item.name == layer_name)
        net = next(item.id for item in design.nets if item.name == "GND")
        zone = next(item.id for item in design.zones if item.net_id == net and layer in item.layer_ids)
        return layer, net, zone

    def build(self, design: DesignIRV2) -> dict:
        layer_id = design.vias[0].start_layer_id
        layer_name = next(item.name for item in design.layers if item.id == layer_id)
        _, net_id, zone_id = self.ids(design, layer_name)
        return build_via_transition_geometry(
            design, via_id=design.vias[0].id,
            antipads=[AntipadSpec(layer_id=layer_id, diameter_mm=0.9, reference_net_id=net_id,
                                  reference_zone_id=zone_id, reference_patch_outer_diameter_mm=2.0,
                                  source_id="clearance:V1:start")],
        )

    def test_exact_circular_transition_is_schema_valid_and_solver_blocked(self) -> None:
        design = self.design()
        geometry = self.build(design)
        schema = json.loads((ROOT / "schemas/pcb-via-transition-geometry-v1.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(geometry)
        self.assertEqual(geometry["span"]["ordered_layer_ids"], [item.id for item in design.layers])
        self.assertEqual(len(geometry["barrel_segments"]), 3)
        self.assertEqual(len(geometry["lands"]), 4)
        self.assertAlmostEqual(geometry["antipads"][0]["clearance_mm"], 0.15)
        self.assertFalse(geometry["topology_audit"]["discrete_watertightness_checked"])
        self.assertEqual(geometry["qualification"], {
            "geometry_state": "admitted_exact_circular", "refinement_state": "refinement_not_convergence_proof",
            "native_handoff_ready": False, "capacitance_ready": False, "si_ready": False, "solver_ready": False,
        })

    def test_four_supported_via_span_classes_are_admitted(self) -> None:
        cases = [("through", ("F.Cu", "B.Cu"), 4), ("blind", ("B.Cu", "In2.Cu"), 2),
                 ("buried", ("In1.Cu", "In2.Cu"), 2), ("microvia", ("F.Cu", "In1.Cu"), 2)]
        for via_type, layers, count in cases:
            with self.subTest(via_type=via_type):
                geometry = self.build(self.design(via_type, layers))
                self.assertEqual(geometry["via_type"], via_type)
                self.assertEqual(len(geometry["interfaces"]), count)

    def test_invalid_type_span_plating_antipad_and_refinement_fail_closed(self) -> None:
        with self.assertRaisesRegex(ViaTransitionGeometryError, "incompatible"):
            self.build(self.design("through", ("F.Cu", "In2.Cu")))
        with self.assertRaisesRegex(ViaTransitionGeometryError, "explicit positive plating"):
            self.build(self.design(plating=None))
        design = self.design()
        layer_id, _, zone_id = self.ids(design)
        with self.assertRaisesRegex(ViaTransitionGeometryError, "reference-net"):
            build_via_transition_geometry(
                design, via_id=design.vias[0].id,
                antipads=[AntipadSpec(layer_id, 0.6, design.vias[0].net_id, zone_id, 2.0, "bad")],
            )
        _, net_id, zone_id = self.ids(design)
        with self.assertRaisesRegex(ViaTransitionGeometryError, "strictly decreasing"):
            build_via_transition_geometry(
                design, via_id=design.vias[0].id,
                antipads=[AntipadSpec(layer_id, 0.9, net_id, zone_id, 2.0, "clearance")],
                refinement_sizes_mm=(0.1, 0.2),
            )
        with self.assertRaisesRegex(ViaTransitionGeometryError, "strictly decreasing"):
            build_via_transition_geometry(
                design, via_id=design.vias[0].id,
                antipads=[AntipadSpec(layer_id, 0.9, net_id, zone_id, 2.0, "clearance")],
                refinement_sizes_mm=(True,),
            )

    def test_non_circular_land_profiles_are_excluded(self) -> None:
        profiles = [
            {"layer_id": name, "use": "regular", "shape": "rect" if index == 1 else "circle",
             "size_mm": [0.6, 0.6], "offset_mm": [0.0, 0.0], "source_primitive_id": f"P{index}"}
            for index, name in enumerate(("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"))
        ]
        with self.assertRaisesRegex(ViaTransitionGeometryError, "centered circular"):
            self.build(self.design(profiles=profiles))

    def test_source_zone_stackup_center_and_barrel_containment_fail_closed(self) -> None:
        profiles = [
            {"layer_id": name, "use": "regular", "shape": "circle", "size_mm": [0.34, 0.34],
             "offset_mm": [0.0, 0.0], "source_primitive_id": f"P{index}"}
            for index, name in enumerate(("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"))
        ]
        with self.assertRaisesRegex(ViaTransitionGeometryError, "contain the plated barrel"):
            self.build(self.design(profiles=profiles))
        design = self.design()
        layer_id, net_id, zone_id = self.ids(design)
        with self.assertRaisesRegex(ViaTransitionGeometryError, "not fully contained"):
            build_via_transition_geometry(
                design, via_id=design.vias[0].id,
                antipads=[AntipadSpec(layer_id, 0.9, net_id, zone_id, 40.0, "clearance")],
            )
        design.vias[0].center_mm = (float("nan"), 3.0)
        with self.assertRaisesRegex(ViaTransitionGeometryError, "finite two-dimensional center"):
            self.build(design)
        design = self.design()
        next(item for item in design.layers if item.name == "In1.Cu").z_mm = 0.01
        with self.assertRaisesRegex(ViaTransitionGeometryError, "non-overlapping"):
            self.build(design)

    def test_complete_reference_zone_minus_antipad_is_schema_valid_and_regenerated(self) -> None:
        design = self.design()
        via_geometry = self.build(design)
        first = build_reference_plane_antipad_geometry(design, via_geometry=via_geometry)
        self.assertEqual(first, build_reference_plane_antipad_geometry(design, via_geometry=via_geometry))
        schema = json.loads(
            (ROOT / "schemas/pcb-reference-plane-antipad-geometry-v1.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(first)
        self.assertEqual(first, validate_reference_plane_antipad_geometry(
            first, design=design, via_geometry=via_geometry
        ))
        region = first["regions"][0]
        self.assertEqual(region["source_zone"]["outer_ring_mm"],
                         [[-5.0, -5.0], [9.0, -5.0], [9.0, 11.0], [-5.0, 11.0]])
        self.assertAlmostEqual(region["exact_area_mm2"], 224.0 - math.pi * 0.45 ** 2)
        self.assertFalse(first["qualification"]["native_handoff_ready"])
        self.assertFalse(first["qualification"]["physics_convergence_performed"])
        self.assertFalse(first["qualification"]["solver_ready"])

    def test_full_reference_zone_rejects_unsupported_topology_and_promoted_claims(self) -> None:
        design = self.design()
        via_geometry = self.build(design)
        report = build_reference_plane_antipad_geometry(design, via_geometry=via_geometry)
        report["qualification"]["solver_ready"] = True
        with self.assertRaisesRegex(ReferencePlaneAntipadGeometryError, "does not match"):
            validate_reference_plane_antipad_geometry(report, design=design, via_geometry=via_geometry)

        concave = self.design()
        concave_geometry = self.build(concave)
        zone = next(item for item in concave.zones if item.id == concave_geometry["antipads"][0]["reference_zone_id"])
        zone.outlines_mm = [[(-5.0, -5.0), (9.0, -5.0), (1.0, 0.0), (9.0, 11.0), (-5.0, 11.0)]]
        with self.assertRaisesRegex(ReferencePlaneAntipadGeometryError, "strictly convex"):
            build_reference_plane_antipad_geometry(concave, via_geometry=concave_geometry)

        holed = self.design()
        holed_geometry = self.build(holed)
        zone = next(item for item in holed.zones if item.id == holed_geometry["antipads"][0]["reference_zone_id"])
        zone.holes_mm = [[(6.0, 6.0), (7.0, 6.0), (7.0, 7.0), (6.0, 7.0)]]
        with self.assertRaisesRegex(ReferencePlaneAntipadGeometryError, "hole-free"):
            build_reference_plane_antipad_geometry(holed, via_geometry=holed_geometry)

    def test_complete_reference_zone_mesh_is_closed_schema_valid_and_regenerated(self) -> None:
        design = self.design()
        via_geometry = self.build(design)
        geometry = build_reference_plane_antipad_geometry(design, via_geometry=via_geometry)
        first = build_reference_plane_antipad_mesh(geometry, radial_segments=16)
        self.assertEqual(first, build_reference_plane_antipad_mesh(geometry, radial_segments=16))
        schema = json.loads(
            (ROOT / "schemas/pcb-reference-plane-antipad-mesh-v1.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(first)
        self.assertEqual(first, validate_reference_plane_antipad_mesh(first, source_geometry=geometry))
        self.assertTrue(first["topology_audit"]["passed"])
        self.assertEqual(first["topology_audit"]["closed_domains"], 1)
        self.assertEqual(first["domains"][0]["kind"], "reference_plane_full_zone")
        outer_loop = next(item for item in first["boundary_loops"] if item["role"] == "source_outer")
        outer_points = {tuple(first["vertices_mm"][index][:2]) for index in outer_loop["vertex_indices"]}
        self.assertTrue({tuple(point) for point in geometry["regions"][0]["source_zone"]["outer_ring_mm"]}
                        <= outer_points)
        antipad_loop = next(item for item in first["boundary_loops"] if item["role"] == "antipad_hole")
        vertices = first["vertices_mm"]
        center = first["center_mm"]
        distances = []
        for index, vertex_index in enumerate(antipad_loop["vertex_indices"]):
            left = vertices[vertex_index]
            right = vertices[antipad_loop["vertex_indices"][(index + 1) % len(antipad_loop["vertex_indices"])]]
            midpoint = [(left[0] + right[0]) / 2.0, (left[1] + right[1]) / 2.0]
            distances.append(math.hypot(midpoint[0] - center[0], midpoint[1] - center[1]))
        self.assertAlmostEqual(min(distances), geometry["regions"][0]["antipad_holes"][0]["radius_mm"])
        self.assertFalse(first["qualification"]["native_handoff_ready"])
        self.assertFalse(first["qualification"]["solver_ready"])

    def test_reference_zone_mesh_handles_boundary_vertex_rays_and_rejects_mutation(self) -> None:
        design = self.design()
        via_geometry = self.build(design)
        zone = next(item for item in design.zones if item.id == via_geometry["antipads"][0]["reference_zone_id"])
        zone.outlines_mm = [[(2.0, -10.0), (15.0, 3.0), (2.0, 16.0), (-11.0, 3.0)]]
        geometry = build_reference_plane_antipad_geometry(design, via_geometry=via_geometry)
        mesh = build_reference_plane_antipad_mesh(geometry, radial_segments=16)
        self.assertTrue(mesh["topology_audit"]["passed"])
        mutated = json.loads(json.dumps(mesh))
        mutated["qualification"]["solver_ready"] = True
        with self.assertRaisesRegex(ReferencePlaneAntipadMeshError, "does not match"):
            validate_reference_plane_antipad_mesh(mutated, source_geometry=geometry)
        for value in (7, 10, 132, True):
            with self.subTest(value=value), self.assertRaises(ReferencePlaneAntipadMeshError):
                build_reference_plane_antipad_mesh(geometry, radial_segments=value)


if __name__ == "__main__":
    unittest.main()
