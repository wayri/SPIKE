from __future__ import annotations

import copy
import json
import math
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from tests.python import test_via_transition_geometry as fixtures
from python.spike_core.reference_plane_antipad_geometry_v2 import (
    ReferencePlaneAntipadGeometryV2Error,
    build_reference_plane_antipad_geometry_v2,
    validate_reference_plane_antipad_geometry_v2,
)


ROOT = Path(__file__).resolve().parents[2]


class ReferencePlaneAntipadGeometryV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads((ROOT / "schemas/pcb-reference-plane-antipad-geometry-v2.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)

    def fixture(self):
        helper = fixtures.ViaTransitionGeometryTests()
        design = helper.design()
        via = helper.build(design)
        zone = next(item for item in design.zones if item.id == via["antipads"][0]["reference_zone_id"])
        zone.outlines_mm = [[(-5, -5), (9, -5), (9, 11), (4, 5), (-5, 11)]]
        zone.holes_mm = [[(-2, -2), (-1, -2), (-1, -1), (-2, -1)]]
        return design, via, zone

    def test_concave_zone_and_existing_cutout_are_exact_grid_schema_valid(self) -> None:
        design, via, _ = self.fixture()
        report = build_reference_plane_antipad_geometry_v2(design, via_geometry=via)
        self.assertEqual(report, build_reference_plane_antipad_geometry_v2(design, via_geometry=via))
        Draft202012Validator(self.schema).validate(report)
        self.assertEqual(report, validate_reference_plane_antipad_geometry_v2(report, design=design, via_geometry=via))
        region = report["regions"][0]
        self.assertEqual(len(region["source_zone"]["source_hole_rings_mm"]), 1)
        self.assertAlmostEqual(region["exact_polygon_area_mm2"], 181.0)
        self.assertAlmostEqual(region["analytic_resolved_area_mm2"], 181.0 - math.pi * 0.45 ** 2)
        self.assertFalse(report["qualification"]["mesh_topology_admitted"])
        self.assertFalse(report["qualification"]["solver_ready"])

    def test_crossing_nested_touching_antipad_and_curves_fail_closed(self) -> None:
        design, via, zone = self.fixture()
        cases = [
            [[(8, 10), (10, 10), (10, 12), (8, 12)]],
            [[(-2, -2), (1, -2), (1, 1), (-2, 1)], [(-1, -1), (0, -1), (0, 0), (-1, 0)]],
            [[(1.5, 2.5), (2.5, 2.5), (2.5, 3.5), (1.5, 3.5)]],
        ]
        for holes in cases:
            changed = copy.deepcopy(design)
            target = next(item for item in changed.zones if item.id == zone.id)
            target.holes_mm = holes
            with self.subTest(holes=holes), self.assertRaises(ReferencePlaneAntipadGeometryV2Error):
                build_reference_plane_antipad_geometry_v2(changed, via_geometry=via)
        zone.boundary_rings = [object()]
        with self.assertRaisesRegex(ReferencePlaneAntipadGeometryV2Error, "straight segments only"):
            build_reference_plane_antipad_geometry_v2(design, via_geometry=via)

    def test_promoted_or_stale_report_is_rejected(self) -> None:
        design, via, _ = self.fixture()
        report = build_reference_plane_antipad_geometry_v2(design, via_geometry=via)
        report["qualification"]["solver_ready"] = True
        with self.assertRaises(ValidationError):
            Draft202012Validator(self.schema).validate(report)
        with self.assertRaisesRegex(ReferencePlaneAntipadGeometryV2Error, "does not match"):
            validate_reference_plane_antipad_geometry_v2(report, design=design, via_geometry=via)


if __name__ == "__main__":
    unittest.main()
