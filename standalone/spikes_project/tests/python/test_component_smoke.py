# SPDX-License-Identifier: Apache-2.0
"""Source checks for the frozen component workflow self-test."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "studio/python"))
TEST_TEMP_ROOT = Path(__file__).resolve().parents[4] / ".tmp" / "component-smoke-tests"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

from spikes_studio import component_smoke as smoke
from spikes_studio.component_package import behavior_digest, load
from spikes_studio.ide import find_tool


NATIVE_LIBRARY = (os.environ.get("SPIKES_TEST_NATIVE_LIBRARY") or
                  os.environ.get("SPIKES_TEST_LIBRARY"))


class ComponentSmokeTests(unittest.TestCase):
    def test_owned_fixtures_roundtrip_as_inert_packages(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            root = Path(directory)
            for name, value in (("spice", smoke._spice_component()),
                                ("cpp", smoke._cpp_component()),
                                ("verilog", smoke._verilog_component())):
                before = behavior_digest(value)
                loaded, installed, count = smoke._roundtrip(value, root / name)
                self.assertEqual(count, 1)
                self.assertEqual(load(installed), value)
                self.assertEqual(behavior_digest(loaded), before)
            self.assertEqual(
                [pin["name"] for pin in smoke._spice_component()["symbol"]["terminals"]],
                ["IN", "OUT", "REF"],
            )
            self.assertEqual(
                [pin["mode"] for pin in smoke._cpp_component()["symbol"]["terminals"]],
                ["AI", "AO"],
            )
            self.assertEqual(
                [pin["mode"] for pin in smoke._verilog_component()["symbol"]["terminals"]],
                ["DI", "DO"],
            )

    def test_isolated_environment_restores_process_paths(self):
        previous = os.environ.get("LOCALAPPDATA")
        previous_tempdir = tempfile.tempdir
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            root = Path(directory) / "runtime"
            with smoke._isolated_environment(root):
                self.assertEqual(Path(os.environ["LOCALAPPDATA"]), root / "local-app-data")
                self.assertEqual(Path(tempfile.gettempdir()), root / "temp")
                created = Path(tempfile.mkdtemp(prefix="probe-"))
                self.assertEqual(created.parent, root / "temp")
        self.assertEqual(os.environ.get("LOCALAPPDATA"), previous)
        self.assertEqual(tempfile.tempdir, previous_tempdir)

    def test_missing_native_and_toolchains_are_structured_failure_and_skips(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory, \
                patch("spikes_studio.component_smoke._discover_tools", return_value={
                    "clang++": None, "cl": None, "iverilog": None, "vvp": None,
                }):
            destination = Path(directory) / "result.json"
            exit_code = smoke.run(Path(directory) / "missing-native.dll", destination)
            report = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["contract"], smoke.CONTRACT)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["counts"],
                         {"passed": 0, "failed": 1, "skipped": 3, "total": 4})
        self.assertEqual(report["errors"][0]["case"],
                         "spice_package_pinmap_native_rc")
        self.assertIsNone(report["native"]["sha256"])
        self.assertEqual([case["id"] for case in report["cases"]], [
            "spice_package_pinmap_native_rc",
            "cpp_controller_compile_and_sample",
            "verilog_component_compile",
            "verilog_vvp_digital_simulation",
        ])

    @unittest.skipUnless(
        NATIVE_LIBRARY and Path(NATIVE_LIBRARY).is_file(),
        "set SPIKES_TEST_NATIVE_LIBRARY to run the real native component smoke",
    )
    def test_real_source_component_workflows(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            destination = Path(directory) / "component-self-test.json"
            exit_code = smoke.run(NATIVE_LIBRARY, destination)
            report = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 0, report["errors"])
        self.assertTrue(report["passed"])
        self.assertEqual(report["counts"]["failed"], 0)
        self.assertEqual(report["counts"]["total"], 4)
        self.assertIsNotNone(report["native"]["sha256"])
        by_id = {case["id"]: case for case in report["cases"]}
        self.assertEqual(by_id["spice_package_pinmap_native_rc"]["status"], "passed")
        if find_tool("clang++") or find_tool("cl"):
            self.assertEqual(by_id["cpp_controller_compile_and_sample"]["status"], "passed")
        if find_tool("iverilog"):
            self.assertEqual(by_id["verilog_component_compile"]["status"], "passed")
        if find_tool("iverilog") and find_tool("vvp"):
            self.assertEqual(by_id["verilog_vvp_digital_simulation"]["status"], "passed")


if __name__ == "__main__":
    unittest.main()
