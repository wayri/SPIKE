from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.via_transition_geometry import AntipadSpec, build_via_transition_geometry
from python.spike_core.via_transition_mesh import ViaTransitionMeshError, build_via_transition_mesh
from python.spike_core.via_transition_native_handoff import (
    ViaTransitionNativeHandoffError,
    build_native_via_transition_handoff,
)


ROOT = Path(__file__).resolve().parents[2]


def geometry_fixture() -> dict:
    names = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
    legacy = DesignIR(
        design_id="native-handoff-board", name="native-handoff-board", source_format="fixture",
        layers=[{"id": index, "name": name, "type": "copper", "thickness_mm": 0.035}
                for index, name in enumerate(names)],
        nets=[{"id": 1, "name": "SIG"}, {"id": 2, "name": "GND"}],
        vias=[{"id": "V1", "net_name": "SIG", "at": [2.0, 3.0], "diameter": 0.6,
               "drill": 0.3, "plating_mm": 0.025, "layers": ["F.Cu", "B.Cu"], "type": "through"}],
        zones=[{"id": f"GND:{name}", "net_name": "GND", "layer": name,
                "polygons": [[[-5.0, -5.0], [9.0, -5.0], [9.0, 11.0], [-5.0, 11.0]]]}
               for name in names],
        metadata={"source_sha256": "c" * 64},
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


class ViaTransitionNativeHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(
            (ROOT / "schemas/native-via-transition-handoff-v1.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

    def test_native_handoff_is_schema_valid_and_physics_blocked(self) -> None:
        geometry = geometry_fixture()
        mesh = build_via_transition_mesh(geometry, radial_segments=8)
        result = build_native_via_transition_handoff(mesh, source_geometry=geometry)
        self.validator.validate(result)
        self.assertEqual(result["native_validation"]["vertex_count"], len(mesh["vertices_mm"]))
        self.assertEqual(result["native_validation"]["triangle_count"], len(mesh["triangles"]))
        self.assertFalse(result["native_validation"]["solver_entry_points_exposed"])
        self.assertEqual(result["qualification"]["state"], "geometry_handoff_only")
        self.assertFalse(result["qualification"]["capacitance_ready"])
        self.assertFalse(result["qualification"]["si_ready"])
        self.assertFalse(result["qualification"]["solver_ready"])

    def test_changed_geometry_is_rejected_before_native_admission(self) -> None:
        geometry = geometry_fixture()
        mesh = build_via_transition_mesh(geometry, radial_segments=8)
        changed = copy.deepcopy(geometry)
        changed["drill_diameter_mm"] += 0.01
        with self.assertRaises(ViaTransitionMeshError):
            build_native_via_transition_handoff(mesh, source_geometry=changed)

    def test_schema_rejects_any_physics_promotion(self) -> None:
        geometry = geometry_fixture()
        result = build_native_via_transition_handoff(
            build_via_transition_mesh(geometry, radial_segments=8), source_geometry=geometry
        )
        for field in ("capacitance_ready", "si_ready", "solver_ready"):
            promoted = copy.deepcopy(result)
            promoted["qualification"][field] = True
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.validator.validate(promoted)

    def test_missing_native_symbol_fails_closed(self) -> None:
        import python.spike_core.via_transition_native_handoff as module

        original = module._load_native
        module._load_native = lambda: object()
        try:
            geometry = geometry_fixture()
            mesh = build_via_transition_mesh(geometry, radial_segments=8)
            with self.assertRaises(ViaTransitionNativeHandoffError):
                build_native_via_transition_handoff(mesh, source_geometry=geometry)
        finally:
            module._load_native = original


if __name__ == "__main__":
    unittest.main()
