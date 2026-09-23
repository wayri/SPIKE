# SPDX-License-Identifier: MIT
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import patch

import python.spikes as spikes
from python.spikes.cli import CLI_VERSION
from python.spikes.library import LIBRARY_VERSION
from python.spikes.version import ENGINE_VERSION
from scripts import build_spikes_engine_release


ROOT = Path(__file__).resolve().parents[2]


class SpikesEngineVersionTests(unittest.TestCase):
    def test_engine_runtime_surfaces_share_beta_version(self) -> None:
        self.assertEqual(ENGINE_VERSION, "0.3.0-beta.1")
        self.assertEqual(spikes.__version__, ENGINE_VERSION)
        self.assertEqual(CLI_VERSION, ENGINE_VERSION)
        self.assertEqual(LIBRARY_VERSION, ENGINE_VERSION)

    def test_cli_prints_engine_version(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "python.spikes", "--version"],
            cwd=ROOT, capture_output=True, text=True, shell=False, check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout.strip(), f"SPIKES {ENGINE_VERSION}")

    def test_native_console_version_is_build_bound_to_engine_version(self) -> None:
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        project = re.search(r"project\(SPIKE VERSION ([0-9.]+)", cmake)
        prerelease = re.search(
            r'set\(SPIKES_ENGINE_PRERELEASE "([^"]+)"', cmake,
        )
        self.assertIsNotNone(project)
        self.assertIsNotNone(prerelease)
        self.assertEqual(
            f"{project.group(1)}-{prerelease.group(1)}", ENGINE_VERSION,
        )
        console = (ROOT / "src/spikes/console_main.cpp").read_text(encoding="utf-8")
        self.assertIn('"spikes_console " SPIKES_ENGINE_VERSION', console)
        self.assertNotIn("0.3.0-alpha", console)

    def test_engine_release_builder_defaults_to_engine_version(self) -> None:
        captured: dict[str, object] = {}

        def fake_build(**kwargs):
            captured.update(kwargs)
            return Path("package"), Path("archive"), {}

        with patch.object(build_spikes_engine_release, "build_engine_release", fake_build), patch.object(
            sys, "argv", ["build_spikes_engine_release.py", "--library", "spikes_c_api.dll"],
        ), patch.object(Path, "mkdir"), patch.object(Path, "write_text"), patch("builtins.print"):
            self.assertEqual(build_spikes_engine_release.main(), 0)
        self.assertEqual(captured["version"], ENGINE_VERSION)


if __name__ == "__main__":
    unittest.main()
