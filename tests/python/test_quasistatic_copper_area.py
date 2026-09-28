# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Independent geometric/parallel-plate oracles, not electrostatic validation."""

import unittest
from math import pi
from types import SimpleNamespace

import numpy as np

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.hybrid_mesh import build_hybrid_mesh
from python.spike_core.quasistatic_copper_area import (
    _partition_area, estimate_branch_capacitance,
)
from python.spike_core.quasistatic_capacitance import EPSILON_0_F_M, estimate_line_capacitance_per_m


def rectangle(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def zone(owner, points, net="SIG", layer="F.Cu"):
    return {"id": owner, "points": points, "layer": layer, "net_name": net}


def design(**kwargs):
    return DesignIR(layers=[{"name": "F.Cu"}, {"name": "B.Cu"}], stackup=[
        {"name": "F.Cu", "thickness": 0.035},
        {"name": "core", "thickness": 0.2, "epsilon_r": 4, "loss_tangent": 0.02},
        {"name": "B.Cu", "thickness": 0.035},
    ], **kwargs)


def branch(owner="z", kind="zone", length=1, net="SIG", layer="F.Cu"):
    return SimpleNamespace(source_id=owner, kind=kind, length_mm=length,
                           net=net, layer=layer)


class CopperAreaCapacitanceTests(unittest.TestCase):
    def test_rectangle_union_overlap_and_duplicate_oracle(self):
        polygons = [rectangle(0, 0, 2, 2), rectangle(1, 0, 3, 2), rectangle(0, 0, 2, 2)]
        areas = _partition_area(polygons, 3, [])
        self.assertEqual(areas, {(0, ""): 4.0, (1, ""): 2.0})

    def test_crossing_triangles_have_exact_three_square_mm_union(self):
        # Each area is 2; their overlap is a height-1, base-2 triangle (area 1).
        polygons = [[(0, 0), (2, 0), (0, 2)], [(0, 0), (2, 0), (2, 2)]]
        self.assertAlmostEqual(sum(_partition_area(polygons, 2, []).values()), 3.0)

    def test_partition_and_translation_preserve_exact_area(self):
        for offset in (0.0, 1_000_000.0):
            pieces = [rectangle(offset + i / 8, offset, offset + (i + 1) / 8, offset + 2)
                      for i in range(16)]
            self.assertAlmostEqual(sum(_partition_area(pieces, 16, []).values()), 4.0)

    def test_parallel_plate_uses_area_not_mesh_width_or_branch_count(self):
        board = design(zones=[zone("z", rectangle(0, 0, 2, 2))])
        expected = EPSILON_0_F_M * 4 * 4e-6 / 0.2e-3
        for count in (1, 4, 16, 64):
            values, _, info = estimate_branch_capacitance(board, AnalysisSpec(),
                                                         [branch(length=1 / count)] * count)
            self.assertAlmostEqual(values.sum() / expected, 1.0, places=12)
            self.assertEqual(info["estimated_branch_count"], count)
            self.assertEqual(info["status"], "approximate")
            self.assertEqual(info["branch_reference_layers"], ["B.Cu"] * count)

    def test_fixed_physical_mesh_refinement_changes_C_below_two_percent(self):
        board = design(zones=[zone("z", rectangle(0, 0, 2, 2))])
        totals = []
        for h in (1.0, 0.5, 0.25):
            spec = AnalysisSpec(mode="ac", net_names=["SIG"], mesh={
                "target_size_mm": h, "zone_cell_mm": h, "max_zone_cells": 1000,
                "max_conductors": 2000, "memory_budget_mb": 512,
            })
            mesh = build_hybrid_mesh(board, spec)
            values, _, _ = estimate_branch_capacitance(board, spec, mesh.branches)
            totals.append(float(values.sum()))
        self.assertGreater(min(totals), 0)
        for coarse, fine in zip(totals, totals[1:]):
            self.assertLess(abs(coarse - fine) / fine, 0.02)

    def test_zone_pad_track_overlap_is_counted_once(self):
        board = design(zones=[zone("z", rectangle(0, 0, 2, 2))], pads=[
            {"id": "p", "at": [2, 1], "size": [2, 2], "shape": "rect", "layer": "F.Cu", "net_name": "SIG"},
        ], tracks=[{"id": "t", "start": [0, 1], "end": [4, 1], "width": 1,
                    "layer": "F.Cu", "net_name": "SIG"}])
        values, _, info = estimate_branch_capacitance(board, AnalysisSpec(),
            [branch(), branch("p", "pad"), branch("t", "track")])
        # Union of zone + pad is 6 mm^2, leaving exactly 1 mm of 1-mm-wide track.
        expected = EPSILON_0_F_M * 4 * 6e-6 / 0.2e-3 + estimate_line_capacitance_per_m(1, 0.2, 4) * 1e-3
        self.assertAlmostEqual(values.sum() / expected, 1.0, places=12)
        self.assertAlmostEqual(info["unique_estimated_area_mm2"], 7.0)

    def test_explicit_reference_is_projected_overlap_not_midpoint(self):
        board = design(zones=[zone("z", rectangle(0, 0, 2, 2)),
            zone("return", rectangle(1, -1, 3, 3), "GND", "B.Cu")])
        spec = AnalysisSpec(return_path={"mode": "explicit", "net": "GND"})
        values, _, info = estimate_branch_capacitance(board, spec,
            [branch(), branch("return", net="GND", layer="B.Cu")])
        expected = EPSILON_0_F_M * 4 * 2e-6 / 0.2e-3
        self.assertAlmostEqual(values.sum() / expected, 1.0, places=12)
        self.assertEqual(info["skipped_return_conductor_branch_count"], 1)

    def test_actual_counts_exclude_topology_vias_and_duplicate_copper(self):
        board = design(zones=[zone("z", rectangle(0, 0, 2, 2)), zone("zz", rectangle(0, 0, 2, 2))])
        values, _, info = estimate_branch_capacitance(board, AnalysisSpec(),
            [branch(), branch("zz"), branch(kind="pad_attachment"), branch(kind="via"), branch("missing")])
        self.assertEqual(np.count_nonzero(values), 1)
        self.assertEqual(info["estimated_branch_count"], 1)
        self.assertEqual(info["skipped_branch_count"], 4)
        for category in ("topology", "via", "geometry", "overlap"):
            self.assertEqual(info[f"skipped_{category}_branch_count"], 1)

    def test_missing_explicit_return_and_unsupported_pad_fail_closed(self):
        board = design(pads=[{"id": "p", "at": [0, 0], "size": [2, 2],
                             "shape": "custom", "layer": "F.Cu", "net_name": "SIG"}])
        for spec in (AnalysisSpec(), AnalysisSpec(return_path={"mode": "explicit"})):
            values, _, info = estimate_branch_capacitance(board, spec, [branch("p", "pad")])
            self.assertEqual(values.sum(), 0)
            self.assertEqual(info["status"], "unsupported")

    def test_two_dielectric_layers_use_series_electrical_height(self):
        board = design(zones=[zone("z", rectangle(0, 0, 2, 2))])
        board.stackup[1:2] = [{"name": "a", "thickness": 0.1, "epsilon_r": 2},
                              {"name": "b", "thickness": 0.1, "epsilon_r": 4}]
        values, _, _ = estimate_branch_capacitance(board, AnalysisSpec(), [branch()])
        expected = EPSILON_0_F_M * 4e-6 / (0.1e-3 / 2 + 0.1e-3 / 4)
        self.assertAlmostEqual(values.sum() / expected, 1.0, places=12)

    def test_missing_dielectric_segment_is_not_silently_omitted(self):
        board = design(zones=[zone("z", rectangle(0, 0, 2, 2))])
        board.stackup.insert(2, {"name": "unknown", "thickness": 0.1})
        values, _, info = estimate_branch_capacitance(board, AnalysisSpec(), [branch()])
        self.assertEqual(values.sum(), 0)
        self.assertEqual(info["status"], "unsupported")
        self.assertEqual(info["skipped_reference_branch_count"], 1)

    def test_owner_partition_does_not_change_parallel_plate_total(self):
        totals = []
        for count in (1, 2, 8):
            board = design(zones=[zone(str(i), rectangle(2 * i / count, 0, 2 * (i + 1) / count, 2))
                                 for i in range(count)])
            values, _, _ = estimate_branch_capacitance(board, AnalysisSpec(),
                                                      [branch(str(i)) for i in range(count)])
            totals.append(values.sum())
        np.testing.assert_allclose(totals, [totals[0]] * len(totals), rtol=1e-13, atol=0)

    def test_resource_limit_fails_closed_with_reason(self):
        with self.assertRaisesRegex(ValueError, "2000"):
            _partition_area([[(0, 0), (1, 0), (0, 1)]] * 1001, 1001, [])

    def test_roundrect_and_oval_match_analytic_area_with_fixed_chord_bound(self):
        for shape, ratio, expected in (("roundrect", 0.25, 8 - (4 - pi) * 0.5 ** 2),
                                       ("oval", None, 4 + pi)):
            pad = {"id": "p", "at": [0, 0], "size": [4, 2], "rotation": 17,
                   "shape": shape, "layer": "F.Cu", "net_name": "SIG"}
            if ratio is not None:
                pad["roundrect_rratio"] = ratio
            values, _, info = estimate_branch_capacitance(design(pads=[pad]), AnalysisSpec(), [branch("p", "pad")])
            area = info["unique_estimated_area_mm2"]
            self.assertGreater(values.sum(), 0)
            self.assertLessEqual(area, expected)
            self.assertLess((expected - area) / expected, 0.000402)

    def test_arcs_and_missing_roundrect_radius_are_explicitly_incomplete(self):
        board = design(tracks=[{"id": "t", "start": [0, 0], "mid": [1, 1], "end": [2, 0],
                               "width": 1, "net_name": "SIG", "layer": "F.Cu"}])
        values, _, info = estimate_branch_capacitance(board, AnalysisSpec(), [branch("t", "track")])
        self.assertEqual(values.sum(), 0)
        self.assertFalse(info["complete_source_coverage"])
        self.assertIn("arc", info["geometry_failures"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
