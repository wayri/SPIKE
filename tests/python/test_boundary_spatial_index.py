# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
from __future__ import annotations

from math import cos, inf, nextafter, sin
import random
import unittest
from unittest.mock import patch

from python.spike_core.boundary_spatial_index import (
    BoundarySpatialIndex,
    BoundarySpatialIndexError,
    MAX_INDEX_EDGES,
    canonical_edge,
    conservative_edge_bounds,
    tolerance_query_bounds,
)
from python.spike_core.source_filled_boundary import (
    _distance_to_edge,
    prepare_source_filled_boundary,
)


def bridged_annulus(scale=1.0, offset=(0.0, 0.0), angle=0.0):
    dx, dy = offset

    def transform(point):
        x, y = point[0] * scale, point[1] * scale
        return (
            dx + x * cos(angle) - y * sin(angle),
            dy + x * sin(angle) + y * cos(angle),
        )

    outer = [transform(point) for point in ((-3, -3), (3, -3), (3, 3), (-3, 3))]
    hole = [transform(point) for point in ((-1, -1), (-1, 1), (1, 1), (1, -1))]
    return [*outer, outer[0], hole[0], *hole[1:], hole[0], outer[0]]


def reference_contains(boundary, point, tolerance):
    x, y = point
    inside = False
    canonical_edges = tuple(canonical_edge(edge) for edge in boundary.edges)
    for start, end in canonical_edges:
        if (start[1] > y) == (end[1] > y):
            continue
        crossing_x = start[0] + (y - start[1]) * (
            end[0] - start[0]
        ) / (end[1] - start[1])
        if x < crossing_x:
            inside = not inside
    if inside:
        return True
    return any(
        _distance_to_edge(point, edge) <= tolerance
        for edge in canonical_edges
    )


class BoundarySpatialIndexTests(unittest.TestCase):
    def test_seeded_indexed_contains_exactly_matches_canonical_full_scan(self):
        generator = random.Random(130013)
        domains = [
            prepare_source_filled_boundary(bridged_annulus(angle=-1.5505626236354044)),
            prepare_source_filled_boundary(
                bridged_annulus(scale=1e290, offset=(1e300, -1e300), angle=0.31)
            ),
            prepare_source_filled_boundary(
                bridged_annulus(scale=1e-300, angle=-0.73)
            ),
            prepare_source_filled_boundary(
                bridged_annulus(scale=4.0, offset=(1e16, -1e16), angle=0.19)
            ),
        ]
        fixed = [
            ((-1.1390573990378208, -3.0236647039143074), 0.0),
            ((0.0, 0.0), nextafter(0.0, inf)),
            ((1e300, -1e300), nextafter(1e285, inf)),
            ((0.0, 3e-300), nextafter(1e-310, inf)),
        ]
        for domain in domains:
            for point, tolerance in fixed:
                self.assertEqual(
                    domain.contains(point, tolerance),
                    reference_contains(domain, point, tolerance),
                )
            xs = [point[0] for point in domain.points]
            ys = [point[1] for point in domain.points]
            for _ in range(250):
                point = (
                    generator.uniform(min(xs), max(xs)),
                    generator.uniform(min(ys), max(ys)),
                )
                tolerance = generator.choice((
                    0.0,
                    nextafter(0.0, inf),
                    nextafter(abs(max(xs) - min(xs)) * 1e-12, inf),
                ))
                self.assertEqual(
                    domain.contains(point, tolerance),
                    reference_contains(domain, point, tolerance),
                )

    def test_edge_ray_and_point_queries_are_closed_supersets(self):
        domain = prepare_source_filled_boundary(
            bridged_annulus(angle=-0.3246830216258543)
        )
        self.assertEqual(
            domain.query_edges((-inf, -inf, inf, inf)), domain.edges,
        )
        generator = random.Random(99173)
        for _ in range(300):
            point = (generator.uniform(-4, 4), generator.uniform(-4, 4))
            tolerance = generator.choice((0.0, 1e-12, 0.1, nextafter(0.5, -inf)))
            directed_candidates = domain.query_edges(
                tolerance_query_bounds(point, tolerance)
            )
            self.assertTrue(all(edge in domain.edges for edge in directed_candidates))
            candidates = {canonical_edge(edge) for edge in directed_candidates}
            required = {
                edge for edge in domain._canonical_edges
                if _distance_to_edge(point, edge) <= tolerance
            }
            self.assertLessEqual(required, candidates)
            ray_candidates = set(domain._spatial_index.ray_edges(point[1]))
            straddling = {
                edge for edge in domain._canonical_edges
                if min(edge[0][1], edge[1][1]) <= point[1]
                <= max(edge[0][1], edge[1][1])
            }
            self.assertLessEqual(straddling, ray_candidates)

            bounds = (
                point[0] - 0.25, point[1] - 0.25,
                point[0] + 0.25, point[1] + 0.25,
            )
            expected_points = tuple(
                source_point for source_point in domain.points
                if bounds[0] <= source_point[0] <= bounds[2]
                and bounds[1] <= source_point[1] <= bounds[3]
            )
            self.assertEqual(domain.query_points(bounds), expected_points)

    def test_nearest_bounds_cover_rounded_segment_evaluation(self):
        edges = (
            ((1e16, 0.0), (1.0, 1e-300)),
            ((-1e308, 1.0), (1e308, -1.0)),
            ((0.0, -1e-300), (nextafter(0.0, inf), 1e-300)),
        )
        for edge in edges:
            bounds = conservative_edge_bounds(edge)
            start, end = edge if edge[0] <= edge[1] else (edge[1], edge[0])
            dx, dy = end[0] - start[0], end[1] - start[1]
            if dx in (-inf, inf) or dy in (-inf, inf):
                self.assertIn(inf, tuple(abs(value) for value in bounds))
                continue
            for ratio in (0.0, nextafter(0.0, inf), 0.5, nextafter(1.0, 0.0), 1.0):
                point = (start[0] + ratio * dx, start[1] + ratio * dy)
                self.assertLessEqual(bounds[0], point[0])
                self.assertLessEqual(point[0], bounds[2])
                self.assertLessEqual(bounds[1], point[1])
                self.assertLessEqual(point[1], bounds[3])

    def test_index_budget_and_invalid_queries_fail_closed(self):
        edge = ((0.0, 0.0), (1.0, 1.0))
        with (
            patch(
                "python.spike_core.boundary_spatial_index.MAX_INDEX_EDGES", 1
            ),
            self.assertRaises(BoundarySpatialIndexError),
        ):
            BoundarySpatialIndex((edge, edge), ())
        with self.assertRaises(BoundarySpatialIndexError):
            BoundarySpatialIndex((edge,), ()).query_edges((0.0, 0.0, -1.0, 1.0))
        self.assertEqual(MAX_INDEX_EDGES, 131_072)


if __name__ == "__main__":
    unittest.main()
