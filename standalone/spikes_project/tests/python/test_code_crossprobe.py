# SPDX-License-Identifier: Apache-2.0
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "python"))

from spikes_studio.code_crossprobe import MAX_TEXT, resolve_references


class CodeCrossprobeTests(unittest.TestCase):
    def setUp(self):
        self.document = {"components": [
            {"id": "source-id", "ref": "Vdrive", "nodes": ["Gate", "0"]},
            {"id": "load-id", "ref": "Rload", "nodes": ["Gate", "Return"]},
        ]}
        self.controller = {"pins": [
            {"name": "sense", "mode": "AI", "node": "Gate", "reference": "Return"},
            {"name": "enable", "mode": "DI", "node": "Enable", "reference": "0"},
            {"name": "drive", "mode": "DO", "source": "Vdrive"},
        ]}

    def test_exact_case_insensitive_component_and_net_tokens(self):
        result = resolve_references("vDrIvE gate RLOAD", self.document, self.controller)
        self.assertEqual(result["nets"], {"Gate"})
        self.assertEqual(result["components"], {"source-id", "load-id"})
        self.assertEqual(result["pins"], {"sense", "drive"})

    def test_does_not_match_substrings(self):
        result = resolve_references("myGate Rload_extra senseMore", self.document, self.controller)
        self.assertEqual(result, {"nets": set(), "components": set(), "pins": set()})

    def test_pin_names_and_ordered_array_access(self):
        result = resolve_references("SENSE inputs[ 1 ] outputs[0]", self.document, self.controller)
        self.assertEqual(result["pins"], {"sense", "enable", "drive"})
        self.assertEqual(result['nets'],{'Gate','Return','0'})
        self.assertIn('source-id',result['components'])

    def test_input_endpoints_and_driving_source_endpoints_link_pins(self):
        self.assertEqual(resolve_references("Return", self.document, self.controller)["pins"], {"sense"})
        self.assertEqual(resolve_references("0", self.document, self.controller)["pins"], {"enable", "drive"})

    def test_document_controller_default_and_no_mutation(self):
        document = {**self.document, "controller_setup": self.controller}
        before = repr(document)
        self.assertEqual(resolve_references("outputs[0]", document)["pins"], {"drive"})
        self.assertEqual(repr(document), before)

    def test_non_text_and_bounded_tail_are_safe(self):
        self.assertEqual(resolve_references(None, self.document), {"nets": set(), "components": set(), "pins": set()})
        text = "x" * MAX_TEXT + " Gate"
        self.assertEqual(resolve_references(text, self.document, self.controller)["nets"], set())


if __name__ == "__main__":
    unittest.main()
