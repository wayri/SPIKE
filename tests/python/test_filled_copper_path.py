# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
from __future__ import annotations

from math import cos, fsum, inf, nextafter, sin
import unittest
from unittest.mock import patch

import python.spike_core.filled_copper_path as filled_path
from python.spike_core.filled_copper_path import (
    MAX_HOLES,
    MAX_SOURCE_VERTICES,
    FilledCopperPath,
    FilledPathBudgetError,
    FilledPathError,
    prepare_filled_path,
)


def area(polygon):
    return abs(fsum(
        start[0] * end[1] - end[0] * start[1]
        for start, end in zip(polygon, (*polygon[1:], polygon[0]))
    )) / 2


def clipped_area(polygon, bounds):
    result = list(polygon)
    for axis, boundary, keep_greater in (
        (0, bounds[0], True), (0, bounds[2], False),
        (1, bounds[1], True), (1, bounds[3], False),
    ):
        clipped = []
        for start, end in zip(result, (*result[1:], result[0])):
            start_inside = start[axis] >= boundary if keep_greater else start[axis] <= boundary
            end_inside = end[axis] >= boundary if keep_greater else end[axis] <= boundary
            if start_inside != end_inside:
                ratio = (boundary - start[axis]) / (end[axis] - start[axis])
                intersection = (
                    start[0] + ratio * (end[0] - start[0]),
                    start[1] + ratio * (end[1] - start[1]),
                )
                clipped.append(intersection)
            if end_inside:
                clipped.append(end)
        result = clipped
        if not result:
            return 0.0
    return area(result)


def annulus_path(offset=(0, 0)):
    dx, dy = offset
    return [
        (dx + x, dy + y)
        for x, y in (
            (0, 0), (4, 0), (4, 4), (0, 4), (0, 0),
            (1, 1), (1, 3), (3, 3), (3, 1), (1, 1), (0, 0),
        )
    ]


def several_holes(count):
    origin = (0.0, 0.0)
    path = [origin, (100.0, 0.0), (100.0, 100.0), (0.0, 100.0), origin]
    for index in range(count):
        x = 1.0 + (index % 25) * 3.0
        y = 1.0 + (index // 25) * 3.0
        hole = [(x, y), (x, y + 1), (x + 1, y + 1), (x + 1, y), (x, y)]
        path.extend([*hole, origin])
    return path


class FilledCopperPathTests(unittest.TestCase):
    def test_exact_bridge_cancellation_recovers_annulus(self):
        source = annulus_path()
        domain = prepare_filled_path(source)
        self.assertIsInstance(domain, FilledCopperPath)
        self.assertEqual(tuple(domain), tuple((float(x), float(y)) for x, y in source))
        self.assertEqual(len(domain.edges), 8)
        self.assertEqual(len(domain.holes), 1)
        self.assertGreater(area(domain.outer), 0)
        self.assertTrue(domain.contains((0.5, 2.0)))
        self.assertFalse(domain.contains((2.0, 2.0)))
        self.assertTrue(domain.contains((1.0, 2.0), 1e-9))
        self.assertNotIn(((0.0, 0.0), (1.0, 1.0)), domain.edges)
        self.assertNotIn(((1.0, 1.0), (0.0, 0.0)), domain.edges)

    def test_reversal_and_translation_preserve_area_and_occupancy(self):
        forward = prepare_filled_path(annulus_path((7, -3)))
        reverse = prepare_filled_path(list(reversed(annulus_path((7, -3)))))
        self.assertIsNotNone(forward)
        self.assertIsNotNone(reverse)
        self.assertAlmostEqual(
            sum(area(piece) for piece in forward.cell_fragments(7, -3, 11, 1)),
            12.0,
            places=12,
        )
        self.assertAlmostEqual(
            sum(area(piece) for piece in reverse.cell_fragments(7, -3, 11, 1)),
            12.0,
            places=12,
        )
        for point in ((7.5, -1), (9, -1), (11, 1)):
            self.assertEqual(forward.contains(point), reverse.contains(point))

    def test_bridge_is_not_a_tolerance_boundary(self):
        source = [
            (0, 0), (8, 8), (8, 2), (2, 2), (2, 8),
            (8, 8), (0, 0), (10, 0), (10, 10), (0, 10),
        ]
        domain = prepare_filled_path(source)
        self.assertFalse(domain.contains((4, 4), 1e-6))
        self.assertTrue(domain.contains((1, 1), 1e-6))
        self.assertAlmostEqual(
            sum(area(piece) for piece in domain.cell_fragments(0, 0, 10, 10)),
            64.0,
            places=12,
        )

    def test_cell_fragments_are_clockwise_convex_pieces_and_preserve_area(self):
        domain = prepare_filled_path(annulus_path())
        fragments = []
        for row in range(4):
            for column in range(4):
                pieces = domain.cell_fragments(column, row, column + 1, row + 1)
                if 1 <= column < 3 and 1 <= row < 3:
                    self.assertEqual(pieces, [])
                fragments.extend(pieces)
        self.assertAlmostEqual(sum(area(piece) for piece in fragments), 12.0, places=12)
        self.assertTrue(all(len(piece) in (3, 4) for piece in fragments))
        self.assertTrue(all(
            fsum(
                start[0] * end[1] - end[0] * start[1]
                for start, end in zip(piece, (*piece[1:], piece[0]))
            ) < 0
            for piece in fragments
        ))

    def test_multiple_holes_are_retained(self):
        domain = prepare_filled_path(several_holes(4))
        self.assertEqual(len(domain.holes), 4)
        self.assertTrue(domain.contains((90, 90)))
        for index in range(4):
            x = 1.5 + index * 3.0
            self.assertFalse(domain.contains((x, 1.5)))
        self.assertAlmostEqual(
            sum(area(piece) for piece in domain.cell_fragments(0, 0, 100, 100)),
            9996.0,
            places=9,
        )

    def test_disjoint_hole_bboxes_prune_nested_ring_ray_checks(self):
        original = filled_path._strictly_inside_integer
        with patch(
            "python.spike_core.filled_copper_path._strictly_inside_integer",
            wraps=original,
        ) as contains:
            domain = prepare_filled_path(several_holes(12))
        self.assertEqual(len(domain.holes), 12)
        self.assertEqual(contains.call_count, 12)

    def test_aggregate_topology_work_budget_bounds_cheap_sweep_visits(self):
        # These two rings share their x span but are disjoint in y.  The
        # bounded sweep must count its active-list filtering even though it
        # reaches no exact cross-ring intersection predicate.
        integer_rings = (
            ((0, 0), (10, 0), (10, 1), (0, 1)),
            ((0, 3), (10, 3), (10, 4), (0, 4)),
        )
        budget = filled_path._TopologyBudget()
        original = filled_path._intersects
        with (
            patch("python.spike_core.filled_copper_path.MAX_TOPOLOGY_WORK", 1),
            patch(
                "python.spike_core.filled_copper_path._intersects",
                wraps=original,
            ) as intersects,
            self.assertRaisesRegex(FilledPathBudgetError, "aggregate work"),
        ):
            filled_path._validate_cross_ring_intersections(integer_rings, budget)
        self.assertEqual(intersects.call_count, 0)

    def test_nested_holes_fail_closed(self):
        origin = (0, 0)
        outer = [origin, (10, 0), (10, 10), (0, 10), origin]
        large_hole = [(2, 2), (2, 8), (8, 8), (8, 2), (2, 2)]
        nested_hole = [(3, 3), (3, 4), (4, 4), (4, 3), (3, 3)]
        source = [*outer, *large_hole, origin, *nested_hole, origin]
        with self.assertRaisesRegex(FilledPathError, "nested holes"):
            prepare_filled_path(source)

    def test_no_retraced_edge_uses_ordinary_polygon_path(self):
        self.assertIsNone(prepare_filled_path([(0, 0), (1, 0), (0, 1)]))
        ordinary = [(float(index), float(index % 2)) for index in range(MAX_SOURCE_VERTICES + 1)]
        self.assertIsNone(prepare_filled_path(ordinary))

    def test_crossing_and_bad_incidence_fail_closed(self):
        crossing = [
            (0, 0), (4, 4), (0, 4), (4, 0), (0, 0),
            (1, 1), (1, 2), (2, 2), (2, 1), (1, 1), (0, 0),
        ]
        with self.assertRaises(FilledPathError):
            prepare_filled_path(crossing)
        branched = annulus_path() + [(0, 0), (2, 0), (0, 0)]
        with self.assertRaises(FilledPathError):
            prepare_filled_path(branched)

    def test_explicit_vertex_hole_and_fragment_budgets(self):
        oversized_retraced = annulus_path() + [
            (float(index), 20.0 + float(index % 2))
            for index in range(MAX_SOURCE_VERTICES)
        ]
        with self.assertRaises(FilledPathBudgetError):
            prepare_filled_path(oversized_retraced)
        with self.assertRaises(FilledPathBudgetError):
            prepare_filled_path(several_holes(MAX_HOLES + 1))
        domain = prepare_filled_path(annulus_path())
        with (
            patch("python.spike_core.filled_copper_path.MAX_CELL_FRAGMENT_WORK", 1),
            self.assertRaises(FilledPathBudgetError),
        ):
            domain.cell_fragments(0, 0, 4, 4)

    def test_unrepresentable_tiny_slab_fails_closed(self):
        source = [
            (1, 0), (4, 2), (4, 4), (6, 4), (6, 2),
            (4, 2), (1, 0), (10, 0), (10, 10), (1, 10),
        ]
        domain = prepare_filled_path(source)
        with self.assertRaisesRegex(FilledPathError, "no representable interior"):
            domain.cell_fragments(1.0, 0.0, nextafter(1.0, inf), 1.0)

    def test_slanted_hole_partial_cell_matches_independent_rect_clip(self):
        angle = -0.3246830216258543
        base_hole = [(-1, -1), (-1, 1), (1, 1), (1, -1)]
        hole = [
            (x * cos(angle) - y * sin(angle), x * sin(angle) + y * cos(angle))
            for x, y in base_hole
        ]
        outer = [(-3, -3), (3, -3), (3, 3), (-3, 3)]
        source = [*outer, outer[0], hole[0], *hole[1:], hole[0], outer[0]]
        domain = prepare_filled_path(source)
        bounds = (-3.70349571689019, -2.428103617447772,
                  2.947058323119836, 1.139551104404882)
        fragments = domain.cell_fragments(*bounds)
        expected = clipped_area(outer, bounds) - clipped_area(hole, bounds)
        self.assertAlmostEqual(sum(area(piece) for piece in fragments), expected, places=12)
        self.assertTrue(all(len(piece) in (3, 4) for piece in fragments))


if __name__ == "__main__":
    unittest.main()
