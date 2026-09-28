# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import tempfile
import unittest

from scripts.recover_kicad_zone_fill import compare_summary, summarize_import


BOARD = """(kicad_pcb (version 20240108) (generator pcbnew)
 (general (thickness 1.6))
 (layers (0 \"F.Cu\" signal) (31 \"B.Cu\" signal))
 (net 0 \"\") (net 1 \"GND\")
 (zone (net 1) (net_name \"GND\") (layer \"F.Cu\") (uuid zone-a)
   (hatch edge 0.5) (connect_pads (clearance 0.5))
   (min_thickness 0.25) (fill yes (thermal_gap 0.3) (thermal_bridge_width 0.3))
   (polygon (pts (xy 0 0) (xy 10 0) (xy 10 10) (xy 0 10)))
   (filled_polygon (layer \"F.Cu\") (pts (xy 0 0) (xy 10 0) (xy 10 10) (xy 0 10)))))"""


class ZoneFillRecoveryTests(unittest.TestCase):
    def test_spi_ke_reimport_summary_preserves_zone_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            board = Path(temporary) / "fixture.kicad_pcb"
            board.write_text(BOARD, encoding="utf-8")
            source = summarize_import(board)
            candidate = summarize_import(board)
        comparison = compare_summary(source, candidate)
        self.assertEqual(source["source_zone_ids"], ["zone-a"])
        self.assertEqual(source["filled_component_records"], 1)
        self.assertTrue(comparison["source_zone_ids_preserved"])
        self.assertEqual(comparison["filled_component_records_delta"], 0)

    def test_comparison_detects_lost_zone_identity_and_refilled_copper(self):
        source = {"source_zone_ids": ["zone-a"], "source_zone_id_counts": {"zone-a": 1},
                  "filled_component_records": 0, "outline_intent_records": 1}
        candidate = {"source_zone_ids": ["zone-a", "zone-b"],
                     "source_zone_id_counts": {"zone-a": 1, "zone-b": 1},
                     "filled_component_records": 2, "outline_intent_records": 0}
        comparison = compare_summary(source, candidate)
        self.assertFalse(comparison["source_zone_ids_preserved"])
        self.assertEqual(comparison["source_zone_ids_added"], ["zone-b"])
        self.assertEqual(comparison["filled_component_records_delta"], 2)
        self.assertEqual(comparison["outline_intent_records_delta"], -1)


if __name__ == "__main__":
    unittest.main()
