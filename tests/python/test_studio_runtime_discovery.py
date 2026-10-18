# SPDX-License-Identifier: Apache-2.0
"""Inert launch discovery and strict worker dispatch regression checks."""
import unittest
from pathlib import Path
from unittest.mock import patch
from python.spike_core.studio_bridge import studio_runtime_capabilities, handle_studio_bridge_request

class StudioRuntimeDiscoveryTests(unittest.TestCase):
    def test_source_runtime_has_prepare_but_needs_gui(self):
        with patch("python.spike_core.studio_bridge.importlib.util.find_spec", return_value=None):
            value = studio_runtime_capabilities()
        self.assertEqual(value["contract"], "spike/studio-runtime/v1")
        self.assertTrue(value["can_prepare"])
        self.assertFalse(value["can_launch"])
        self.assertIn("wxPython", value["reason"])
        self.assertFalse(value["live_sync"])

    def test_frozen_worker_never_claims_source_launch(self):
        with patch("python.spike_core.studio_bridge.sys.frozen", True, create=True), patch("python.spike_core.studio_bridge.importlib.util.find_spec", return_value=object()):
            value = studio_runtime_capabilities()
        self.assertFalse(value["can_launch"])
        self.assertIn("worker package", value["reason"])

    def test_discovery_is_parameterless_and_does_not_launch(self):
        with patch("python.spike_core.studio_bridge.subprocess.Popen") as spawn:
            response = handle_studio_bridge_request("studio_runtime_capabilities", {}, Path.cwd())
            self.assertTrue(response["ok"])
            rejected = handle_studio_bridge_request("studio_runtime_capabilities", {"executable":"anything"}, Path.cwd())
            self.assertFalse(rejected["ok"])
            spawn.assert_not_called()
        self.assertIsNone(handle_studio_bridge_request("unrelated", {}, Path.cwd()))

if __name__ == "__main__":
    unittest.main()
