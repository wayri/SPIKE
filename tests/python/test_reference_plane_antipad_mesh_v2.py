from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from tests.python import test_reference_plane_antipad_geometry_v2 as geometry_v2_fixtures
from tests.python import test_reference_plane_antipad_geometry_v3 as geometry_v3_fixtures
from python.spike_core.reference_plane_antipad_geometry_v2 import (
    build_reference_plane_antipad_geometry_v2,
)
from python.spike_core.reference_plane_antipad_geometry_v3 import (
    build_reference_plane_antipad_geometry_v3,
)
from python.spike_core.reference_plane_antipad_mesh_v2 import (
    ReferencePlaneAntipadMeshV2Error,
    build_reference_plane_antipad_mesh_v2,
    validate_reference_plane_antipad_mesh_v2,
)


class ReferencePlaneAntipadMeshV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.schema = json.loads((root / "schemas/pcb-reference-plane-antipad-mesh-v2.schema.json")
                                .read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)

    def geometries(self):
        design_v2, via_v2, _ = geometry_v2_fixtures.ReferencePlaneAntipadGeometryV2Tests().fixture()
        design_v3, via_v3 = geometry_v3_fixtures.ReferencePlaneAntipadGeometryV3Tests().fixture()
        return [
            build_reference_plane_antipad_geometry_v2(design_v2, via_geometry=via_v2),
            build_reference_plane_antipad_geometry_v3(design_v3, via_geometry=via_v3),
        ]

    def test_v2_and_v3_form_deterministic_closed_solver_blocked_meshes(self) -> None:
        for geometry in self.geometries():
            with self.subTest(contract=geometry["contract"]):
                mesh = build_reference_plane_antipad_mesh_v2(geometry, radial_segments=16)
                Draft202012Validator(self.schema).validate(mesh)
                self.assertEqual(mesh, build_reference_plane_antipad_mesh_v2(
                    geometry, radial_segments=16))
                self.assertEqual(mesh, validate_reference_plane_antipad_mesh_v2(
                    mesh, source_geometry=geometry))
                self.assertTrue(mesh["topology_audit"]["passed"])
                self.assertTrue(mesh["qualification"]["mesh_topology_admitted"])
                self.assertTrue(mesh["qualification"]["conservative_antipad_void_proven"])
                self.assertFalse(mesh["qualification"]["native_handoff_ready"])
                self.assertFalse(mesh["qualification"]["solver_ready"])
                roles = {item["role"] for item in mesh["boundary_loops"]}
                self.assertEqual(roles, {"source_outer", "source_cutout", "antipad_hole"})
                self.assertEqual({item["surface"] for item in mesh["boundary_loops"]},
                                 {"lower", "upper"})
                surface_roles = {item["surface_role"] for item in mesh["triangles"]}
                self.assertIn("source_cutout_boundary", surface_roles)
                self.assertIn("antipad_void_boundary", surface_roles)

    def test_curve_provenance_and_conservative_source_claim_are_honest(self) -> None:
        straight, curved = self.geometries()
        exact_mesh = build_reference_plane_antipad_mesh_v2(straight, radial_segments=16)
        curved_mesh = build_reference_plane_antipad_mesh_v2(curved, radial_segments=16)
        self.assertTrue(exact_mesh["qualification"]["conservative_source_copper_envelope_proven"])
        self.assertFalse(curved_mesh["qualification"]["conservative_source_copper_envelope_proven"])
        self.assertGreater(curved_mesh["tessellation"]["maximum_source_curve_deviation_mm"], 0)
        self.assertIn("source_boundary_sha256", curved_mesh["domains"][0])
        self.assertIn("flattened_boundary_sha256", curved_mesh["domains"][0])

    def test_cancellation_resources_and_stale_evidence_fail_closed(self) -> None:
        geometry = self.geometries()[0]
        with self.assertRaisesRegex(ReferencePlaneAntipadMeshV2Error, "cancelled"):
            build_reference_plane_antipad_mesh_v2(geometry, cancel_check=lambda: True)
        with self.assertRaisesRegex(ReferencePlaneAntipadMeshV2Error, "work"):
            build_reference_plane_antipad_mesh_v2(geometry, maximum_work_steps=1)
        mesh = build_reference_plane_antipad_mesh_v2(geometry, radial_segments=16)
        self.assertLessEqual(mesh["resources"]["actual_work_steps"],
                             mesh["resources"]["maximum_work_steps"])
        stale = copy.deepcopy(mesh)
        stale["qualification"]["solver_ready"] = True
        with self.assertRaises(ValidationError):
            Draft202012Validator(self.schema).validate(stale)
        with self.assertRaisesRegex(ReferencePlaneAntipadMeshV2Error, "does not match"):
            validate_reference_plane_antipad_mesh_v2(stale, source_geometry=geometry)


if __name__ == "__main__":
    unittest.main()
