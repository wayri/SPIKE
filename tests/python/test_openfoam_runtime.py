from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from python.spike_core.openfoam_runtime import detect_openfoam_runtime


class OpenFoamRuntimeTests(unittest.TestCase):
    def setUp(self):
        detect_openfoam_runtime.cache_clear()

    def tearDown(self):
        detect_openfoam_runtime.cache_clear()

    def test_wsl_probe_uses_a_fixed_no_shell_command(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="2606\n", stderr="")
        with patch("python.spike_core.openfoam_runtime._native_runtime", return_value=None), patch(
            "python.spike_core.openfoam_runtime.sys.platform", "win32"
        ), patch(
            "python.spike_core.openfoam_runtime.shutil.which", return_value=r"C:\\Windows\\System32\\wsl.exe"
        ), patch(
            "python.spike_core.openfoam_runtime.subprocess.run", return_value=completed
        ) as spawned:
            runtime = detect_openfoam_runtime()

        self.assertEqual(runtime["transport"], "wsl_process")
        self.assertEqual(runtime["version"], "2606")
        self.assertEqual(runtime["executable"], "wsl://Ubuntu/usr/bin/openfoam2606")
        self.assertEqual(spawned.call_args.args[0][-2:], ["/usr/bin/openfoam2606", "-show-api"])
        self.assertFalse(spawned.call_args.kwargs["shell"])
        self.assertEqual(spawned.call_args.kwargs["timeout"], 12)

    def test_invalid_wsl_version_is_not_reported_as_available(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="unexpected\n", stderr="")
        with patch("python.spike_core.openfoam_runtime._native_runtime", return_value=None), patch(
            "python.spike_core.openfoam_runtime.sys.platform", "win32"
        ), patch(
            "python.spike_core.openfoam_runtime.shutil.which", return_value=r"C:\\Windows\\System32\\wsl.exe"
        ), patch("python.spike_core.openfoam_runtime.subprocess.run", return_value=completed):
            runtime = detect_openfoam_runtime()

        self.assertFalse(runtime["available"])
        self.assertEqual(runtime["transport"], "none")
