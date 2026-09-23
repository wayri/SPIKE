from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from jsonschema import Draft202012Validator, ValidationError

from tests.python import test_via_transition_geometry as fixtures
from python.spike_core.design_ir_v2_schema import ZoneBoundaryRing, ZoneBoundarySegment
from python.spike_core.planar_curve_tessellation import (
    PlanarCurveTessellationError,
    flatten_zone_boundaries,
)
from python.spike_core.reference_plane_antipad_geometry_v3 import (
    ReferencePlaneAntipadGeometryV3Error,
    build_reference_plane_antipad_geometry_v3,
    validate_reference_plane_antipad_geometry_v3,
)


ROOT = Path(__file__).resolve().parents[2]


class ReferencePlaneAntipadGeometryV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(
            (ROOT / "schemas/pcb-reference-plane-antipad-geometry-v3.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(cls.schema)

    def fixture(self):
        helper = fixtures.ViaTransitionGeometryTests()
        design = helper.design()
        via = helper.build(design)
        zone = next(item for item in design.zones if item.id == via["antipads"][0]["reference_zone_id"])
        zone.outlines_mm = []
        zone.holes_mm = []
        zone.fill_style_id = "SOLID_FILL"
        zone.fill_property = "FILL"
        zone.boundary_rings = [
            ZoneBoundaryRing(
                role="outer", start_mm=(-5.0, -5.0), segments=[
                    ZoneBoundarySegment("line", (9.0, -5.0)),
                    ZoneBoundarySegment("arc", (9.0, 11.0), (9.0, 3.0), False),
                    ZoneBoundarySegment("line", (-5.0, 11.0)),
                    ZoneBoundarySegment("arc", (-5.0, -5.0), (-5.0, 3.0), False),
                ],
            ),
            ZoneBoundaryRing(
                role="cutout", start_mm=(-1.5, 0.0), segments=[
                    ZoneBoundarySegment("arc", (-2.5, 0.0), (-2.0, 0.0), True),
                    ZoneBoundarySegment("arc", (-1.5, 0.0), (-2.0, 0.0), True),
                ],
            ),
        ]
        return design, via

    def test_outer_and_cutout_arcs_are_bounded_deterministic_and_schema_valid(self) -> None:
        design, via = self.fixture()
        report = build_reference_plane_antipad_geometry_v3(design, via_geometry=via)
        self.assertEqual(report, build_reference_plane_antipad_geometry_v3(design, via_geometry=via))
        Draft202012Validator(self.schema).validate(report)
        self.assertEqual(report, validate_reference_plane_antipad_geometry_v3(
            report, design=design, via_geometry=via
        ))
        region = report["regions"][0]
        curve = region["curve_tessellation"]
        self.assertEqual(curve["source_arc_count"], 4)
        self.assertEqual(len(curve["arc_tessellations"]), 4)
        self.assertLessEqual(curve["maximum_certified_curve_deviation_mm"], 0.001)
        self.assertEqual([item["directed_sweep_deg"] > 0 for item in curve["arc_tessellations"]],
                         [True, True, False, False])
        self.assertEqual(len(region["source_boundary_sha256"]), 64)
        self.assertEqual(len(region["flattened_boundary_sha256"]), 64)
        self.assertFalse(report["qualification"]["conservative_copper_envelope_proven"])
        self.assertFalse(report["qualification"]["mesh_topology_admitted"])
        self.assertFalse(report["qualification"]["solver_ready"])

    def test_off_grid_curve_and_arc_budget_overflow_fail_closed(self) -> None:
        design, via = self.fixture()
        changed = copy.deepcopy(design)
        changed.zones[0].boundary_rings[0].segments[0].end_mm = (9.0000005, -5.0)
        with self.assertRaisesRegex(ReferencePlaneAntipadGeometryV3Error, "flattening"):
            build_reference_plane_antipad_geometry_v3(changed, via_geometry=via)

        huge = SimpleNamespace(
            outlines_mm=[], holes_mm=[], boundary_rings=[ZoneBoundaryRing(
                role="outer", start_mm=(0.0, -900.0), segments=[
                    ZoneBoundarySegment("arc", (0.0, 900.0), (0.0, 0.0), False),
                    ZoneBoundarySegment("line", (-1.0, 900.0)),
                    ZoneBoundarySegment("line", (0.0, -900.0)),
                ],
            )],
        )
        with self.assertRaisesRegex(PlanarCurveTessellationError, "segment budget"):
            flatten_zone_boundaries(huge)

    def test_stale_or_promoted_report_is_rejected(self) -> None:
        design, via = self.fixture()
        report = build_reference_plane_antipad_geometry_v3(design, via_geometry=via)
        report["qualification"]["solver_ready"] = True
        with self.assertRaises(ValidationError):
            Draft202012Validator(self.schema).validate(report)
        with self.assertRaisesRegex(ReferencePlaneAntipadGeometryV3Error, "does not match"):
            validate_reference_plane_antipad_geometry_v3(report, design=design, via_geometry=via)


if __name__ == "__main__":
    unittest.main()
