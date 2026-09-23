# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Independent overlap-energy checks for the volume PEEC resistance form."""

import math
import unittest
from pathlib import Path

import numpy as np

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.hybrid_mesh import (
    MeshBranch, TOPOLOGY_ONLY_BRANCH_KINDS, build_hybrid_mesh,
)
from python.spike_core.peec_volume_resistance import assemble_overlap_resistance
from python.spike_core.service import _design_from_kicad


def rectangle(name, start, end, width=0.2, z=0.0, net="N"):
    return MeshBranch(name, "track", 0, 1, (*start, z), (*end, z), width, 0.035,
                      5.8e7, "F.Cu", net, name)


def annulus(name, low, high, x=0.0, y=0.0):
    plating = 0.025
    diameter = 0.3
    return MeshBranch(name, "via", 0, 1, (x, y, low), (x, y, high),
                      math.pi * (diameter + plating), plating, 5.8e7,
                      "F.Cu->B.Cu", "N", name)


class VolumeResistanceTests(unittest.TestCase):
    def test_identical_and_reversed_bases_preserve_energy(self):
        forward = rectangle("a", (0.0, 0.0), (1.0, 0.0))
        duplicate = rectangle("b", (0.0, 0.0), (1.0, 0.0))
        reversed_basis = rectangle("c", (1.0, 0.0), (0.0, 0.0))
        matrix, quality = assemble_overlap_resistance(
            DesignIR(), [forward, duplicate, reversed_basis]
        )
        expected = forward.resistance_ohm
        np.testing.assert_allclose(matrix, expected * np.array([
            [1, 1, -1], [1, 1, -1], [-1, -1, 1]
        ]), rtol=1e-12, atol=1e-17)
        self.assertEqual(quality["overlap_pair_count"], 3)
        self.assertGreaterEqual(quality["minimum_resistance_eigenvalue_ohm"], -1e-17)

    def test_partial_overlap_and_orthogonal_current(self):
        base = rectangle("a", (233.0, 159.0), (234.0, 159.0))
        shifted = rectangle("b", (233.0, 159.1), (234.0, 159.1))
        transverse = rectangle("c", (233.5, 158.7), (233.5, 159.3))
        matrix, _ = assemble_overlap_resistance(DesignIR(), [base, shifted, transverse])
        self.assertAlmostEqual(matrix[0, 1] / matrix[0, 0], 0.5, places=10)
        self.assertAlmostEqual(matrix[0, 2], 0.0, places=16)
        self.assertAlmostEqual(matrix[1, 2], 0.0, places=16)

    def test_coaxial_segment_additivity_and_cross_shape_orthogonality(self):
        design = DesignIR(vias=[{"id": name, "drill": 0.3} for name in ("a", "b", "c")])
        first, second = annulus("a", 0.0, 0.1), annulus("b", 0.1, 0.2)
        matrix, _ = assemble_overlap_resistance(design, [first, second,
            rectangle("track", (-0.5, 0.0), (0.5, 0.0))])
        self.assertEqual(matrix[0, 1], 0.0)
        self.assertEqual(matrix[0, 2], 0.0)
        self.assertAlmostEqual(matrix[0, 0] + matrix[1, 1],
                               annulus("c", 0.0, 0.2).resistance_ohm, places=13)

    def test_incompatible_overlap_rejected(self):
        first = rectangle("a", (0.0, 0.0), (1.0, 0.0), net="N")
        other = rectangle("b", (0.0, 0.0), (1.0, 0.0), net="OTHER")
        with self.assertRaisesRegex(ValueError, "incompatible net"):
            assemble_overlap_resistance(DesignIR(), [first, other])
        crossing_other_net = rectangle("c", (0.5, -0.5), (0.5, 0.5), net="OTHER")
        with self.assertRaisesRegex(ValueError, "incompatible net"):
            assemble_overlap_resistance(DesignIR(), [first, crossing_other_net])
        via_design = DesignIR(vias=[{"id": name, "drill": 0.3} for name in ("a", "b")])
        with self.assertRaisesRegex(ValueError, "noncoaxial annuli"):
            assemble_overlap_resistance(via_design,
                                        [annulus("a", 0.0, 0.1), annulus("b", 0.0, 0.1, x=0.01)])

    def test_optional_marble_retained_copper_is_ohmically_passive(self):
        board = (Path(__file__).resolve().parents[2] / "build" / "marble-qualification"
                 / "sources" / "Marble-v1.4.4" / "design" / "Marble.kicad_pcb")
        if not board.is_file():
            self.skipTest("pinned public Marble board has not been fetched")
        design = _design_from_kicad(str(board))
        net = "Net-(C383-Pad1)"
        for field in ("tracks", "vias", "pads", "zones"):
            setattr(design, field, [item for item in getattr(design, field)
                                   if str(item.get("net_name", item.get("net", ""))) == net])
        mesh = build_hybrid_mesh(design, AnalysisSpec(mode="ac", net_names=[net],
            mesh={"target_size_mm": 1.0, "zone_cell_mm": 1.0,
                  "max_conductors": 500, "max_zone_cells": 250}))
        self.assertFalse(mesh.truncated)
        branches = [item for item in mesh.branches
                    if item.kind not in TOPOLOGY_ONLY_BRANCH_KINDS]
        self.assertEqual(len(branches), 45)
        matrix, quality = assemble_overlap_resistance(design, branches)
        self.assertEqual(matrix.shape, (45, 45))
        self.assertGreater(quality["overlap_pair_count"], 0)
        self.assertGreaterEqual(quality["minimum_resistance_eigenvalue_ohm"], -1e-18)


if __name__ == "__main__":
    unittest.main()
