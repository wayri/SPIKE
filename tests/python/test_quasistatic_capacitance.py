# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic

from copy import deepcopy
import unittest

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.hybrid_mesh import build_hybrid_mesh
from python.spike_core.hybrid_mesh import MeshBranch
from python.spike_core.quasistatic_capacitance import (
    EPSILON_0_F_M,
    estimate_branch_capacitance,
    estimate_line_capacitance_per_m,
)


class QuasistaticCapacitanceTests(unittest.TestCase):
    def test_invalid_or_ambiguous_zone_area_is_never_admitted(self):
        design = DesignIR(
            zones=[{"id": "signal", "layer": "F.Cu", "net_name": "VCC",
                    "points": [(0, 0), (2, 0), (2, 2), (0, 2)]},
                   {"id": "return", "layer": "B.Cu", "net_name": "GND",
                    "points": [(-1, -1), (3, -1), (3, 3), (-1, 3)]}],
            stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035},
                     {"name": "core", "type": "core", "thickness": 0.2, "epsilon_r": 4.0},
                     {"name": "B.Cu", "type": "copper", "thickness": 0.035}],
        )
        spec = AnalysisSpec(mode="ac", net_names=["VCC", "GND"],
                            return_path={"mode": "explicit", "net": "GND"})
        branch = MeshBranch("signal-link", "zone", 0, 1, (0.5, 1, 0), (1.5, 1, 0),
                            0.5, 0.035, 5.8e7, "F.Cu", "VCC", "signal")
        baseline, _, info = estimate_branch_capacitance(design, spec, [branch])
        self.assertGreater(float(baseline.sum()), 0)
        self.assertEqual(info["status"], "approximate")
        for defect in ("hole", "nonfinite", "duplicate"):
            altered = deepcopy(design)
            if defect == "hole":
                altered.zones[0]["holes"] = [[(0.5, 0.5), (1, 0.5), (0.5, 1)]]
            elif defect == "nonfinite":
                altered.zones[0]["points"][0] = (float("nan"), 0)
            else:
                altered.zones.append(deepcopy(altered.zones[0]))
            with self.subTest(defect=defect):
                values, _, quality = estimate_branch_capacitance(altered, spec, [branch])
                self.assertEqual(float(values.sum()), 0.0)
                self.assertEqual(quality["status"], "unsupported")

    def test_fixed_zone_area_is_invariant_to_internal_link_refinement(self):
        design = DesignIR(
            layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
            nets=[{"name": "VCC"}, {"name": "GND"}],
            zones=[
                {"id": "signal-zone", "layer": "F.Cu", "net_name": "VCC",
                 "points": [(0, 0), (2, 0), (2, 2), (0, 2)],
                 "filled_copper_state": "source_filled", "source_fill_provenance_complete": True},
                {"id": "return-zone", "layer": "B.Cu", "net_name": "GND",
                 "points": [(-1, -1), (3, -1), (3, 3), (-1, 3)],
                 "filled_copper_state": "source_filled", "source_fill_provenance_complete": True},
            ],
            stackup=[
                {"name": "F.Cu", "type": "copper", "thickness": 0.035},
                {"name": "core", "type": "core", "thickness": 0.2, "epsilon_r": 4.0},
                {"name": "B.Cu", "type": "copper", "thickness": 0.035},
            ],
        )
        spec = AnalysisSpec(mode="ac", net_names=["VCC", "GND"],
                            return_path={"mode": "explicit", "net": "GND"})
        totals = []
        for n in (2, 4, 8, 16):
            h = 2.0 / n
            branches = []
            node = 0
            for row in range(n):
                for column in range(n - 1):
                    y, x = (row + 0.5) * h, (column + 0.5) * h
                    branches.append(MeshBranch(
                        f"z:h:{row}:{column}", "zone", node, node + 1,
                        (x, y, 0), (x + h, y, 0), h, 0.035, 5.8e7,
                        "F.Cu", "VCC", "signal-zone"))
                    node += 2
            values, _, info = estimate_branch_capacitance(design, spec, branches)
            totals.append(float(values.sum()))
            self.assertEqual(info["admitted_planar_source_count"], 1)
        expected = EPSILON_0_F_M * 4.0 * 4.0e-6 / 0.2e-3
        for value in totals:
            self.assertAlmostEqual(value, expected, delta=expected * 1e-12)

    def test_wide_microstrip_approaches_parallel_plate_limit(self):
        width_mm = 100.0
        height_mm = 1.0
        epsilon_r = 4.0
        measured = estimate_line_capacitance_per_m(width_mm, height_mm, epsilon_r)
        parallel_plate = EPSILON_0_F_M * epsilon_r * width_mm / height_mm
        self.assertLess(abs(measured - parallel_plate) / parallel_plate, 0.05)

    def test_explicit_return_extracts_capacitance_and_dielectric_loss(self):
        design = DesignIR(
            layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
            nets=[{"name": "VCC"}, {"name": "GND"}],
            tracks=[
                {"id": "signal", "start": [0, 0], "end": [20, 0], "width": 1.0, "layer": "F.Cu", "net_name": "VCC"},
                {"id": "return", "start": [0, 0], "end": [20, 0], "width": 5.0, "layer": "B.Cu", "net_name": "GND"},
            ],
            stackup=[
                {"name": "F.Cu", "type": "copper", "thickness": 0.035},
                {"name": "core", "type": "core", "thickness": 0.2, "epsilon_r": 4.2, "loss_tangent": 0.018},
                {"name": "B.Cu", "type": "copper", "thickness": 0.035},
            ],
        )
        spec = AnalysisSpec(
            mode="ac",
            net_names=["VCC", "GND"],
            return_path={"mode": "explicit", "net": "GND"},
            mesh={"target_size_mm": 5.0},
        )
        mesh = build_hybrid_mesh(design, spec)
        values, losses, info = estimate_branch_capacitance(design, spec, mesh.branches)
        signal_indices = [index for index, branch in enumerate(mesh.branches) if branch.net == "VCC"]
        self.assertEqual(info["status"], "approximate")
        self.assertEqual(info["reference_net"], "GND")
        self.assertGreater(sum(values[index] for index in signal_indices), 0)
        self.assertTrue(all(losses[index] > 0 for index in signal_indices))
        self.assertGreater(info["loss_tangent_branch_coverage"], 0)

    def test_via_capacitance_remains_explicitly_unsupported(self):
        design = DesignIR(
            layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
            vias=[{"id": "v1", "at": [0, 0], "drill": 0.3, "size": 0.6, "layers": ["F.Cu", "B.Cu"], "net_name": "VCC"}],
            stackup=[
                {"name": "F.Cu", "type": "copper", "thickness": 0.035},
                {"name": "core", "type": "core", "thickness": 0.2, "epsilon_r": 4.2},
                {"name": "B.Cu", "type": "copper", "thickness": 0.035},
            ],
        )
        spec = AnalysisSpec(mode="ac", net_names=["VCC"])
        mesh = build_hybrid_mesh(design, spec)
        values, _, info = estimate_branch_capacitance(design, spec, mesh.branches)
        self.assertEqual(float(values.sum()), 0.0)
        self.assertGreater(info["skipped_via_branch_count"], 0)

    def test_remote_explicit_return_copper_is_not_treated_as_a_plane(self):
        design = DesignIR(
            layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
            tracks=[
                {"id": "signal", "start": [0, 0], "end": [10, 0], "width": 0.5, "layer": "F.Cu", "net_name": "VCC"},
                {"id": "remote-return", "start": [0, 50], "end": [10, 50], "width": 1.0, "layer": "B.Cu", "net_name": "GND"},
            ],
            stackup=[
                {"name": "F.Cu", "type": "copper", "thickness": 0.035},
                {"name": "core", "type": "core", "thickness": 0.2, "epsilon_r": 4.2},
                {"name": "B.Cu", "type": "copper", "thickness": 0.035},
            ],
        )
        spec = AnalysisSpec(
            mode="ac",
            net_names=["VCC", "GND"],
            return_path={"mode": "explicit", "net": "GND"},
            mesh={"target_size_mm": 5.0},
        )
        mesh = build_hybrid_mesh(design, spec)
        values, _, info = estimate_branch_capacitance(design, spec, mesh.branches)
        signal_indices = [index for index, branch in enumerate(mesh.branches) if branch.net == "VCC"]
        self.assertEqual(sum(values[index] for index in signal_indices), 0.0)
        self.assertGreater(info["skipped_reference_geometry_branch_count"], 0)


if __name__ == "__main__":
    unittest.main()
