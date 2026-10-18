# SPDX-License-Identifier: Apache-2.0
"""Portable, fail-closed admission for the local assembly airflow runtime."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core import assembly_airflow_runtime as airflow_runtime


class AssemblyAirflowRuntimeTest(unittest.TestCase):
    def test_missing_or_changed_development_interpreter_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {'LOCALAPPDATA': directory}
        ):
            with self.assertRaisesRegex(ValueError, 'pinned development Python 3.11 unavailable'):
                airflow_runtime._admitted_development_python311()
            executable = airflow_runtime._development_python311_path()
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b'changed interpreter')
            with patch.object(airflow_runtime.runtime, '_sha', return_value='0' * 64):
                with self.assertRaisesRegex(ValueError, 'pinned development Python 3.11 unavailable'):
                    airflow_runtime._admitted_development_python311()

    def test_same_pinned_interpreter_is_admitted_under_any_local_app_data(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {'LOCALAPPDATA': directory}
        ):
            executable = Path(directory)/'Programs'/'Python'/'Python311'/'python.exe'
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b'pinned interpreter fixture')
            with patch.object(
                airflow_runtime.runtime, '_sha',
                return_value=airflow_runtime.DEVELOPMENT_PYTHON_SHA256,
            ):
                self.assertEqual(airflow_runtime._admitted_development_python311(), executable)

    def test_home_fallback_uses_standard_windows_location(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(
            airflow_runtime.Path, 'home', return_value=Path('D:/portable-user')
        ):
            self.assertEqual(
                airflow_runtime._development_python311_path(),
                Path('D:/portable-user/AppData/Local/Programs/Python/Python311/python.exe'),
            )


if __name__ == '__main__':
    unittest.main()
