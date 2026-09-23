# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Independent area oracles for fail-closed rectangular zone support admission."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.hybrid_mesh import MeshBranch, build_hybrid_mesh
from python.spike_core.peec_volume_adapter import extract_volume_matrices
from python.spike_core.peec_volume_support import (
    ZoneBasisSupportError, admit_zone_basis_support, zone_basis_support_report,
)


def _design(points):
    return DesignIR(zones=[{"id": "source-zone", "layer": "F.Cu",
                           "net_name": "N", "points": points}])


def _branch(start=(0.0, 0.5), end=(1.5, 0.5), width=1.0):
    return MeshBranch("source-zone:link:0:1", "zone", 0, 1,
                      (*start, 0.0), (*end, 0.0), width, 0.035, 5.8e7,
                      "F.Cu", "N", "source-zone")


class ZoneBasisSupportTests(unittest.TestCase):
    def test_sloping_boundary_leak_has_exact_triangular_area(self):
        design = _design([(0, 0), (2, 0), (0, 2)])
        branch = _branch()
        saved = deepcopy((design, branch))
        report = zone_basis_support_report(design, [branch])
        self.assertAlmostEqual(report["outside_area_sum_mm2"], 0.5 * 0.5 * 0.5)
        self.assertEqual(report["violations"][0]["source_id"], "source-zone")
        self.assertEqual(report["violations"][0]["branch_id"], branch.id)
        self.assertEqual((design, branch), saved)  # No width/topology mutation.
        with self.assertRaises(ZoneBasisSupportError) as caught:
            admit_zone_basis_support(design, [branch])
        self.assertEqual(caught.exception.code, "PEEC_ZONE_BASIS_OUTSIDE_COPPER")
        self.assertEqual(caught.exception.report, report)

    def test_concave_notch_not_only_rectangle_corners_is_checked(self):
        design = _design([(0, 0), (3, 0), (3, 3), (2, 3),
                          (2, 1), (1, 1), (1, 3), (0, 3)])
        report = zone_basis_support_report(design, [_branch((0.5, 1), (2.5, 1))])
        self.assertAlmostEqual(report["outside_area_sum_mm2"], 0.5)

    def test_clockwise_and_translated_polygons_are_equivalent(self):
        polygon = [(0, 0), (2, 0), (0, 2)]
        for offset in (0.0, 1e8):
            for points in (polygon, polygon[::-1]):
                design = _design([(x + offset, y + offset) for x, y in points])
                branch = _branch((offset, offset + 0.5), (offset + 1.5, offset + 0.5))
                with self.subTest(offset=offset, clockwise=points == polygon[::-1]):
                    self.assertAlmostEqual(zone_basis_support_report(design, [branch])[
                        "outside_area_sum_mm2"], 0.125, places=12)

    def test_exact_boundary_contact_and_reversed_current_are_admitted(self):
        design = _design([(0, 0), (2, 0), (2, 1), (0, 1)])
        branch = _branch((0, 0.5), (2, 0.5))
        for item in (branch, replace(branch, start_mm=branch.end_mm, end_mm=branch.start_mm)):
            self.assertEqual(admit_zone_basis_support(design, [item])["violations"], [])

    def test_all_violating_owners_are_retained(self):
        design = _design([(0, 0), (2, 0), (0, 2)])
        with self.assertRaises(ZoneBasisSupportError) as caught:
            admit_zone_basis_support(design, [_branch(), replace(_branch(), id="second-link")])
        self.assertEqual([row["branch_id"] for row in caught.exception.report["violations"]],
                         ["source-zone:link:0:1", "second-link"])

    def test_ambiguous_missing_mismatched_and_hole_sources_fail_closed(self):
        baseline = _design([(0, 0), (2, 0), (2, 1), (0, 1)])
        variants = [DesignIR(), replace(baseline, zones=baseline.zones * 2)]
        for field, value in (("layer", "B.Cu"), ("net_name", "other"),
                             ("holes", [[(0, 0), (1, 0), (0, 1)]])):
            altered = deepcopy(baseline)
            altered.zones[0][field] = value
            variants.append(altered)
        for design in variants:
            with self.subTest(zones=design.zones), self.assertRaises(ZoneBasisSupportError) as caught:
                admit_zone_basis_support(design, [_branch()])
            self.assertEqual(caught.exception.code, "PEEC_ZONE_SUPPORT_UNRESOLVED")
            self.assertEqual(caught.exception.report["source_id"], "source-zone")

    def test_nonfinite_and_self_crossing_boundaries_fail_closed(self):
        for points in ([(0, 0), (float("nan"), 0), (0, 1)],
                       [(0, 0), (float("inf"), 0), (0, 1)],
                       [{"x": 0}, (2, 0), (0, 1)],
                       [(0, 0), (2, 2), (0, 2), (2, 0)]):
            with self.subTest(points=points), self.assertRaises(ZoneBasisSupportError):
                admit_zone_basis_support(_design(points), [_branch()])

    def test_invalid_zone_current_geometry_has_stable_unresolved_code(self):
        design = _design([(0, 0), (2, 0), (2, 1), (0, 1)])
        branch = _branch((0.5, 0.5), (0.5, 0.5))
        with self.assertRaises(ZoneBasisSupportError) as caught:
            admit_zone_basis_support(design, [branch])
        self.assertEqual(caught.exception.code, "PEEC_ZONE_SUPPORT_UNRESOLVED")
        self.assertEqual(caught.exception.report["branch_id"], branch.id)

    def test_rejection_precedes_native_allocation_and_quadrature(self):
        backend = SimpleNamespace(**{name: Mock() for name in (
            "VolumeMatrixAssembler", "VolumeMatrixIntegrationOptions",
            "VolumeRectangularBasis", "VolumeCoaxialAnnulusBasis")})
        with self.assertRaisesRegex(ZoneBasisSupportError, "OUTSIDE_COPPER"):
            extract_volume_matrices(backend, _design([(0, 0), (2, 0), (0, 2)]), [_branch()])
        backend.VolumeMatrixAssembler.assert_not_called()
        backend.VolumeMatrixIntegrationOptions.assert_not_called()

    def test_nonzone_bases_are_outside_this_gate_scope(self):
        self.assertEqual(admit_zone_basis_support(DesignIR(), [replace(_branch(), kind="track")])[
            "zone_basis_count"], 0)

    def test_optional_marble_reproduces_independent_support_audit(self):
        from python.spike_core.service import _design_from_kicad

        board = (Path(__file__).resolve().parents[2] / "build" / "marble-qualification"
                 / "sources" / "Marble-v1.4.4" / "design" / "Marble.kicad_pcb")
        if not board.is_file():
            self.skipTest("pinned public Marble board has not been fetched")
        design = _design_from_kicad(str(board))
        net = "Net-(C383-Pad1)"
        for field in ("tracks", "vias", "pads", "zones"):
            setattr(design, field, [item for item in getattr(design, field)
                                   if str(item.get("net_name", item.get("net", ""))) == net])
        # Independent Shapely measurements recorded in MARBLE_PEEC_MESH_AUDIT.md.
        for size, count, violations, outside in ((1.0, 18, 7, 0.558522869),
                                                (0.5, 82, 19, 0.710276566),
                                                (0.25, 315, 40, 0.294066074)):
            mesh = build_hybrid_mesh(design, AnalysisSpec(mode="ac", net_names=[net],
                mesh={"target_size_mm": size, "zone_cell_mm": size,
                      "max_zone_cells": 1000, "max_conductors": 2000}))
            with self.subTest(size_mm=size):
                self.assertFalse(mesh.truncated)
                report = zone_basis_support_report(design, mesh.branches)
                self.assertEqual(report["zone_basis_count"], count)
                self.assertEqual(report["violating_basis_count"], violations)
                self.assertAlmostEqual(report["outside_area_sum_mm2"], outside, delta=1e-8)
                with self.assertRaises(ZoneBasisSupportError):
                    admit_zone_basis_support(design, mesh.branches)


if __name__ == "__main__":
    unittest.main()
