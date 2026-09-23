from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from python.spike_core.reference_plane_antipad_geometry import build_reference_plane_antipad_geometry
from python.spike_core.reference_plane_antipad_mesh import (
    ReferencePlaneAntipadMeshError,
    build_reference_plane_antipad_mesh,
)
from python.spike_core.reference_plane_antipad_native_handoff import (
    ReferencePlaneAntipadNativeHandoffError,
    build_native_reference_plane_antipad_handoff,
)


ROOT = Path(__file__).resolve().parents[2]


def full_plane_fixture() -> tuple[dict, dict]:
    # The exact full-zone builder needs the source DesignIR as well as its via artifact.
    from tests.python.test_via_transition_geometry import ViaTransitionGeometryTests

    helper = ViaTransitionGeometryTests()
    design = helper.design()
    via_geometry = helper.build(design)
    geometry = build_reference_plane_antipad_geometry(design, via_geometry=via_geometry)
    return geometry, build_reference_plane_antipad_mesh(geometry, radial_segments=16)


class ReferencePlaneAntipadNativeHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(
            (ROOT / "schemas/native-reference-plane-antipad-handoff-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

    def test_real_native_handoff_is_schema_valid_and_physics_blocked(self) -> None:
        geometry, mesh = full_plane_fixture()
        result = build_native_reference_plane_antipad_handoff(mesh, source_geometry=geometry)
        self.validator.validate(result)
        self.assertEqual(result["native_validation"]["vertex_count"], len(mesh["vertices_mm"]))
        self.assertEqual(result["native_validation"]["triangle_count"], len(mesh["triangles"]))
        self.assertEqual(result["native_validation"]["domain_count"], len(mesh["domains"]))
        self.assertFalse(result["native_validation"]["solver_entry_points_exposed"])
        self.assertFalse(result["qualification"]["physics_convergence_performed"])
        self.assertFalse(result["qualification"]["capacitance_ready"])
        self.assertFalse(result["qualification"]["si_ready"])
        self.assertFalse(result["qualification"]["solver_ready"])

    def test_changed_geometry_is_rejected_before_native_admission(self) -> None:
        geometry, mesh = full_plane_fixture()
        changed = copy.deepcopy(geometry)
        changed["regions"][0]["antipad_holes"][0]["radius_mm"] += 0.01
        with self.assertRaises(ReferencePlaneAntipadMeshError):
            build_native_reference_plane_antipad_handoff(mesh, source_geometry=changed)

    def test_schema_rejects_any_physics_promotion(self) -> None:
        geometry, mesh = full_plane_fixture()
        result = build_native_reference_plane_antipad_handoff(mesh, source_geometry=geometry)
        for field in ("physics_convergence_performed", "capacitance_ready", "si_ready", "solver_ready"):
            promoted = copy.deepcopy(result)
            promoted["qualification"][field] = True
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.validator.validate(promoted)

    def test_missing_native_symbol_fails_closed(self) -> None:
        import python.spike_core.reference_plane_antipad_native_handoff as module

        original = module._native
        module._native = lambda: object()
        try:
            geometry, mesh = full_plane_fixture()
            with self.assertRaises(ReferencePlaneAntipadNativeHandoffError):
                build_native_reference_plane_antipad_handoff(mesh, source_geometry=geometry)
        finally:
            module._native = original


if __name__ == "__main__":
    unittest.main()
