# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import tempfile
import unittest
from pathlib import Path
from python.core.board_parser import KicadParser


class RoundrectSourceTests(unittest.TestCase):
    def parse(self, parameter):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "roundrect.kicad_pcb"
            path.write_text('(kicad_pcb (version 20260101) (layers (0 "F.Cu" signal)) '
                '(net 1 "N") (footprint "fixture" (layer "F.Cu") '
                '(property "Reference" "U1") (pad "1" smd roundrect (at 1 2 30) '
                '(size 2 1) (layers "F.Cu") (net 1 "N") ' + parameter + ')))', encoding="utf-8")
            return KicadParser(path)

    def test_ratio_and_chamfer_are_retained(self):
        parser = self.parse('(roundrect_rratio 0.25) (chamfer_ratio 0.1) (chamfer top_left)')
        self.assertEqual(parser.pads[0]["roundrect_rratio"], .25)
        self.assertEqual(parser.pads[0]["chamfer_ratio"], .1)
        self.assertEqual(parser.pads[0]["chamfer"], ["top_left"])

    def test_missing_ratio_is_not_invented(self):
        self.assertNotIn("roundrect_rratio", self.parse("").pads[0])

    def test_bad_ratio_does_not_drop_pad(self):
        for value in ("nan", "-0.1", "2", "bad"):
            parser = self.parse(f'(roundrect_rratio {value})')
            self.assertEqual(len(parser.pads), 1)
            self.assertIsNone(parser.pads[0]["roundrect_rratio"])
            self.assertTrue(any("invalid roundrect_rratio" in message for message in parser.diagnostics))
