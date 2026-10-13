# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
from __future__ import annotations

from math import cos, sin
import unittest
from unittest.mock import patch

from python.spike_core.filled_copper_path import (
    FilledPathError,
    prepare_filled_path,
)
from python.spike_core.source_filled_boundary import (
    SourceFilledBoundary,
    SourceFilledBoundaryBudgetError,
    SourceFilledBoundaryCancelled,
    SourceFilledBoundaryError,
    prepare_source_filled_boundary,
)


def bridge_through_hole_path():
    return [
        (0, 0), (8, 8), (8, 2), (2, 2), (2, 8),
        (8, 8), (0, 0), (10, 0), (10, 10), (0, 10),
    ]


class SourceFilledBoundaryTests(unittest.TestCase):
    def test_retraced_bridge_is_removed_but_source_coordinates_are_retained(self):
        source = bridge_through_hole_path()
        boundary = prepare_source_filled_boundary(source)
        self.assertIsInstance(boundary, SourceFilledBoundary)
        self.assertEqual(
            tuple(boundary), tuple((float(x), float(y)) for x, y in source)
        )
        self.assertNotIn(((0.0, 0.0), (8.0, 8.0)), boundary.edges)
        self.assertNotIn(((8.0, 8.0), (0.0, 0.0)), boundary.edges)
        self.assertFalse(hasattr(boundary, "cell_fragments"))

    def test_contains_uses_filled_parity_and_physical_boundary_only(self):
        boundary = prepare_source_filled_boundary(bridge_through_hole_path())
        self.assertFalse(boundary.contains((4, 4), 1e-6))
        self.assertTrue(boundary.contains((1, 1), 1e-6))
        self.assertTrue(boundary.contains((0, 5), 0.0))
        self.assertFalse(boundary.contains((-1e-5, 5), 1e-6))

    def test_boundary_containment_is_invariant_to_path_reversal(self):
        angle = -1.5505626236354044
        rotate = lambda point: (
            point[0] * cos(angle) - point[1] * sin(angle),
            point[0] * sin(angle) + point[1] * cos(angle),
        )
        outer = [rotate(point) for point in ((-3, -3), (3, -3), (3, 3), (-3, 3))]
        hole = [rotate(point) for point in ((-1, -1), (-1, 1), (1, 1), (1, -1))]
        source = [*outer, outer[0], hole[0], *hole[1:], hole[0], outer[0]]
        forward = prepare_source_filled_boundary(source)
        reverse = prepare_source_filled_boundary(list(reversed(source)))
        query = (-1.1390573990378208, -3.0236647039143074)
        self.assertEqual(forward.contains(query), reverse.contains(query))

    def test_no_retrace_defers_to_established_simple_polygon_path(self):
        self.assertIsNone(
            prepare_source_filled_boundary([(0, 0), (1, 0), (0, 1)])
        )

    def test_boundary_view_does_not_impose_strict_domain_topology(self):
        crossing = [
            (0, 0), (4, 4), (0, 4), (4, 0), (0, 0),
            (1, 1), (1, 2), (2, 2), (2, 1), (1, 1), (0, 0),
        ]
        self.assertIsNotNone(prepare_source_filled_boundary(crossing))
        with self.assertRaises(FilledPathError):
            prepare_filled_path(crossing)

        origin = (0, 0)
        nested = [
            origin, (10, 0), (10, 10), (0, 10), origin,
            (2, 2), (2, 8), (8, 8), (8, 2), (2, 2), origin,
            (3, 3), (3, 4), (4, 4), (4, 3), (3, 3), origin,
        ]
        self.assertIsNotNone(prepare_source_filled_boundary(nested))
        with self.assertRaisesRegex(FilledPathError, "nested holes"):
            prepare_filled_path(nested)

    def test_ambiguous_multiplicity_and_size_budget_fail_closed(self):
        ambiguous = bridge_through_hole_path() + [(0, 0), (8, 8), (0, 0)]
        with self.assertRaises(SourceFilledBoundaryError):
            prepare_source_filled_boundary(ambiguous)
        with (
            patch(
                "python.spike_core.source_filled_boundary.MAX_SOURCE_VERTICES", 8
            ),
            self.assertRaises(SourceFilledBoundaryBudgetError),
        ):
            prepare_source_filled_boundary(bridge_through_hole_path())

    def test_periodic_cancellation_returns_no_partial_boundary(self):
        calls = 0

        def cancel():
            nonlocal calls
            calls += 1
            return calls >= 2

        with self.assertRaises(SourceFilledBoundaryCancelled):
            prepare_source_filled_boundary(
                bridge_through_hole_path() * 1_025,
                cancel_check=cancel,
            )


if __name__ == "__main__":
    unittest.main()
