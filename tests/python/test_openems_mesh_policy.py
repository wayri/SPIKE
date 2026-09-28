# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Deterministic tests for openEMS final-grid admission and mesh seeding."""

from __future__ import annotations

import ast
import math
import unittest

from extensions.openems_suite.openems_adapter_source import OPENEMS_DRIVER, pad_polygon
from extensions.openems_suite.openems_mesh_policy import actual_grid_report, require_time_window


class OpenEmsMeshPolicyTests(unittest.TestCase):
    def test_actual_grid_metrics_have_units_and_vacuum_cfl_bound(self):
        report = actual_grid_report(
            {"x": [0.0, 1.0, 3.0], "y": [-1.0, 1.0], "z": [0.0, 0.5, 1.0]},
            8,
            8 * 256,
        )
        self.assertEqual(report["axis_cell_counts"], {"x": 2, "y": 1, "z": 2})
        self.assertEqual(report["cell_count"], 4)
        self.assertEqual(report["estimated_memory_bytes"], 1024)
        self.assertEqual(report["minimum_spacing_mm"], {"x": 1.0, "y": 2.0, "z": 0.5})
        expected = 1.0 / (299_792_458.0 * math.sqrt(
            1 / 0.001**2 + 1 / 0.002**2 + 1 / 0.0005**2))
        self.assertAlmostEqual(report["vacuum_cfl_reference_timestep_s"], expected, places=24)

    def test_actual_grid_fails_closed_for_order_and_budgets(self):
        valid = {"x": [0, 1, 2], "y": [0, 1, 2], "z": [0, 1, 2]}
        with self.assertRaisesRegex(RuntimeError, "NOT_INCREASING_X"):
            actual_grid_report({**valid, "x": [0, 1, 1]}, 100, 100000)
        with self.assertRaisesRegex(RuntimeError, "CELL_BUDGET_EXCEEDED"):
            actual_grid_report(valid, 7, 100000)
        with self.assertRaisesRegex(RuntimeError, "MEMORY_BUDGET_EXCEEDED"):
            actual_grid_report(valid, 8, 2047)
        with self.assertRaisesRegex(RuntimeError, "SPACING_UNREPRESENTABLE_X"):
            actual_grid_report({**valid, "x": [0, 1e-13, 1]}, 100, 100000)

    def test_conservative_time_window_policy_rejects_short_reference(self):
        grid = actual_grid_report(
            {axis: [0, 0.0078, 1] for axis in ("x", "y", "z")},
            100, 100000,
        )
        with self.assertRaisesRegex(RuntimeError, "TIME_WINDOW_POLICY_INSUFFICIENT"):
            require_time_window(grid, 30000, 100e6, 1e9)
        accepted = require_time_window(grid, 10_000_000, 100e6, 1e9)
        self.assertGreaterEqual(
            accepted["cfl_reference_time_window_s"],
            accepted["minimum_one_cycle_window_s"],
        )

    def test_curved_pad_polygon_and_ports_are_not_changed(self):
        pad = {"shape": "circle", "at": [4.0, -2.0], "size": [1.0, 1.0]}
        before = pad_polygon(pad)
        namespace = {"math": math}
        tree = ast.parse(OPENEMS_DRIVER)
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "pad_polygon")
        exec(compile(ast.Module(body=[function], type_ignores=[]), "<driver-pad>", "exec"), namespace)
        self.assertEqual(namespace["pad_polygon"](pad), before)
        self.assertIn('edges2grid="all"', OPENEMS_DRIVER)
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "AddEdges2Grid"
        ]
        self.assertEqual(len(calls), 1)
        self.assertIn('options.get("experimental_compact_edge_grid", False) is True', OPENEMS_DRIVER)
        self.assertIn('if not compact_edges:', OPENEMS_DRIVER)
        self.assertIn("actual_grid_report(", OPENEMS_DRIVER)
        self.assertIn("require_time_window(", OPENEMS_DRIVER)
        self.assertLess(OPENEMS_DRIVER.index("actual_grid_report("), OPENEMS_DRIVER.index("fdtd.Run("))


if __name__ == "__main__":
    unittest.main()
