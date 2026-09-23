from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from tests.python import test_reference_plane_antipad_mesh_v2 as fixtures
from python.spike_core.generalized_reference_plane_native_handoff import (
    GeneralizedReferencePlaneNativeHandoffError,
    build_generalized_reference_plane_native_handoff,
)
from python.spike_core.reference_plane_antipad_mesh_v2 import (
    build_reference_plane_antipad_mesh_v2,
)


class GeneralizedReferencePlaneNativeHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.schema = json.loads((root / "schemas/native-reference-plane-antipad-handoff-v2.schema.json")
                                .read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)

    def test_v2_and_v3_closed_loops_pass_solver_isolated_native_admission(self) -> None:
        for geometry in fixtures.ReferencePlaneAntipadMeshV2Tests().geometries():
            with self.subTest(contract=geometry["contract"]):
                mesh = build_reference_plane_antipad_mesh_v2(geometry, radial_segments=16)
                report = build_generalized_reference_plane_native_handoff(
                    mesh, source_geometry=geometry)
                self.assertEqual(report, build_generalized_reference_plane_native_handoff(
                    mesh, source_geometry=geometry))
                Draft202012Validator(self.schema).validate(report)
                self.assertTrue(report["native_validation"]["complete_loop_coverage_checked"])
                self.assertTrue(report["native_validation"]["source_curve_claim_checked"])
                self.assertFalse(report["native_validation"]["solver_entry_points_exposed"])
                self.assertFalse(report["qualification"]["solver_ready"])

    def test_stale_mesh_and_promoted_report_fail_closed(self) -> None:
        geometry = fixtures.ReferencePlaneAntipadMeshV2Tests().geometries()[0]
        mesh = build_reference_plane_antipad_mesh_v2(geometry, radial_segments=16)
        stale = copy.deepcopy(mesh)
        stale["boundary_loops"].pop()
        with self.assertRaises(GeneralizedReferencePlaneNativeHandoffError):
            build_generalized_reference_plane_native_handoff(stale, source_geometry=geometry)
        report = build_generalized_reference_plane_native_handoff(mesh, source_geometry=geometry)
        report["qualification"]["solver_ready"] = True
        with self.assertRaises(ValidationError):
            Draft202012Validator(self.schema).validate(report)


if __name__ == "__main__":
    unittest.main()
