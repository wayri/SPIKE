# SPDX-License-Identifier: Apache-2.0
"""Curved-source approximation must remain visible in import evidence."""
from pathlib import Path
import unittest
import tempfile

from python.spike_core.kicad_importer import import_kicad_design

ROOT = Path(__file__).resolve().parents[2]


class ArcImportDiagnosticsTests(unittest.TestCase):
    def test_arc_chords_are_reported_with_native_source_lineage(self):
        design = import_kicad_design(str(ROOT / 'benchmarks/parity-import/geometry.kicad_pcb'))
        self.assertIn('KICAD_ARC_LINEARIZED', [issue.code for issue in design.issues])
        diagnostics = [d for d in design.metadata['parser_diagnostics'] if d.get('code') == 'KICAD_ARC_LINEARIZED']
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0]['source_id'], '77777777-7777-4777-8777-777777777777')
        self.assertEqual(diagnostics[0]['segment_count'], 8)
        self.assertEqual(diagnostics[0]['severity'], 'warning')

    def test_straight_fixture_has_no_curved_source_warning(self):
        design = import_kicad_design(str(ROOT / 'benchmarks/parity-import/coupon.kicad_pcb'))
        self.assertNotIn('KICAD_ARC_LINEARIZED', [issue.code for issue in design.issues])

    def test_anonymous_arc_approximation_is_also_reported(self):
        source = (ROOT / 'benchmarks/parity-import/geometry.kicad_pcb').read_text()
        source = source.replace('(uuid "77777777-7777-4777-8777-777777777777")', '')
        with tempfile.TemporaryDirectory(dir=ROOT / 'build/parity-test-temp') as directory:
            board = Path(directory) / 'anonymous.kicad_pcb'
            board.write_text(source)
            design = import_kicad_design(str(board))
        diagnostics = [d for d in design.metadata['parser_diagnostics'] if d.get('code') == 'KICAD_ARC_LINEARIZED']
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0]['segment_count'], 8)
