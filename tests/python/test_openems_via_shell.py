# SPDX-License-Identifier: Apache-2.0
"""Exact radial contract shared by host admission and isolated CSXCAD worker."""
from __future__ import annotations

import ast
import math
import unittest

from extensions.openems_suite.openems_adapter_source import OPENEMS_DRIVER, via_shell_dimensions


class ViaShellTests(unittest.TestCase):
    def test_shell_preserves_drill_and_wall_radii(self):
        radius, width = via_shell_dimensions(.6, .35, .025)
        self.assertAlmostEqual(radius - width/2, .35/2)
        self.assertAlmostEqual(radius + width/2, .35/2 + .025)

    def test_worker_uses_same_source(self):
        parsed = ast.parse(OPENEMS_DRIVER)
        helpers = [node for node in parsed.body if isinstance(node, ast.FunctionDef)
                   and node.name == "via_shell_dimensions"]
        self.assertEqual(len(helpers), 1)
        namespace = {"math": math}
        exec(compile(ast.Module(body=helpers, type_ignores=[]), "worker-via", "exec"), namespace)
        self.assertEqual(namespace["via_shell_dimensions"](.6, .35, .025),
                         via_shell_dimensions(.6, .35, .025))

    def test_invalid_wall_is_rejected_without_clamping(self):
        for dimensions in ((.6, .35, 0), (.6, .35, .2), (.6, .6, .025),
                           (.6, -.1, .025), (.6, .35, math.nan)):
            with self.subTest(dimensions=dimensions), self.assertRaises(ValueError):
                via_shell_dimensions(*dimensions)


if __name__ == "__main__":
    unittest.main()
