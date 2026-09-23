from __future__ import annotations

import unittest
import random
from collections import Counter, defaultdict

from python import spike_peec_native as native


def point(x: float, y: float):
    item = native.PlanarPoint2()
    item.x, item.y = x, y
    return item


def qpoint(x: int, y: int):
    item = native.QuantizedPlanarPoint2()
    item.x, item.y = x, y
    return item


def audit_constrained_mesh(region, mesh) -> None:
    vertices = list(mesh.vertices)
    index = {(item.x, item.y): offset for offset, item in enumerate(vertices)}
    rings = [region.outer, *region.cutouts]
    boundary_count = sum(len(ring.points) for ring in rings)
    assert len(index) == len(vertices) == boundary_count
    assert set(index) == {(item.x, item.y) for ring in rings for item in ring.points}
    normalized = lambda a, b: (a, b) if a < b else (b, a)
    constraints = {
        normalized(index[(ring.points[offset].x, ring.points[offset].y)],
                   index[(ring.points[(offset + 1) % len(ring.points)].x,
                          ring.points[(offset + 1) % len(ring.points)].y)])
        for ring in rings for offset in range(len(ring.points))
    }
    incidence, edge_faces, area = Counter(), defaultdict(list), 0
    for item in mesh.triangles:
        assert len({item.a, item.b, item.c}) == 3
        a, b, c = vertices[item.a], vertices[item.b], vertices[item.c]
        twice_area = (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)
        assert twice_area > 0
        area += twice_area
        for first, second in ((item.a, item.b), (item.b, item.c), (item.c, item.a)):
            item_edge = normalized(first, second)
            incidence[item_edge] += 1
            edge_faces[item_edge].append((item.a, item.b, item.c))
    assert all(incidence[item] == 1 for item in constraints)
    assert all(count == (1 if item in constraints else 2)
               for item, count in incidence.items())
    vertex_count, edge_count, triangle_count = len(vertices), len(incidence), len(mesh.triangles)
    holes = len(region.cutouts)
    assert triangle_count == 2 * vertex_count - boundary_count + 2 * holes - 2
    assert edge_count == vertex_count + triangle_count + holes - 1
    assert vertex_count - edge_count + triangle_count == 1 - holes
    source_area = sum(native.exact_quantized_planar_twice_area(ring.points) for ring in rings)
    assert area == source_area == mesh.twice_area_grid
    for item_edge, faces in edge_faces.items():
        if item_edge in constraints or len(faces) != 2:
            continue
        opposite = [next(vertex for vertex in face if vertex not in item_edge) for face in faces]
        u, v = item_edge
        first, second = opposite
        crosses = (native.exact_quantized_planar_orientation(
            vertices[first], vertices[second], vertices[u]) !=
            native.exact_quantized_planar_orientation(
                vertices[first], vertices[second], vertices[v]) and
            native.exact_quantized_planar_orientation(
                vertices[u], vertices[v], vertices[first]) !=
            native.exact_quantized_planar_orientation(
                vertices[u], vertices[v], vertices[second]))
        if crosses:
            incircle = native.exact_quantized_planar_incircle(
                vertices[u], vertices[v], vertices[first], vertices[second])
            assert incircle <= 0
            assert incircle != 0 or item_edge <= normalized(first, second)


class NativePlanarTopologyTests(unittest.TestCase):
    def test_exact_grid_orientation_and_incircle_are_native_and_deterministic(self) -> None:
        a, b, c = qpoint(0, 0), qpoint(10, 0), qpoint(0, 10)
        self.assertEqual(native.exact_quantized_planar_orientation(a, b, c), 1)
        self.assertEqual(native.exact_quantized_planar_incircle(a, b, c, qpoint(5, 5)), 1)
        self.assertEqual(native.exact_quantized_planar_incircle(a, b, c, qpoint(10, 10)), 0)
        self.assertEqual(native.exact_quantized_planar_incircle(a, b, c, qpoint(11, 11)), -1)
        large = [qpoint(-1_000_000_000, -1_000_000_000),
                 qpoint(1_000_000_000, -1_000_000_000),
                 qpoint(1_000_000_000, 1_000_000_000), qpoint(0, 0)]
        self.assertEqual(native.exact_quantized_planar_incircle(*large), 1)

    def test_native_incircle_matches_independent_python_integer_oracle(self) -> None:
        generator = random.Random(20260828)
        checked = 0
        while checked < 250:
            values = [(generator.randint(-1_000_000_000, 1_000_000_000),
                       generator.randint(-1_000_000_000, 1_000_000_000)) for _ in range(4)]
            (ax0, ay0), (bx0, by0), (cx0, cy0), (dx0, dy0) = values
            orientation = (bx0 - ax0) * (cy0 - ay0) - (by0 - ay0) * (cx0 - ax0)
            if orientation == 0:
                continue
            ax, ay, bx, by, cx, cy = (ax0 - dx0, ay0 - dy0, bx0 - dx0,
                                      by0 - dy0, cx0 - dx0, cy0 - dy0)
            determinant = ((ax * ax + ay * ay) * (bx * cy - by * cx)
                           + (bx * bx + by * by) * (cx * ay - cy * ax)
                           + (cx * cx + cy * cy) * (ax * by - ay * bx))
            expected = (1 if determinant > 0 else -1 if determinant < 0 else 0) \
                * (1 if orientation > 0 else -1)
            actual = native.exact_quantized_planar_incircle(*(qpoint(x, y) for x, y in values))
            self.assertEqual(actual, expected)
            checked += 1

    def test_scaled_orientation_and_area_match_python_integer_oracles(self) -> None:
        generator = random.Random(20260829)
        for _ in range(250):
            a = (generator.randint(-1_000_000_000, 1_000_000_000),
                 generator.randint(-1_000_000_000, 1_000_000_000))
            b = (generator.randint(-1_000_000_000, 1_000_000_000),
                 generator.randint(-1_000_000_000, 1_000_000_000))
            denominator = generator.randint(1, 16)
            numerator = (generator.randint(-denominator * 1_000_000_000,
                                            denominator * 1_000_000_000),
                         generator.randint(-denominator * 1_000_000_000,
                                            denominator * 1_000_000_000))
            determinant = ((b[0] - a[0]) * (numerator[1] - a[1] * denominator)
                           - (b[1] - a[1]) * (numerator[0] - a[0] * denominator))
            expected = 1 if determinant > 0 else -1 if determinant < 0 else 0
            self.assertEqual(native.exact_quantized_planar_orientation_scaled(
                qpoint(*a), qpoint(*b), *numerator, denominator
            ), expected)

        ring = [qpoint(-1_000_000_000, -1_000_000_000),
                qpoint(1_000_000_000, -1_000_000_000),
                qpoint(1_000_000_000, 1_000_000_000),
                qpoint(-1_000_000_000, 1_000_000_000)]
        self.assertEqual(native.exact_quantized_planar_twice_area(ring), 8_000_000_000_000_000_000)
        self.assertEqual(native.exact_quantized_planar_twice_area(list(reversed(ring))),
                         -8_000_000_000_000_000_000)

    def test_concave_ring_is_canonicalized_without_convexification(self) -> None:
        ring = native.canonicalize_simple_planar_ring([
            point(4, 0), point(4, 4), point(2, 2), point(0, 4), point(0, 0)
        ])
        self.assertTrue(ring.simple)
        self.assertAlmostEqual(ring.signed_area, 12.0)
        self.assertEqual((ring.points[0].x, ring.points[0].y), (0.0, 0.0))
        self.assertEqual(len(ring.points), 5)

    def test_self_intersection_nonfinite_and_unresolved_orientation_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            native.canonicalize_simple_planar_ring([
                point(0, 0), point(2, 2), point(0, 2), point(2, 0)
            ])
        with self.assertRaises(ValueError):
            native.canonicalize_simple_planar_ring([
                point(0, 0), point(float("nan"), 1), point(1, 0)
            ])
        self.assertEqual(native.certified_planar_orientation(
            point(0, 0), point(1, 1), point(2, 2)), 0)

    def test_quantized_region_canonicalizes_concavity_and_cutouts_exactly(self) -> None:
        region = native.canonicalize_planar_region(
            [point(0, 0), point(8, 0), point(8, 8), point(4, 5), point(0, 8)],
            [[point(1, 1), point(1, 2), point(2, 2), point(2, 1)],
             [point(5, 1), point(5, 2), point(6, 2), point(6, 1)]],
        )
        self.assertTrue(region.topology_valid)
        self.assertAlmostEqual(region.copper_area_mm2, 50.0)
        self.assertEqual(len(region.cutouts), 2)
        self.assertTrue(all(item.input_reversed is False for item in region.cutouts))

    def test_simple_concave_and_collinear_rings_triangulate_with_exact_audits(self) -> None:
        cases = [
            ([point(0, 0), point(6, 0), point(6, 2), point(2, 2), point(2, 6), point(0, 6)], 40),
            ([point(0, 0), point(4, 0), point(8, 0), point(8, 6), point(0, 6)], 96),
        ]
        for source, area2 in cases:
            with self.subTest(area2=area2):
                region = native.canonicalize_planar_region(source, [])
                first = native.triangulate_simple_planar_ring(region.outer)
                second = native.triangulate_simple_planar_ring(region.outer)
                triangles = [(item.a, item.b, item.c) for item in first.triangles]
                self.assertEqual(triangles, [(item.a, item.b, item.c) for item in second.triangles])
                self.assertEqual(len(triangles), len(source) - 2)
                self.assertEqual(first.twice_area_grid, int(area2 / (0.000001 ** 2)))
                self.assertTrue(first.boundary_constraints_preserved)
                self.assertTrue(first.exact_area_preserved)

        with self.assertRaises(ValueError):
            native.triangulate_simple_planar_ring(
                native.canonicalize_planar_region(cases[0][0], []).outer, maximum_points=5
            )
        with self.assertRaises(RuntimeError):
            native.triangulate_simple_planar_ring(
                native.canonicalize_planar_region(cases[0][0], []).outer, maximum_work_steps=1
            )

        baseline = native.triangulate_simple_planar_ring(
            native.canonicalize_planar_region(cases[0][0], []).outer
        )
        expected = [(item.a, item.b, item.c) for item in baseline.triangles]
        raw = cases[0][0]
        for variant in (raw[2:] + raw[:2], list(reversed(raw))):
            candidate = native.triangulate_simple_planar_ring(
                native.canonicalize_planar_region(variant, []).outer
            )
            self.assertEqual([(item.a, item.b, item.c) for item in candidate.triangles], expected)

    def test_quantized_region_rejects_touching_crossing_nested_and_off_grid_input(self) -> None:
        outer = [point(0, 0), point(6, 0), point(6, 6), point(0, 6)]
        bad_cutouts = [
            [[point(5, 5), point(5, 7), point(7, 7), point(7, 5)]],
            [[point(1, 1), point(1, 4), point(4, 4), point(4, 1)],
             [point(3, 3), point(3, 5), point(5, 5), point(5, 3)]],
            [[point(1, 1), point(1, 5), point(5, 5), point(5, 1)],
             [point(2, 2), point(2, 3), point(3, 3), point(3, 2)]],
        ]
        for cutouts in bad_cutouts:
            with self.subTest(cutouts=cutouts), self.assertRaises(ValueError):
                native.canonicalize_planar_region(outer, cutouts)
        with self.assertRaises(ValueError):
            native.canonicalize_planar_region(
                [point(0.0000004, 0), point(2, 0), point(0, 2)], [])

    def test_multi_hole_constrained_triangulation_has_exact_independent_audits(self) -> None:
        fixtures = [
            (native.canonicalize_planar_region(
                [point(0, 0), point(10, 0), point(10, 10), point(0, 10)],
                [[point(3, 3), point(3, 7), point(7, 7), point(7, 3)]],
            ), 8, 168_000_000_000_000),
            (native.canonicalize_planar_region(
                [point(0, 0), point(20, 0), point(20, 10), point(0, 10)],
                [[point(2, 1), point(9.999, 1), point(9.999, 9), point(2, 9)],
                 [point(10.001, 1), point(18, 1), point(18, 9), point(10.001, 9)]],
            ), 14, 144_032_000_000_000),
            (native.canonicalize_planar_region(
                [point(0, 0), point(8, 0), point(8, 8), point(4, 5), point(0, 8)],
                [[point(1, 1), point(1, 2), point(2, 2), point(2, 1)],
                 [point(5, 1), point(5, 2), point(6, 2), point(6, 1)]],
            ), 15, 100_000_000_000_000),
            (native.canonicalize_planar_region(
                [point(0, 0), point(4, 0), point(8, 0), point(8, 6), point(0, 6)], []
            ), 3, 96_000_000_000_000),
        ]
        for region, triangle_count, area in fixtures:
            with self.subTest(holes=len(region.cutouts)):
                mesh = native.triangulate_constrained_planar_region(region)
                audit_constrained_mesh(region, mesh)
                self.assertEqual(len(mesh.triangles), triangle_count)
                self.assertEqual(mesh.twice_area_grid, area)
                self.assertTrue(mesh.boundary_constraints_preserved)
                self.assertTrue(mesh.exact_area_preserved)
                self.assertTrue(mesh.domain_classified)
                self.assertTrue(mesh.locally_delaunay)
                repeat = native.triangulate_constrained_planar_region(region)
                self.assertEqual([(t.a, t.b, t.c) for t in mesh.triangles],
                                 [(t.a, t.b, t.c) for t in repeat.triangles])
                self.assertEqual(mesh.work_steps, repeat.work_steps)

        region = fixtures[0][0]
        with self.assertRaises(ValueError):
            native.triangulate_constrained_planar_region(region, maximum_vertices=7)
        with self.assertRaises(ValueError):
            native.triangulate_constrained_planar_region(region, maximum_triangles=7)
        baseline = native.triangulate_constrained_planar_region(region)
        with self.assertRaises(RuntimeError):
            native.triangulate_constrained_planar_region(
                region, maximum_work_steps=baseline.work_steps - 1)
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            native.triangulate_constrained_planar_region(
                region, cancel_check=lambda: True)

        raw_outer = [point(0, 0), point(20, 0), point(20, 10), point(0, 10)]
        raw_holes = [
            [point(2, 1), point(9.999, 1), point(9.999, 9), point(2, 9)],
            [point(10.001, 1), point(18, 1), point(18, 9), point(10.001, 9)],
        ]
        expected_mesh = native.triangulate_constrained_planar_region(fixtures[1][0])
        expected = [(item.a, item.b, item.c) for item in expected_mesh.triangles]
        variants = [
            (raw_outer[2:] + raw_outer[:2], [raw_holes[1], raw_holes[0]]),
            (list(reversed(raw_outer)), [list(reversed(raw_holes[0])),
                                        list(reversed(raw_holes[1]))]),
        ]
        for outer, holes in variants:
            candidate = native.triangulate_constrained_planar_region(
                native.canonicalize_planar_region(outer, holes))
            self.assertEqual([(item.a, item.b, item.c) for item in candidate.triangles], expected)


if __name__ == "__main__":
    unittest.main()
