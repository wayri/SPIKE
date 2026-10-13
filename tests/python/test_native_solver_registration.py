# SPDX-License-Identifier: Apache-2.0
"""Native workbenches must survive host manifest and process boundaries."""
import json
from pathlib import Path
import unittest
from python.spike_core.extensions import ExtensionManifest, ProcessExtension

class NativeSolverRegistrationTests(unittest.TestCase):
    def test_registered_routes_and_host_preflight(self):
        repository = Path(__file__).resolve().parents[2]
        cases = [("palace_suite", "palace-discover", {}, {"em", "pi", "si"}),
                 ("xyce_suite", "xyce-circuit", {"operation": "preflight"}, {"pi", "si"})]
        for directory, contribution, parameters, expected in cases:
            with self.subTest(directory=directory):
                root = repository / "extensions" / directory
                manifest = ExtensionManifest.from_dict(json.loads((root / "spike-extension.json").read_text(encoding="utf-8")))
                routes = [route for items in manifest.contributes.values() for item in items for route in item.get("workspace_routes", [])]
                self.assertEqual({route["workspace"] for route in routes}, expected)
                response = ProcessExtension(manifest, root, True).invoke(contribution, {"parameters": parameters})
                self.assertEqual(response["contract"], "spike/extension-result/v1")
                self.assertFalse(response["data"]["solved"])
                self.assertIn("runtime", response["data"])

if __name__ == "__main__":
    unittest.main()
