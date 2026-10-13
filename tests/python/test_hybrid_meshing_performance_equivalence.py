# SPDX-License-Identifier: Apache-2.0
"""Exact-equivalence checks for bounded hybrid-mesher optimizations."""

from __future__ import annotations

from dataclasses import asdict
from math import isfinite, ldexp, nextafter
import json
import random
import unittest
from unittest.mock import patch

from python.spike_core.contracts import AnalysisSpec, SpiDeR
from python.spike_core.hybrid_mesh import (
    COPPER_CONDUCTIVITY_S_M,
    _distance_to_segment,
    _edge_may_be_within_tolerance,
    _point_in_polygon,
    _segments,
    build_hybrid_mesh,
)


def _legacy_point_in_polygon(point, polygon, tolerance=0.0):
    """Pre-optimization predicate retained as an independent exact oracle."""

    inside = False
    x, y = point
    previous = polygon[-1]
    for current in polygon:
        if (current[1] > y) != (previous[1] > y):
            crossing = (previous[0] - current[0]) * (y - current[1]) / (
                (previous[1] - current[1]) or 1e-15
            ) + current[0]
            if x < crossing:
                inside = not inside
        previous = current
    if inside:
        return True

    return bool(
        tolerance
        and any(_distance_to_segment(point, a, b) <= tolerance for a, b in _segments(polygon))
    )


def _fixture() -> tuple[SpiDeR, AnalysisSpec]:
    concave = [
        [0.0, 0.0], [8.0, 0.0], [8.0, 3.0], [5.0, 3.0],
        [5.0, 1.0], [3.0, 1.0], [3.0, 3.0], [0.0, 3.0],
    ]
    design = SpiDeR(
        design_id="hybrid-performance-equivalence",
        name="nonconvex multilayer via and drilled pad",
        layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
        stackup=[
            {"name": "F.Cu", "type": "copper", "thickness": 0.035},
            {"name": "core", "type": "dielectric", "thickness": 1.53},
            {"name": "B.Cu", "type": "copper", "thickness": 0.035},
        ],
        tracks=[
            {"id": "left", "start": [-2.0, 0.5], "end": [0.0, 0.5],
             "width": 0.5, "layer": "F.Cu", "net_name": "VCC"},
            {"id": "right", "start": [8.0, 0.5], "end": [10.0, 0.5],
             "width": 0.5, "layer": "B.Cu", "net_name": "VCC"},
        ],
        zones=[
            {"id": "top-plane", "points": concave, "layer": "F.Cu", "net_name": "VCC"},
            {"id": "bottom-plane", "points": concave, "layer": "B.Cu", "net_name": "VCC"},
        ],
        vias=[{
            "id": "via", "at": [8.0, 0.5], "size": 0.7, "drill": 0.3,
            "plating_thickness_mm": 0.025, "layers": ["F.Cu", "B.Cu"],
            "net_name": "VCC",
        }],
        pads=[{
            "id": "drilled-pad", "at": [0.0, 0.5], "size": [1.4, 1.1],
            "drill": [0.45, 0.45], "shape": "oval", "drill_shape": "circle",
            "layers": ["F.Cu", "B.Cu"], "layer": "F.Cu", "net_name": "VCC",
        }],
    )
    spec = AnalysisSpec(
        mode="dc",
        net_names=["VCC"],
        sources=[{"position_mm": [-2.0, 0.5], "layer": "F.Cu", "net": "VCC"}],
        loads=[{"position_mm": [10.0, 0.5], "layer": "B.Cu", "net": "VCC"}],
        mesh={
            "target_size_mm": 0.5,
            "zone_cell_mm": 0.5,
            "max_zone_cells": 500,
            "max_conductors": 20_000,
        },
    )
    return design, spec


def _canonical(mesh) -> bytes:
    return json.dumps(
        asdict(mesh), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


class HybridMeshingPerformanceEquivalenceTests(unittest.TestCase):
    def test_seeded_extreme_scale_gate_never_rejects_legacy_match(self):
        generator = random.Random(0x5EEDC0DE)
        exponents = (-1070, -1022, -500, -50, 0, 50, 500, 999)
        checked = 0
        for index in range(1000):
            exponent = exponents[index % len(exponents)]
            scale = ldexp(1.0, exponent)
            start = (
                generator.uniform(-2.0, 2.0) * scale,
                generator.uniform(-2.0, 2.0) * scale,
            )
            delta_scale = ldexp(1.0, exponents[(index * 5 + 3) % len(exponents)])
            end = (
                start[0] + generator.uniform(-2.0, 2.0) * delta_scale,
                start[1] + generator.uniform(-2.0, 2.0) * delta_scale,
            )
            point = (
                start[0] + generator.uniform(-3.0, 3.0) * delta_scale,
                start[1] + generator.uniform(-3.0, 3.0) * delta_scale,
            )
            if not all(isfinite(value) for value in (*start, *end, *point)):
                continue
            distance = _distance_to_segment(point, start, end)
            if not isfinite(distance):
                continue
            tolerances = {
                distance,
                nextafter(distance, 0.0),
                nextafter(distance, float("inf")),
            }
            for tolerance in tolerances:
                if not _edge_may_be_within_tolerance(point, start, end, tolerance):
                    self.assertGreater(distance, tolerance)
                checked += 1
        self.assertGreaterEqual(checked, 2000)

        # Explicit non-finite rounded deltas must retain the legacy distance
        # call, while subnormal segments whose squared length underflows remain
        # governed by the same degenerate-segment path.
        self.assertTrue(_edge_may_be_within_tolerance(
            (0.0, 0.0), (-1e308, 0.0), (1e308, 0.0), 1e-4,
        ))
        tiny = (nextafter(0.0, 1.0), 0.0)
        tiny_distance = _distance_to_segment((1.0, 0.0), (0.0, 0.0), tiny)
        self.assertEqual(tiny_distance, 1.0)
        self.assertFalse(_edge_may_be_within_tolerance(
            (1.0, 0.0), (0.0, 0.0), tiny, nextafter(1.0, 0.0),
        ))

    def test_bounded_edge_rejection_is_boolean_equivalent_to_legacy_predicate(self):
        polygons = [
            [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)],
            [(0.0, 0.0), (5.0, 0.0), (5.0, 1.0), (2.0, 1.0),
             (2.0, 4.0), (0.0, 4.0)],
            [(1.0, 0.0), (0.1, 0.0), (1.0, 1.0)],
            [(10.0, 0.0), (1.0, 0.0), (10.0, 10.0)],
            [(1e16, 0.0), (1.0, 0.0), (1e16, 1e16)],
        ]
        points = [
            (x / 4.0, y / 4.0)
            for x in range(-8, 29)
            for y in range(-8, 25)
        ]
        points.extend([(0.0, 0.0), (4.0 + 1e-4, 1.5), (2.0, 1.0 + 1e-10)])
        points.extend([
            (nextafter(0.1 - 0.0001, float("-inf")), 0.0),
            (nextafter(1.0 - 0.0001, float("-inf")), 0.0),
            (nextafter(4.0 + 0.0001, float("inf")), 1.5),
            (0.0, -1e-5),
        ])
        for polygon in polygons:
            for tolerance in (0.0, 1e-9, 1e-4, 0.05):
                for point in points:
                    with self.subTest(polygon=len(polygon), tolerance=tolerance, point=point):
                        self.assertEqual(
                            _point_in_polygon(point, polygon, tolerance),
                            _legacy_point_in_polygon(point, polygon, tolerance),
                        )

    def test_complete_mesh_is_byte_exact_with_legacy_predicate(self):
        design, spec = _fixture()
        with patch("python.spike_core.hybrid_mesh._point_in_polygon", _legacy_point_in_polygon):
            reference = build_hybrid_mesh(design, spec)
        optimized = build_hybrid_mesh(design, spec)
        self.assertEqual(_canonical(optimized), _canonical(reference))
        self.assertEqual(optimized.geometry_counts, {"track": 2, "zone": 2, "via": 1, "pad": 1})
        self.assertFalse(optimized.truncated)
        self.assertTrue(any(cell["source_id"] == "drilled-pad" for cell in optimized.cells))
        self.assertTrue(any(branch.kind == "via" for branch in optimized.branches))
        self.assertEqual({node.layer for node in optimized.nodes}, {"F.Cu", "B.Cu"})
        self.assertEqual({node.net for node in optimized.nodes}, {"VCC"})

    def test_analytic_straight_trace_dc_resistance_is_conserved(self):
        length_mm, width_mm, thickness_mm = 20.0, 1.0, 0.035
        design = SpiDeR(
            name="analytical trace",
            layers=[{"name": "F.Cu"}],
            stackup=[{"name": "F.Cu", "type": "copper", "thickness": thickness_mm}],
            tracks=[{
                "id": "trace", "start": [0.0, 0.0], "end": [length_mm, 0.0],
                "width": width_mm, "layer": "F.Cu", "net_name": "VCC",
            }],
        )
        spec = AnalysisSpec(
            mode="dc", net_names=["VCC"],
            mesh={"target_size_mm": 0.4, "max_conductors": 10_000},
        )
        mesh = build_hybrid_mesh(design, spec)
        measured = sum(branch.resistance_ohm for branch in mesh.branches)
        expected = length_mm * 1e-3 / (
            COPPER_CONDUCTIVITY_S_M * width_mm * 1e-3 * thickness_mm * 1e-3
        )
        self.assertAlmostEqual(measured, expected, delta=expected * 1e-12)


if __name__ == "__main__":
    unittest.main()
