# SPDX-License-Identifier: Apache-2.0
"""Contact candidates must preserve the full-scan observation predicates."""

from math import cos, inf, nextafter, sin
import random
import unittest

from python.spike_core.hybrid_mesh import _pad_boundary_polygon
from python.spike_core.source_filled_boundary import (
    SourceFilledBoundary, prepare_source_filled_boundary,
)
from python.spike_core.zone_pad_connection_evidence import _observes_contact


class FullScanBoundary(SourceFilledBoundary):
    """Disable candidate pruning without changing containment or final gates."""

    def query_points(self, bounds):
        return self.points

    def query_edges(self, bounds):
        return self.edges


def annulus(scale=1.0, angle=0.0, offset=(0.0, 0.0)):
    def transform(point):
        x, y = point
        return (
            offset[0] + scale * (x * cos(angle) - y * sin(angle)),
            offset[1] + scale * (x * sin(angle) + y * cos(angle)),
        )

    outer = list(map(transform, [(-3, -3), (3, -3), (3, 3), (-3, 3)]))
    hole = list(map(transform, [(-1, -1), (-1, 1), (1, 1), (1, -1)]))
    return [*outer, outer[0], *hole, hole[0], outer[0]]


def observe(pad, boundary, tolerance):
    perimeter = _pad_boundary_polygon(pad)
    bounds = (
        min(x for x, _ in perimeter), min(y for _, y in perimeter),
        max(x for x, _ in perimeter), max(y for _, y in perimeter),
    )
    # Production intentionally omits its old cached edge list for this type.
    return _observes_contact(pad, perimeter, bounds, boundary, (), tolerance)


class IndexedContactObservationTests(unittest.TestCase):
    def test_crossing_only_contact_uses_original_edges_without_cached_edges(self):
        boundary = prepare_source_filled_boundary(annulus())
        linear = FullScanBoundary(boundary.points, boundary.edges)
        # Center is in the hole, all pad corners are outside the outer ring,
        # and all source vertices are outside this narrow pad. Contact requires
        # the segment-intersection path rather than any point witness.
        pad = {"shape": "rect", "at": [0.0, 0.0], "size": [10.0, 0.2]}
        self.assertTrue(observe(pad, linear, 1e-6))
        self.assertTrue(observe(pad, boundary, 1e-6))
        self.assertEqual(
            boundary.query_edges((-inf, -inf, inf, inf)), boundary.edges,
        )

    def test_seeded_indexed_contact_matches_full_scan_candidates(self):
        generator = random.Random(131091)
        cases = (
            (1.0, 0.0, (0.0, 0.0)),
            (0.01, -1.5505626236354044, (100.0, -200.0)),
            (128.0, 0.371, (1e12, -1e12)),
        )
        for scale, angle, offset in cases:
            path = annulus(scale, angle, offset)
            for source in (path, list(reversed(path))):
                boundary = prepare_source_filled_boundary(source)
                linear = FullScanBoundary(boundary.points, boundary.edges)
                for index in range(60):
                    pad = {
                        "shape": generator.choice(("rect", "circle", "oval")),
                        "at": [offset[axis] + scale * generator.uniform(-4, 4)
                               for axis in (0, 1)],
                        "size": [scale * generator.uniform(0.02, 4)
                                 for _ in range(2)],
                        "rotation": generator.uniform(-180, 180),
                    }
                    tolerance = generator.choice((0.0, 1e-6, nextafter(1e-6, inf)))
                    with self.subTest(scale=scale, angle=angle, case=index):
                        self.assertEqual(
                            observe(pad, boundary, tolerance),
                            observe(pad, linear, tolerance),
                        )

    def test_representable_neighbors_of_contact_threshold_match_full_scan(self):
        boundary = prepare_source_filled_boundary(annulus())
        linear = FullScanBoundary(boundary.points, boundary.edges)
        for tolerance in (0.0, nextafter(0.0, inf), 1e-6):
            threshold = 3.5 + tolerance
            for x in (nextafter(threshold, -inf), threshold,
                      nextafter(threshold, inf)):
                pad = {"shape": "rect", "at": [x, 0.0], "size": [1.0, 0.2]}
                self.assertEqual(
                    observe(pad, boundary, tolerance),
                    observe(pad, linear, tolerance),
                )


if __name__ == "__main__":
    unittest.main()
