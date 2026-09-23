# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Independent geometry/units checks for the PEEC magnetic handoff."""

import math
import unittest

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.hybrid_mesh import MeshBranch, build_hybrid_mesh
from python.spike_core.peec_magnetic_geometry import (
    MagneticGeometryError,
    describe_magnetic_cross_section,
)


def branch(kind="via", width=None, thickness=0.025, source_id="v1"):
    drill = 0.3
    equivalent_width = math.pi * (drill + thickness)
    return MeshBranch(
        "b1", kind, 0, 1, (1.0, 2.0, 0.0), (1.0, 2.0, 0.14),
        equivalent_width if width is None else width, thickness, 5.8e7,
        "F.Cu->B.Cu", "VCC", source_id,
    )


class PEECMagneticGeometryTests(unittest.TestCase):
    def test_mesh_generated_via_preserves_separate_magnetic_geometry(self):
        design = DesignIR(
            layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            vias=[{"id": "v1", "at": [1.0, 2.0], "drill": 0.3,
                   "layers": ["F.Cu", "B.Cu"], "net_name": "VCC"}],
        )
        mesh = build_hybrid_mesh(
            design, AnalysisSpec(mode="ac", net_names=["VCC"], mesh={"target_size_mm": 1.0})
        )
        via = next(item for item in mesh.branches if item.kind == "via")
        section = describe_magnetic_cross_section(design, via)
        self.assertAlmostEqual(section.inner_radius_mm, 0.15)
        self.assertAlmostEqual(section.outer_radius_mm, 0.175)
        self.assertAlmostEqual(section.area_mm2, via.width_mm * via.thickness_mm)
        self.assertIsNone(section.width_mm)

    def test_via_annulus_uses_physical_radius_not_resistance_width(self):
        conductor = branch()
        section = describe_magnetic_cross_section(
            DesignIR(vias=[{"id": "v1", "drill": 0.3}]), conductor
        )
        self.assertEqual(section.shape, "circular_annulus")
        self.assertAlmostEqual(section.inner_radius_mm, 0.15, places=12)
        self.assertAlmostEqual(section.outer_radius_mm, 0.175, places=12)
        self.assertAlmostEqual(section.area_mm2, math.pi * (0.175**2 - 0.15**2), places=12)
        self.assertIsNone(section.width_mm)
        self.assertGreater(conductor.width_mm, section.outer_radius_mm * 2)

    def test_circular_plated_pad_barrel_uses_drill_size(self):
        conductor = branch("pad_barrel", source_id="pad-a")
        section = describe_magnetic_cross_section(
            DesignIR(pads=[{"id": "pad-a", "drill_size": [0.3, 0.3], "plated": True}]),
            conductor,
        )
        self.assertAlmostEqual(section.inner_radius_mm, 0.15)
        self.assertAlmostEqual(section.outer_radius_mm, 0.175)

    def test_track_is_a_finite_rectangle_with_mm_squared_area(self):
        conductor = branch("track", width=0.2, thickness=0.035)
        section = describe_magnetic_cross_section(DesignIR(), conductor)
        self.assertEqual(section.shape, "rectangle")
        self.assertAlmostEqual(section.area_mm2, 0.007)
        self.assertEqual((section.width_mm, section.thickness_mm), (0.2, 0.035))

    def test_graph_only_attachment_is_not_a_magnetic_filament(self):
        with self.assertRaisesRegex(MagneticGeometryError, "graph-only"):
            describe_magnetic_cross_section(
                DesignIR(), branch("pad_attachment", width=0.2, thickness=0.035)
            )

    def test_oval_pad_barrel_fails_closed(self):
        design = DesignIR(pads=[{
            "id": "v1", "drill_size": [0.4, 0.3], "drill_shape": "oval", "plated": True,
        }])
        with self.assertRaisesRegex(MagneticGeometryError, "noncircular"):
            describe_magnetic_cross_section(design, branch("pad_barrel"))

    def test_inconsistent_or_invalid_dimensions_fail_closed(self):
        design = DesignIR(vias=[{"id": "v1", "drill": 0.3}])
        with self.assertRaisesRegex(MagneticGeometryError, "area"):
            describe_magnetic_cross_section(design, branch(width=0.3))
        with self.assertRaisesRegex(MagneticGeometryError, "finite positive"):
            describe_magnetic_cross_section(design, branch(thickness=float("nan")))
        with self.assertRaisesRegex(MagneticGeometryError, "finite positive"):
            describe_magnetic_cross_section(DesignIR(vias=[{"id": "v1", "drill": 0}]), branch())
        with self.assertRaisesRegex(MagneticGeometryError, "units=mm"):
            describe_magnetic_cross_section(DesignIR(units="mil", vias=design.vias), branch())

    def test_missing_or_ambiguous_source_fails_closed(self):
        with self.assertRaisesRegex(MagneticGeometryError, "found 0"):
            describe_magnetic_cross_section(DesignIR(), branch())
        duplicated = DesignIR(vias=[{"id": "v1", "drill": 0.3}, {"id": "v1", "drill": 0.3}])
        with self.assertRaisesRegex(MagneticGeometryError, "found 2"):
            describe_magnetic_cross_section(duplicated, branch())

    def test_nonvertical_barrel_fails_closed(self):
        conductor = branch()
        conductor.end_mm = (1.1, 2.0, 0.14)
        with self.assertRaisesRegex(MagneticGeometryError, "vertical"):
            describe_magnetic_cross_section(DesignIR(vias=[{"id": "v1", "drill": 0.3}]), conductor)

    def test_malformed_numeric_and_huge_coordinate_fail_closed(self):
        design = DesignIR(vias=[{"id": "v1", "drill": 0.3}])
        for bad in (True, "0.025", 10**10000):
            conductor = branch()
            conductor.thickness_mm = bad
            with self.subTest(bad_type=type(bad).__name__), self.assertRaises(MagneticGeometryError):
                describe_magnetic_cross_section(design, conductor)
        conductor = branch()
        conductor.start_mm = (10**10000, 2.0, 0.0)
        with self.assertRaisesRegex(MagneticGeometryError, "endpoints"):
            describe_magnetic_cross_section(design, conductor)
        conductor = branch("track", width=1e308, thickness=1e308)
        with self.assertRaisesRegex(MagneticGeometryError, "area"):
            describe_magnetic_cross_section(design, conductor)

    def test_large_coordinate_does_not_hide_barrel_axis_tilt(self):
        conductor = branch()
        conductor.start_mm = (1e9, 2.0, 0.0)
        conductor.end_mm = (1e9 + 1e-4, 2.0, 0.14)
        with self.assertRaisesRegex(MagneticGeometryError, "vertical"):
            describe_magnetic_cross_section(
                DesignIR(vias=[{"id": "v1", "drill": 0.3}]), conductor
            )


if __name__ == "__main__":
    unittest.main()
