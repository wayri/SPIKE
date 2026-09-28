# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Analytical and admission tests for integrated local track mesh controls."""
import copy
import math
import unittest

from python.spike_core.local_mesh_controls import LocalTrackControls
from python.spike_core.contracts import DesignIR, AnalysisSpec
from python.spike_core.hybrid_mesh import build_hybrid_mesh


TRACKS = [{"id": "t1", "net_name": "PWR"}, {"id": "t2", "net_name": "GND"}]


def request(refinements=None, splits=None):
    return {"contract": "spike/local-track-mesh-controls/v1",
            "refinements": refinements or [], "splits": splits or []}


def rule(a=0.2, b=0.8, size=0.3, track="t1"):
    return {"track_id": track, "from_fraction": a, "to_fraction": b, "target_size_mm": size}


def control(raw, selected=(), tolerance=0.001, tracks=TRACKS):
    return LocalTrackControls(raw, tracks, selected, tolerance)


class LocalMeshControlsTests(unittest.TestCase):
    def test_real_hybrid_builder_preserves_length_resistance_and_inputs(self):
        design = DesignIR(tracks=[{"id": "t1", "net_name": "PWR", "layer": "F.Cu",
            "start": [0, 0], "end": [10, 0], "width": .2}])
        spec = AnalysisSpec(net_names=["PWR"], mesh={"target_size_mm": 1., "feature_aware": False})
        baseline = build_hybrid_mesh(design, spec)
        spec.mesh["local_controls"] = request([rule(.2, .8, .2)],
            [{"track_id": "t1", "fractions": [.35]}])
        before = copy.deepcopy((design, spec))
        refined = build_hybrid_mesh(design, spec)
        self.assertEqual(before, (design, spec))
        self.assertFalse(refined.truncated)
        self.assertGreater(len(refined.branches), len(baseline.branches))
        self.assertTrue(any(abs(node.x_mm - 3.5) < 1e-12 for node in refined.nodes))
        self.assertAlmostEqual(math.fsum(b.length_mm for b in refined.branches), 10, places=12)
        self.assertAlmostEqual(math.fsum(b.resistance_ohm for b in refined.branches),
                               math.fsum(b.resistance_ohm for b in baseline.branches), places=12)
        for branch in refined.branches:
            midpoint = (branch.start_mm[0] + branch.end_mm[0]) / 2
            if 2 < midpoint < 8:
                self.assertLessEqual(branch.length_mm, .2 + 1e-12)

    def test_real_builder_unknown_source_rejects(self):
        design = DesignIR(tracks=[{"id": "t1", "net_name": "PWR", "layer": "F.Cu",
            "start": [0, 0], "end": [10, 0], "width": .2}])
        spec = AnalysisSpec(net_names=["PWR"], mesh={"local_controls": request([rule(track="missing")])})
        with self.assertRaises(ValueError):
            build_hybrid_mesh(design, spec)

    def test_absent_and_empty_preserve_legacy(self):
        for raw in (None, request()):
            self.assertIsNone(control(raw).fractions("t1", (0, 0), (10, 0), 1, 100))

    def test_manual_exact_endpoints_sorted_deterministic(self):
        raw = request(splits=[{"track_id": "t1", "fractions": [0.71, 0.25]}])
        before = copy.deepcopy(raw)
        c = control(raw)
        expected = [0.25, 0.71, 1.0]
        self.assertEqual(c.fractions("t1", (0, 0), (10, 0), 20, 100), expected)
        self.assertEqual(c.fractions("t1", (0, 0), (10, 0), 20, 100), expected)
        self.assertEqual(raw, before)
        self.assertIsNone(c.fractions("t2", (0, 0), (10, 0), 1, 100))

    def test_overlaps_finest_wins_order_independent(self):
        rules = [rule(0.2, 0.8, 0.5), rule(0.4, 0.6, 0.1)]
        f = control(request(rules)).fractions("t1", (0, 0), (10, 0), 1, 200)
        self.assertEqual(f, control(request(list(reversed(rules)))).fractions("t1", (0, 0), (10, 0), 1, 200))
        for a, b in zip([0.0] + f, f):
            midpoint = (a + b) / 2
            limit = 0.1 if 0.4 < midpoint < 0.6 else 0.5 if 0.2 < midpoint < 0.8 else 1.0
            self.assertLessEqual((b-a)*10, limit + 1e-12)

    def test_refinement_never_coarsens(self):
        f = control(request([rule(0, 1, 100)])).fractions("t1", (0, 0), (10, 0), 0.5, 100)
        self.assertEqual(len(f), 20)

    def test_reversed_diagonal_length_resistance_invariant(self):
        c = control(request([rule()], [{"track_id": "t1", "fractions": [0.35]}]))
        for start, end in [((0, 0), (6, 8)), ((6, 8), (0, 0)), ((-2, 4), (-8, -4))]:
            f = c.fractions("t1", start, end, 1, 200)
            points = [start] + [(start[0]+(end[0]-start[0])*t, start[1]+(end[1]-start[1])*t) for t in f]
            lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
            self.assertEqual(points[-1], end)
            self.assertTrue(all(x > 0 for x in lengths))
            self.assertAlmostEqual(math.fsum(lengths), 10.0, places=12)
            rho, area_m2 = 1.68e-8, 0.2e-3*35e-6
            calculated = math.fsum(rho*x*1e-3/area_m2 for x in lengths)
            self.assertAlmostEqual(calculated, rho*0.01/area_m2, places=14)

    def test_malformed_numbers_reject(self):
        for value in (True, "0.2", None, float("nan"), float("inf"), 10**400):
            for key in ("from_fraction", "to_fraction", "target_size_mm"):
                row = rule()
                row[key] = value
                with self.subTest(key=key, value=str(value)[:30]), self.assertRaises(ValueError):
                    control(request([row]))
            with self.assertRaises(ValueError):
                control(request(splits=[{"track_id": "t1", "fractions": [value]}]))

    def test_invalid_selectors_reject(self):
        for name in ("missing", "t2", 123):
            with self.assertRaises(ValueError):
                control(request([rule(track=name)]), selected=["PWR"])
        with self.assertRaises(ValueError):
            control(request(), tracks=[TRACKS[0], TRACKS[0]])

    def test_unknown_fields_contract_and_shape_reject(self):
        for raw in ({}, [], {**request(), "extra": 1}, {**request(), "contract": "future"},
                    {**request(), "refinements": {}}, request([None])):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                control(raw)

    def test_bad_ranges_splits_and_duplicate_records_reject(self):
        for a, b, size in ((-0.1, 1, 1), (0, 1.1, 1), (0.5, 0.5, 1), (0.7, 0.2, 1), (0, 1, 0.002)):
            with self.assertRaises(ValueError):
                control(request([rule(a, b, size)]))
        for values in ([], [0], [1], [-0.1], [0.5, 0.5], [0.1]*257):
            with self.assertRaises(ValueError):
                control(request(splits=[{"track_id": "t1", "fractions": values}]))
        with self.assertRaises(ValueError):
            control(request(splits=[{"track_id": "t1", "fractions": [0.2]}]*2))

    def test_control_and_segment_budgets_reject(self):
        with self.assertRaises(ValueError):
            control(request([rule()]*257))
        c = control(request([rule(0, 1, 0.1)]))
        with self.assertRaises(ValueError):
            c.fractions("t1", (0, 0), (10, 0), 1, 99)
        c = control(request(splits=[{"track_id": "t1", "fractions": [0.5]}]))
        with self.assertRaises(ValueError):
            c.fractions("t1", (0, 0), (10, 0), 1, 9)

    def test_collapsing_boundaries_and_subdivisions_reject(self):
        for fractions in ([0.0001], [0.4, 0.4001]):
            c = control(request(splits=[{"track_id": "t1", "fractions": fractions}]))
            with self.assertRaises(ValueError):
                c.fractions("t1", (0, 0), (10, 0), 1, 100)
        c = control(request([rule(0, 1, 0.0021)]))
        with self.assertRaises(ValueError):
            c.fractions("t1", (0, 0), (0.003, 0), 1, 100)
        for endpoint in ((0, 0), (float("inf"), 0)):
            with self.assertRaises(ValueError):
                c.fractions("t1", (0, 0), endpoint, 1, 100)


if __name__ == "__main__":
    unittest.main()
