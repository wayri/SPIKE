"""End-to-end worker API coverage for a third-party analysis adapter."""

import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.automation import SpikeAutomation
from python.spike_core.extensions import ExtensionRegistry


ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "extension_sdk" / "examples"


class ExtensionAdapterExampleTest(unittest.TestCase):
    def test_discover_trust_invoke_and_admit_external_field(self):
        registry = ExtensionRegistry()
        discovered = registry.discover([EXAMPLES])
        self.assertEqual(discovered[0]["status"], "loaded")
        self.assertFalse(discovered[0]["trusted"])
        from python.spike_core import service

        with patch.object(service, "_extension_registry", registry):
            automation = SpikeAutomation()
            self.assertFalse(automation.extension_catalog()["extensions"][0]["trusted"])
            automation.call("trust_extension", {"extension_id": "org.example.field-data-adapter"})
            design = {
                "contract": "spike/v1", "design_id": "example-board", "name": "Example board",
                "source_format": "example", "units": "mm", "layers": [], "nets": [],
                "tracks": [], "vias": [], "pads": [], "zones": [], "components": [],
                "stackup": [], "issues": [], "metadata": {},
            }
            envelope = automation.invoke_extension(
                "org.example.field-data-adapter", "import-voltage-field",
                design=design, parameters={"samples": [{"x_mm": 1, "y_mm": 2, "value": 3.3}]},
            )
            admitted = envelope["data"]["analysis_result"]
            self.assertEqual(admitted["provenance"]["extension_id"], "org.example.field-data-adapter")
            self.assertEqual(admitted["fields"]["visualization"]["scalar_fields"]["voltage_v"][0]["value"], 3.3)
            self.assertEqual(admitted["model_status"], "unvalidated")


if __name__ == "__main__":
    unittest.main()
