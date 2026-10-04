# SPDX-License-Identifier: Apache-2.0
"""Explicit Python interpreter coverage for the integrated script workspace."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from python.spike_core import __version__ as SPIKE_VERSION
from python.spike_core.script_runtime import run_python_script


DESIGN = {"contract": "spike/v1", "design_id": "external-board", "name": "External board",
          "source_format": "test", "units": "mm", "layers": [], "nets": [], "tracks": [],
          "vias": [], "pads": [], "zones": [], "components": [], "stackup": [],
          "issues": [], "metadata": {}}
ROOT = Path(__file__).resolve().parents[2]


def engine_interpreter() -> str:
    candidates = [ROOT / ".venv/Scripts/python.exe", ROOT / ".venv/bin/python", Path(sys.executable)]
    for candidate in candidates:
        if candidate.is_file() and subprocess.run([str(candidate), "-I", "-c", "import jsonschema"], capture_output=True).returncode == 0:
            return str(candidate.resolve())
    raise RuntimeError("External-engine test requires an isolated interpreter with SPIKE runtime dependencies.")


class ExternalPythonInterpreterTests(unittest.TestCase):
    def test_explicit_interpreter_preserves_file_workspace_imports_and_ui_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            working = Path(directory)
            (working / "helper.py").write_text("VALUE = 23\n", encoding="utf-8")
            result = run_python_script({
                "python_executable": sys.executable,
                "working_directory": str(working),
                "filename": "analysis.py",
                "workspace": {"boards": [{"id": "board-a", "name": "A", "design_id": "external-board", "design": DESIGN}], "selected_board_id": "board-a", "assembly": {}},
                "code": "import helper\nprint(__file__)\nprint(spike.boards.list()[0]['id'], helper.VALUE)\nspike.ui.open_panel('results')\n",
            })
        self.assertEqual(result["status"], "completed", result.get("stderr"))
        self.assertIn(str(working / "analysis.py"), result["stdout"])
        self.assertIn("board-a 23", result["stdout"])
        self.assertEqual(result["ui_actions"][0]["action"], "open_panel")

    def test_isolated_interpreter_bootstraps_extensions_and_host_sdk(self):
        result = run_python_script({
            "python_executable": sys.executable,
            "code": "from python.spike_core import __version__\nfrom extension_sdk.python.spike_extension_sdk import analysis_envelope\nfrom extensions.emerge_suite.normalize import _number\nprint(__version__)\nprint(analysis_envelope({'contract': 'spike/v1'}, title='SDK')['contract'])\nprint(_number(2, 'value'))\n",
        })
        self.assertEqual(result["status"], "completed", result.get("stderr"))
        self.assertIn(SPIKE_VERSION, result["stdout"])
        self.assertIn("spike/extension-result/v1", result["stdout"])
        self.assertTrue(result["stdout"].rstrip().endswith("2.0"))

    def test_explicit_interpreter_invokes_trusted_external_engine(self):
        examples = Path(__file__).resolve().parents[2] / "extension_sdk/examples"
        code = """reply = spike.invoke_extension(
    'org.example.field-data-adapter', 'import-voltage-field',
    {'samples': [{'x_mm': 1, 'y_mm': 2, 'value': 3.3}]})
print(reply['data']['analysis_result']['fields']['visualization']['scalar_fields']['voltage_v'][0]['value'])
"""
        with patch.dict("os.environ", {"SPIKE_EXTENSION_PATH": str(examples)}):
            result = run_python_script({"python_executable": engine_interpreter(), "code": code,
                                        "design": DESIGN,
                                        "_trusted_extension_ids": ["org.example.field-data-adapter"]})
        self.assertEqual(result["status"], "completed", result.get("stderr"))
        self.assertIn("3.3", result["stdout"])
        self.assertEqual(result["published_result"]["provenance"]["script_upstream_extension_id"],
                         "org.example.field-data-adapter")

    def test_explicit_interpreter_must_be_an_existing_absolute_file(self):
        with self.assertRaisesRegex(ValueError, "absolute path"):
            run_python_script({"python_executable": "python", "code": "pass"})
        with self.assertRaisesRegex(ValueError, "absolute path"):
            run_python_script({"python_executable": str(Path.cwd() / "missing-python"), "code": "pass"})


if __name__ == "__main__":
    unittest.main()
