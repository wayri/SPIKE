from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from tests.python import test_reference_plane_antipad_mesh_v2 as fixtures
from python.spike_core.generalized_reference_plane_mesh_quality import (
    GeneralizedReferencePlaneMeshQualityError,
    build_generalized_reference_plane_mesh_quality,
    validate_generalized_reference_plane_mesh_quality,
)


class GeneralizedReferencePlaneMeshQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.schema = json.loads((root / "schemas/pcb-reference-plane-antipad-mesh-quality-v2.schema.json")
                                .read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)

    def test_v2_and_v3_four_level_geometry_convergence_is_regenerated(self) -> None:
        for geometry in fixtures.ReferencePlaneAntipadMeshV2Tests().geometries():
            with self.subTest(contract=geometry["contract"]):
                report = build_generalized_reference_plane_mesh_quality(geometry)
                Draft202012Validator(self.schema).validate(report)
                self.assertEqual(report, build_generalized_reference_plane_mesh_quality(geometry))
                self.assertEqual(report, validate_generalized_reference_plane_mesh_quality(
                    report, source_geometry=geometry))
                self.assertEqual([item["radial_segments"] for item in report["levels"]],
                                 [8, 16, 32, 64])
                errors = [item["regions"][0]["relative_area_error"]
                          for item in report["levels"]]
                self.assertEqual(errors, sorted(errors, reverse=True))
                self.assertTrue(all(item["native_admission_passed"]
                                    for item in report["levels"]))
                self.assertTrue(report["qualification"]["geometry_convergence_passed"])
                self.assertFalse(report["qualification"]["field_convergence_performed"])
                self.assertFalse(report["qualification"]["solver_ready"])

    def test_cancellation_and_promoted_or_stale_reports_fail_closed(self) -> None:
        geometry = fixtures.ReferencePlaneAntipadMeshV2Tests().geometries()[0]
        with self.assertRaisesRegex(GeneralizedReferencePlaneMeshQualityError, "cancelled"):
            build_generalized_reference_plane_mesh_quality(geometry, cancel_check=lambda: True)
        report = build_generalized_reference_plane_mesh_quality(geometry)
        changed = copy.deepcopy(report)
        changed["qualification"]["solver_ready"] = True
        with self.assertRaises(ValidationError):
            Draft202012Validator(self.schema).validate(changed)
        with self.assertRaisesRegex(GeneralizedReferencePlaneMeshQualityError, "does not match"):
            validate_generalized_reference_plane_mesh_quality(changed, source_geometry=geometry)


if __name__ == "__main__":
    unittest.main()
