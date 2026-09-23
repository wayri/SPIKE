# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yawar Badri
"""Regression: imported KiCad pad ownership is accepted by PI path validation."""

import unittest
from pathlib import Path

from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.service import handle


BOARD = Path(__file__).resolve().parents[2] / "examples/pi/reference_board/spike-pi-reference.kicad_pcb"


class ImportedPiPathTests(unittest.TestCase):
    def test_kicad_series_component_pads_validate_without_fixture_only_ref_field(self):
        design = import_kicad_design(str(BOARD)).to_dict()
        pads = design["pads"]

        def pad(net, x):
            matches = [item for item in pads if item["net_name"] == net and
                       tuple(item["at"]) == (float(x), 10.0)]
            self.assertEqual(len(matches), 1)
            return matches[0]

        before = pad("VIN", 20)
        after = pad("VLOAD", 22)
        self.assertEqual(before["component"], "R1")
        self.assertEqual(after["component"], "R1")
        self.assertNotIn("ref", before)
        path = {
            "contract": "spike/pi-path/v1", "id": "imported-r1",
            "source_terminal": {"net": "VIN", "pad_id": pad("VIN", 5)["id"]},
            "load_terminal": {"net": "VLOAD", "pad_id": pad("VLOAD", 40)["id"]},
            "segments": [{"id": "vin", "net": "VIN"}, {"id": "load", "net": "VLOAD"}],
            "transitions": [{"id": "r1", "component_ref": "R1", "from_segment_id": "vin",
                             "to_segment_id": "load", "input_pad_id": before["id"],
                             "output_pad_id": after["id"],
                             "model": {"primitive": "resistor", "connection_resistance_ohm": 0.1}}],
        }
        response = handle({"method": "validate_pi_path", "params": {
            "design": design, "path": path, "mode": "dc"}})
        self.assertTrue(response["ok"])
        self.assertTrue(response["result"]["can_execute"], response["result"]["issues"])
        self.assertAlmostEqual(response["result"]["interfaces"][0]["dc_resistance_ohm"], 0.1)


if __name__ == "__main__":
    unittest.main()
