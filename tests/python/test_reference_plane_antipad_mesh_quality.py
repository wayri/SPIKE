from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from tests.python.test_reference_plane_antipad_native_handoff import full_plane_fixture
from python.spike_core.reference_plane_antipad_mesh_quality import (
    ReferencePlaneAntipadMeshQualityError,
    build_reference_plane_antipad_mesh_quality,
    validate_reference_plane_antipad_mesh_quality,
)


ROOT = Path(__file__).resolve().parents[2]


class ReferencePlaneAntipadMeshQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads((ROOT / "schemas/pcb-reference-plane-antipad-mesh-quality-v1.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)

    def test_report_is_deterministic_schema_valid_regenerated_and_geometry_only(self) -> None:
        geometry, _ = full_plane_fixture()
        report = build_reference_plane_antipad_mesh_quality(geometry)
        self.assertEqual(report, build_reference_plane_antipad_mesh_quality(geometry))
        Draft202012Validator(self.schema).validate(report)
        self.assertEqual(report, validate_reference_plane_antipad_mesh_quality(report, source_geometry=geometry))
        self.assertEqual([item["radial_segments"] for item in report["levels"]], [8, 16, 32, 64])
        self.assertTrue(report["convergence"]["surface_errors_nonincreasing"])
        self.assertTrue(all(item["native_admission_passed"] for item in report["levels"]))
        self.assertFalse(report["qualification"]["physics_convergence_performed"])
        self.assertFalse(report["qualification"]["solver_ready"])

    def test_invalid_policy_and_strict_terminal_gate_fail_closed(self) -> None:
        geometry, _ = full_plane_fixture()
        for levels in ((8, 16, 32), (8, 16, 24, 48), (True, 16, 32, 64)):
            with self.subTest(levels=levels), self.assertRaises(ReferencePlaneAntipadMeshQualityError):
                build_reference_plane_antipad_mesh_quality(geometry, radial_levels=levels)
        with self.assertRaises(ReferencePlaneAntipadMeshQualityError):
            build_reference_plane_antipad_mesh_quality(geometry, maximum_terminal_relative_error=1e-10)

    def test_mutation_and_physics_promotion_fail_closed(self) -> None:
        geometry, _ = full_plane_fixture()
        report = build_reference_plane_antipad_mesh_quality(geometry)
        promoted = copy.deepcopy(report)
        promoted["qualification"]["solver_ready"] = True
        with self.assertRaises(ValidationError):
            Draft202012Validator(self.schema).validate(promoted)
        with self.assertRaisesRegex(ReferencePlaneAntipadMeshQualityError, "does not match"):
            validate_reference_plane_antipad_mesh_quality(promoted, source_geometry=geometry)


if __name__ == "__main__":
    unittest.main()
