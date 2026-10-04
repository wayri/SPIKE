# SPDX-License-Identifier: Apache-2.0
"""Child and host checks for design-neutral Python script data views."""

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.script_runtime import run_python_script
from python.spike_core.script_views import ScriptViews, admit_views


class ScriptViewTests(unittest.TestCase):
    def test_design_free_views_cross_real_child_and_host(self):
        code = (
            "spike.publish_table('Cases', ['case', 'score'], [['A', 1.5], ['B', None]], "
            "units=['', 'V'], provenance='measured input')\n"
            "spike.publish_plot('Trace', [0, 1, 2], "
            "[{'name': 'port A', 'values': [1.0, None, 3.0]}], "
            "x_label='time', y_label='voltage', x_unit='s', y_unit='V')\n"
            "spike.publish_plot('Pattern', [0, 90], "
            "[{'name': 'gain', 'values': [1.0, 2.0]}], kind='polar')\n"
        )
        result = run_python_script({"code": code, "python_executable": sys.executable})
        self.assertEqual(result["status"], "completed", result["stderr"])
        self.assertIsNone(result["published_result"])
        self.assertEqual([view["kind"] for view in result["views"]], ["table", "line", "polar"])
        self.assertEqual({view["contract"] for view in result["views"]}, {"spike/data-view/v1"})
        self.assertEqual(len({view["id"] for view in result["views"]}), 3)
        self.assertEqual(result["views"][0]["rows"], [["A", 1.5], ["B", None]])
        self.assertEqual(result["views"][1]["series"][0]["values"], [1.0, None, 3.0])
        self.assertEqual(result["views"][2]["x_unit"], "deg")
        self.assertEqual(Path(result["runtime"]["executable"]).resolve(), Path(sys.executable).resolve())
        self.assertTrue(result["runtime"]["python_version"])
        self.assertIn("emerge_version", result["runtime"])
        self.assertIn("optycal_version", result["runtime"])

    def test_invalid_publication_fails_without_partial_views(self):
        cases = [
            ("spike.publish_table('A', ['x'], [[1]])\nspike.publish_table('bad', ['x'], [[float('nan')]])", "finite"),
            ("spike.publish_plot('bad', [0, 1], [{'name': 's', 'values': [1]}])", "length"),
            ("spike.publish_table('bad', ['a', 'b'], [[1]])", "rectangular"),
            ("spike.publish_table('bad', ['a'], [[{}]])", "finite"),
            ("spike.publish_plot('bad', [0], [{'name': 's', 'values': [-1]}], kind='polar')", "nonnegative"),
            ("spike.publish_plot('bad', [0], [{'name': 's', 'values': [1]}], kind='heatmap')", "unsupported"),
        ]
        for code, diagnostic in cases:
            with self.subTest(code=code):
                result = run_python_script({"code": code})
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["views"], [])
                self.assertIsNone(result["published_result"])
                self.assertIn(diagnostic, result["stderr"])

    def test_script_exception_discards_completed_views(self):
        result = run_python_script({"code": "spike.publish_table('A', ['x'], [[1]])\nraise RuntimeError('after view')"})
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["views"], [])
        self.assertIn("after view", result["stderr"])

    def test_complex_spatial_scalar_and_vector_views_cross_child_and_host(self):
        code = (
            "spike.publish_spatial('E field', [{'x': 0, 'y': 1, 'z': 2, 'real': 3, 'imag': -4}], quantity='Ex', unit='V/m')\n"
            "spike.publish_spatial('H vectors', [{'x': 1, 'y': 2, 'z': 3, 'vx': 1, 'vy': 0, 'vz': -2, 'vx_imag': .5, 'vy_imag': 0, 'vz_imag': 1}], quantity='H', unit='A/m')\n"
        )
        result = run_python_script({"code": code})
        self.assertEqual(result["status"], "completed", result["stderr"])
        self.assertEqual([view["kind"] for view in result["views"]], ["spatial", "spatial"])
        self.assertEqual(result["views"][0]["samples"][0]["value_imag"], -4)
        self.assertEqual(result["views"][1]["samples"][0]["vector_real"], [1, 0, -2])
        self.assertEqual(result["views"][1]["value_unit"], "A/m")
        with self.assertRaisesRegex(ValueError, "10000"):
            ScriptViews().publish_spatial("large", [{"x": 0, "y": 0, "z": 0, "real": 1}] * 10_001, quantity="E")

    def test_corner_node_mesh_crosses_child_and_host(self):
        result = run_python_script({"code": "spike.publish_mesh('surface', [[0,0,0],[1,0,0],[0,1,0]], [[0,1,2]], provenance='returned mesh')"})
        self.assertEqual(result["status"], "completed", result["stderr"])
        view = result["views"][0]
        self.assertEqual(view["kind"], "mesh")
        self.assertEqual(view["triangles"], [[0, 1, 2]])
        for triangles in ([[0, 1, 3]], [[0, 0, 1]], [[0, 1, 1.5]]):
            with self.subTest(triangles=triangles), self.assertRaisesRegex(ValueError, "in-bounds integer"):
                ScriptViews().publish_mesh("bad", [[0,0,0],[1,0,0],[0,1,0]], triangles)

    def test_complete_physical_mesh_budget(self):
        collector = ScriptViews()
        vertices = [[float(i), 0., 0.] for i in range(10_000)]
        triangles = [[0, 1, 2]] * 10_000
        collector.publish_mesh('complete', vertices, triangles)
        self.assertEqual(len(admit_views(collector.views)[0]['triangles']), 10_000)
        with self.assertRaisesRegex(ValueError, '10000'):
            ScriptViews().publish_mesh('too many', vertices + [[0., 1., 0.]], triangles)
        with self.assertRaisesRegex(ValueError, '10000'):
            ScriptViews().publish_mesh('too many', vertices, triangles + [[0, 1, 2]])
        with self.assertRaisesRegex(ValueError, '100,000'):
            collector.publish_table('aggregate', ['value'], [[1]] * 40_001)
    def test_publication_and_host_limits(self):
        collector = ScriptViews()
        collector.publish_table("A", ["x"], [[1], [None], [False]])
        self.assertEqual(collector.views[0]["units"], [])
        for index in range(11):
            collector.publish_table(f"T{index}", ["x"], [])
        with self.assertRaisesRegex(ValueError, "12"):
            collector.publish_table("overflow", ["x"], [])
        for columns, rows in [(["x"] * 33, []), (["x", "y"], [[1]])]:
            with self.assertRaises(ValueError):
                ScriptViews().publish_table("invalid", columns, rows)
        with self.assertRaisesRegex(ValueError, "100,000"):
            ScriptViews().publish_table("large", ["x", "y"], [[1, 2]] * 50_001)
        with self.assertRaisesRegex(ValueError, "1 MB"):
            ScriptViews().publish_table("text", ["x"], [["é" * 500_001]])
        with self.assertRaisesRegex(ValueError, "2000"):
            ScriptViews().publish_table("x" * 2_001, ["x"], [])
        with self.assertRaisesRegex(ValueError, "20000"):
            ScriptViews().publish_plot("large", list(range(20_001)), [{"name": "s", "values": [1] * 20_001}])
        with self.assertRaisesRegex(ValueError, "12"):
            ScriptViews().publish_plot("wide", [0], [{"name": str(i), "values": [1]} for i in range(13)])
        with self.assertRaisesRegex(ValueError, "100,000"):
            ScriptViews().publish_plot("dense", list(range(10_000)), [{"name": str(i), "values": [1] * 10_000} for i in range(10)])
        view = collector.views[0]
        for replacement in [dict(view, id="not-uuid"), dict(view, kind="heatmap"),
                            dict(view, rows=[[float("inf")]]), dict(view, unexpected=True)]:
            with self.assertRaises(ValueError):
                admit_views([replacement])
        with self.assertRaisesRegex(ValueError, "unique"):
            admit_views([view, copy.deepcopy(view)])

    def test_host_validation_failure_discards_views(self):
        with patch("python.spike_core.script_runtime.admit_views", side_effect=ValueError("malformed view")):
            result = run_python_script({"code": "spike.publish_table('A', ['x'], [[1]])"})
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["views"], [])
        self.assertIn("malformed view", result["stderr"])

    def test_external_interpreter_path_validation(self):
        for value in ["python", ".", str(Path.cwd()), str(Path.cwd() / "missing-python.exe")]:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "absolute path"):
                run_python_script({"code": "print('x')", "python_executable": value})
        result = run_python_script({"code": "print('external interpreter')",
                                    "python_executable": str(Path(sys.executable).resolve())})
        self.assertEqual(result["status"], "completed", result["stderr"])
        self.assertIn("external interpreter", result["stdout"])


if __name__ == "__main__":
    unittest.main()
