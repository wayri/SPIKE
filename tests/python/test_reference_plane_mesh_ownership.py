from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from tests.python import test_reference_plane_antipad_mesh_v2 as fixtures
from python.spike_core.reference_plane_antipad_mesh_v2 import (
    build_reference_plane_antipad_mesh_v2,
)
from python.spike_core.reference_plane_mesh_ownership import (
    ReferencePlaneMeshOwnershipError,
    build_reference_plane_mesh_ownership_overlay,
    validate_reference_plane_mesh_ownership_overlay,
)


class ReferencePlaneMeshOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.schema = json.loads((
            root / "schemas/pcb-reference-plane-mesh-ownership-v1.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)

    def test_straight_and_curved_admitted_regions_have_owned_overlays(self) -> None:
        for geometry in fixtures.ReferencePlaneAntipadMeshV2Tests().geometries():
            with self.subTest(contract=geometry["contract"]):
                mesh = build_reference_plane_antipad_mesh_v2(geometry, radial_segments=16)
                report = build_reference_plane_mesh_ownership_overlay(
                    mesh, source_geometry=geometry
                )
                Draft202012Validator(self.schema).validate(report)
                self.assertEqual(report, validate_reference_plane_mesh_ownership_overlay(
                    report, mesh=mesh, source_geometry=geometry
                ))
                self.assertEqual(report["summary"]["checked_domains"], len(mesh["domains"]))
                self.assertEqual(report["summary"]["checked_triangles"], len(mesh["triangles"]))
                self.assertEqual(report["summary"]["checked_vertex_references"],
                                 3 * len(mesh["triangles"]))
                self.assertFalse(report["qualification"]["complete_board_copper_coverage"])
                self.assertFalse(report["qualification"]["native_geometric_overlay_verified"])
                self.assertFalse(report["qualification"]["solver_ready"])

    def test_source_boundaries_and_provenance_fail_closed(self) -> None:
        geometry = fixtures.ReferencePlaneAntipadMeshV2Tests().geometries()[0]
        mesh = build_reference_plane_antipad_mesh_v2(geometry, radial_segments=16)
        cases = []
        escaped = copy.deepcopy(mesh)
        escaped["vertices_mm"][0][0] += 100.0
        cases.append(escaped)
        orphan = copy.deepcopy(mesh)
        orphan["triangles"][0]["domain_id"] = "missing-domain"
        cases.append(orphan)
        provenance = copy.deepcopy(mesh)
        provenance["triangles"][0]["source_ids"] = ["foreign-source"]
        cases.append(provenance)
        for candidate in cases:
            with self.subTest(candidate=candidate["triangles"][0]):
                with self.assertRaises(ReferencePlaneMeshOwnershipError):
                    build_reference_plane_mesh_ownership_overlay(
                        candidate, source_geometry=geometry
                    )

    def test_report_mutation_cannot_promote_board_or_solver_readiness(self) -> None:
        geometry = fixtures.ReferencePlaneAntipadMeshV2Tests().geometries()[0]
        mesh = build_reference_plane_antipad_mesh_v2(geometry, radial_segments=16)
        report = build_reference_plane_mesh_ownership_overlay(
            mesh, source_geometry=geometry
        )
        for field in ("complete_board_copper_coverage", "native_geometric_overlay_verified",
                      "solver_ready"):
            promoted = copy.deepcopy(report)
            promoted["qualification"][field] = True
            with self.subTest(field=field), self.assertRaises(ValidationError):
                Draft202012Validator(self.schema).validate(promoted)
            with self.assertRaisesRegex(ReferencePlaneMeshOwnershipError, "regeneration"):
                validate_reference_plane_mesh_ownership_overlay(
                    promoted, mesh=mesh, source_geometry=geometry
                )


if __name__ == "__main__":
    unittest.main()
