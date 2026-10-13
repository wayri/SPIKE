# SPDX-License-Identifier: Apache-2.0
"""Mixed legacy/structured importer diagnostics preserve geometry and evidence."""
from pathlib import Path
import unittest
from unittest.mock import patch

from python.core.board_parser import KicadParser
from python.spike_core.kicad_importer import import_kicad_design

ROOT = Path(__file__).resolve().parents[2]


class DiagnosticCompatibilityTests(unittest.TestCase):
    def test_legacy_text_and_arc_record_coexist_without_losing_geometry(self):
        fixture = ROOT / 'benchmarks/parity-import/geometry.kicad_pcb'
        expected = import_kicad_design(str(fixture))
        original_parse = KicadParser.parse
        diagnostic = 'Legacy source outline diagnostic retained for review.'

        def mixed_parse(parser, *args, **kwargs):
            result = original_parse(parser, *args, **kwargs)
            parser.diagnostics.append(diagnostic)
            return result

        with patch.object(KicadParser, 'parse', mixed_parse):
            actual = import_kicad_design(str(fixture))
        self.assertEqual(actual.tracks, expected.tracks)
        self.assertEqual(actual.zones, expected.zones)
        self.assertEqual(actual.pads, expected.pads)
        self.assertIn(diagnostic, actual.metadata['parser_diagnostics'])
        self.assertIn('KICAD_ARC_LINEARIZED', [issue.code for issue in actual.issues])
        self.assertIn('IMPORT_OBJECT_DIAGNOSTICS', [issue.code for issue in actual.issues])


if __name__ == '__main__':
    unittest.main()
