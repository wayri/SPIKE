# SPDX-License-Identifier: Apache-2.0
"""Deterministic area and rejection checks for thermal copper rasterization."""

import unittest

import numpy as np

from python.spike_core.contracts import DesignIR
from python.spike_core.thermal_copper_geometry import CopperGeometryError, rasterize_copper


LAYERS = ["F.Cu", "In1.Cu", "B.Cu"]


def raster(design, *, sigma=0, **options):
    return rasterize_copper(design, (0, 0, 4, 4), (4, 4), (1, 1), LAYERS,
                            fuzzy_sigma_mm=sigma, samples_per_axis=10, **options)


class CopperGeometryTests(unittest.TestCase):
    def test_filled_zone_with_cutout_and_rejection_of_outline(self):
        zone = {"layer": "F.Cu", "points": [[0, 0], [4, 0], [4, 4], [0, 4]],
                "holes": [[[1, 1], [3, 1], [3, 3], [1, 3]]],
                "filled_copper_state": "source_filled", "source_fill_provenance_complete": True}
        design = DesignIR(zones=[zone])
        fields, diagnostics = raster(design)
        self.assertAlmostEqual(float(fields["F.Cu"].sum()), 12.0, places=12)
        self.assertEqual(float(fields["F.Cu"][1, 1]), 0.0)
        self.assertEqual(float(fields["In1.Cu"].sum()), 0.0)
        self.assertEqual(diagnostics[0]["code"], "THERMAL_COPPER_SAMPLED")
        zone["filled_copper_state"] = "outline_fallback"
        with self.assertRaises(CopperGeometryError) as error:
            raster(design)
        self.assertEqual(error.exception.diagnostics[0]["path"], "design.zones[0]")

    def test_track_pad_union_and_via_span(self):
        design = DesignIR(
            tracks=[{"layer": "F.Cu", "start": [0.5, 0.5], "end": [3.5, 0.5], "width": 1.0}],
            pads=[{"layer": "F.Cu", "at": [2, 0.5], "size": [1, 1], "shape": "rect"}],
            vias=[{"layers": ["F.Cu", "B.Cu"], "at": [2, 2], "size": 1.0, "drill": 0.4}],
        )
        fields, _ = raster(design)
        self.assertGreater(float(fields["F.Cu"].sum()), 3.0)
        self.assertLess(float(fields["F.Cu"].sum()), 5.0)  # pad overlaps track
        self.assertAlmostEqual(float(fields["In1.Cu"].sum()), float(fields["B.Cu"].sum()))
        self.assertGreater(float(fields["In1.Cu"].sum()), 0.5)
        self.assertLess(float(fields["In1.Cu"].sum()), 0.8)

    def test_roundrect_corners_and_source_bridge_cutout(self):
        pad = {"layer": "F.Cu", "at": [0.5, 0.5], "size": [1, 1],
               "shape": "roundrect", "roundrect_rratio": 0.4}
        # The retraced bridge connects the outer and inner boundary in a
        # source-filled flat polygon path; even-odd scanlines retain its void.
        path = [[1, 1], [4, 1], [4, 4], [1, 4], [1, 1],
                [2, 2], [2, 3], [3, 3], [3, 2], [2, 2], [1, 1]]
        zone = {"layer": "B.Cu", "points": path,
                "filled_copper_state": "source_filled",
                "source_fill_representation": "flat_polygon_path",
                "source_fill_provenance_complete": True}
        fields, _ = raster(DesignIR(pads=[pad], zones=[zone]))
        self.assertLess(float(fields["F.Cu"].sum()), 1.0)
        self.assertGreater(float(fields["F.Cu"].sum()), 0.7)
        self.assertAlmostEqual(float(fields["B.Cu"].sum()), 8.0, places=12)

    def test_fuzzy_conserves_area_and_reveals_neighbor_density(self):
        design = DesignIR(pads=[{"layer": "F.Cu", "at": [0.5, 0.5],
                                 "size": [1, 1], "shape": "rect"}])
        crisp, _ = raster(design)
        fuzzy, diagnostics = raster(design, sigma=0.8)
        self.assertAlmostEqual(float(crisp["F.Cu"].sum()), 1.0)
        self.assertAlmostEqual(float(fuzzy["F.Cu"].sum()), 1.0, places=12)
        self.assertGreater(float(fuzzy["F.Cu"][0, 1]), 0)
        self.assertLess(float(fuzzy["F.Cu"][0, 0]), 1)
        self.assertTrue(np.all((fuzzy["F.Cu"] >= 0) & (fuzzy["F.Cu"] <= 1)))
        self.assertEqual(diagnostics[-1]["code"], "THERMAL_COPPER_FUZZY")

    def test_bad_via_and_unknown_layer_fail_closed(self):
        for design in (DesignIR(vias=[{"layers": ["F.Cu", "B.Cu"], "at": [2, 2],
                                      "size": 0.4, "drill": 0.5}]),
                       DesignIR(tracks=[{"layer": "Unknown.Cu", "start": [0, 0],
                                         "end": [1, 1], "width": 0.2}])):
            with self.subTest(design=design), self.assertRaises(CopperGeometryError):
                raster(design)


if __name__ == "__main__":
    unittest.main()
