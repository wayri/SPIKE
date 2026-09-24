# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Transient must stamp the shared C estimator, not retessellate microstrips."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.transient_peec import _extract_stackup_capacitance, transient_settings


class TransientCapacitanceConsistencyTests(unittest.TestCase):
    def fixture(self):
        design = DesignIR(stackup=[
            {"name": "F.Cu", "thickness": .035},
            {"name": "core", "thickness": .2, "epsilon_r": 4},
            {"name": "B.Cu", "thickness": .035},
        ])
        spec = AnalysisSpec(mode="transient", net_names=["S", "G"],
                            return_path={"mode": "explicit", "net": "G"})
        branches = [SimpleNamespace(kind="zone", layer="F.Cu", length_mm=1,
                    start_mm=(0, 0, 0), end_mm=(1, 0, 0))]
        nodes = [{"net": "S", "layer": "F.Cu", "x_mm": x, "y_mm": 0} for x in (0, 1)]
        nodes.append({"net": "G", "layer": "B.Cu", "x_mm": .5, "y_mm": 0})
        return design, spec, branches, nodes

    def test_shared_value_and_layer_are_stamped_conservatively(self):
        design, spec, branches, nodes = self.fixture()
        info = {"model": "area-surrogate", "branch_reference_layers": ["B.Cu"],
                "estimated_branch_count": 1, "total_capacitance_f": 8e-12}
        # Second endpoint pair records the explicit reference physical node.
        with patch("python.spike_core.quasistatic_capacitance.estimate_branch_capacitance",
                   return_value=(np.array([8e-12]), np.zeros(1), info)):
            matrix, provenance, values = _extract_stackup_capacitance(
                design, spec, transient_settings(spec), branches, [(0, 2)], nodes, 3)
        self.assertEqual(provenance["model"], "area-surrogate")
        self.assertEqual(values[0], 8e-12)
        np.testing.assert_allclose(matrix.sum(axis=0), 0, atol=1e-25)
        self.assertGreaterEqual(np.linalg.eigvalsh(matrix)[0], -1e-25)

    def test_missing_reference_node_cannot_receive_implicit_shunt(self):
        design, spec, branches, nodes = self.fixture()
        with patch("python.spike_core.quasistatic_capacitance.estimate_branch_capacitance",
                   return_value=(np.array([8e-12]), np.zeros(1), {"branch_reference_layers": ["B.Cu"]})):
            matrix, info, values = _extract_stackup_capacitance(
                design, spec, transient_settings(spec), branches, [(0, 1)], nodes[:2], 2)
        self.assertEqual(float(matrix.sum()), 0)
        self.assertEqual(values[0], 0)
        self.assertEqual(info["estimated_branch_count"], 0)
