# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Exact pad lowering and port contact tests without an external engine."""
import ast
import math
import unittest

from python.spike_core.openems_adapter_source import OPENEMS_DRIVER, pad_polygon
from python.spike_core.openems_geometry_admission import screen_geometry
from python.spike_core.openems_validation import _conductor_hits
from tests.python.test_openems_far_field import far_field_design, far_field_spec


class PadGeometryTests(unittest.TestCase):
    def pad(self, **options):
        return {"id": "rotated", "net_name": "RF", "shape": "rect", "at": [2, 3],
                "size": [4, 1], "rotation": 90, "layer": "F.Cu", **options}

    def test_worker_and_admission_share_exact_lowering(self):
        parsed = ast.parse(OPENEMS_DRIVER)
        body = [node for node in parsed.body if isinstance(node, ast.FunctionDef)
                and node.name == "pad_polygon"]
        namespace = {"math": math}
        exec(compile(ast.Module(body=body, type_ignores=[]), "pad-worker", "exec"), namespace)
        for angle in (0, 30, 90, 180, -53, 390):
            pad = self.pad(rotation=angle)
            self.assertEqual(namespace["pad_polygon"](pad), pad_polygon(pad))
            x, y = pad_polygon(pad)
            area = abs(sum(x[i]*y[(i+1)%4]-x[(i+1)%4]*y[i] for i in range(4)))/2
            self.assertAlmostEqual(area, 4)
            self.assertAlmostEqual(sum(x)/4, 2)
            self.assertAlmostEqual(sum(y)/4, 3)
        x, y = pad_polygon(self.pad())
        self.assertAlmostEqual(max(x)-min(x), 1)
        self.assertAlmostEqual(max(y)-min(y), 4)

    def test_admission_accepts_rotation_and_stays_unqualified(self):
        design, spec = far_field_design(), far_field_spec()
        design.pads = [self.pad()]
        report = screen_geometry(design, spec)
        self.assertTrue(report["screen_passed"])
        self.assertFalse(report["production_qualified"])

    def test_ports_match_rotated_footprint(self):
        design = far_field_design()
        design.tracks = []
        design.pads = [self.pad()]
        self.assertEqual(_conductor_hits(design, {"RF"}, [2, 4.8, 0], 1e-6), {"RF"})
        self.assertEqual(_conductor_hits(design, {"RF"}, [3.8, 3, 0], 1e-6), set())
        self.assertEqual(_conductor_hits(design, {"RF"}, [2.5, 3, 0], 1e-6), {"RF"})

    def test_invalid_geometry_and_unsupported_shapes_fail_closed(self):
        for options in ({"shape": "custom"}, {"shape": "roundrect"},
                        {"drill": .2}, {"plated": True}, {"size": [0, 1]},
                        {"size": [True, 1]}, {"size": [1]}, {"at": [math.nan, 0]},
                        {"drill_size": [0.2, 0.2]}, {"pad_kind": "thru_hole"},
                        {"rotation": "90"}, {"rotation": 10**1000},
                        {"rotation": math.inf}, {"at": [1e300, 0]}):
            with self.subTest(options=options):
                pad = self.pad(**options)
                with self.assertRaises(ValueError):
                    pad_polygon(pad)
                design, spec = far_field_design(), far_field_spec()
                design.pads = [pad]
                self.assertFalse(screen_geometry(design, spec)["screen_passed"])

    def test_kicad_undrilled_pad_marker_is_supported(self):
        pad = self.pad(drill=0, drill_shape="none", plated=None)
        self.assertEqual(pad_polygon(pad), pad_polygon(self.pad()))
        design, spec = far_field_design(), far_field_spec()
        design.pads = [pad]
        self.assertTrue(screen_geometry(design, spec)["screen_passed"])

    def test_unsupported_contours_do_not_supply_port_contacts(self):
        design = far_field_design()
        design.tracks = []
        for shape in ("custom", "trapezoid"):
            design.pads = [self.pad(shape=shape)]
            self.assertEqual(_conductor_hits(design, {"RF"}, [2, 3, 0], 1e-6), set())

    def test_rounded_contours_have_bounded_area_error_and_contact(self):
        fixtures = (
            ({"shape": "circle", "size": [2, 2]}, math.pi),
            ({"shape": "oval", "size": [4, 2]}, math.pi + 4),
            ({"shape": "roundrect", "size": [4, 2], "roundrect_rratio": .25},
             8 - (4 - math.pi) * .5**2),
        )
        for options, area in fixtures:
            with self.subTest(shape=options["shape"]):
                pad = self.pad(**options)
                x, y = pad_polygon(pad)
                parsed = ast.parse(OPENEMS_DRIVER)
                body = [node for node in parsed.body if isinstance(node, ast.FunctionDef)
                        and node.name == "pad_polygon"]
                namespace = {"math": math}
                exec(compile(ast.Module(body=body, type_ignores=[]), "pad-worker", "exec"), namespace)
                self.assertEqual([x, y], namespace["pad_polygon"](pad))
                n = len(x)
                polygon_area = abs(sum(x[i]*y[(i+1)%n]-x[(i+1)%n]*y[i]
                                       for i in range(n)))/2
                self.assertLess(abs(polygon_area-area), .02)
                design = far_field_design()
                design.tracks = []
                design.pads = [pad]
                self.assertEqual(_conductor_hits(design, {"RF"}, [2, 3, 0], 1e-6), {"RF"})
                self.assertTrue(screen_geometry(design, far_field_spec())["screen_passed"])


if __name__ == "__main__":
    unittest.main()
