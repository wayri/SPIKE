# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from spikes_studio.document import Document, RC_DECK
from spikes_studio.schematic_layout import startup_layout, source_routes
from spikes_studio.interchange import import_text
from spikes_studio.kicad_import import import_schematic

NETLIST='''(export (version "E")
 (components (comp (ref "R1") (value "1k")) (comp (ref "C1") (value "1u")))
 (nets (net (code "1") (name "OUT") (node (ref "R1") (pin "2")) (node (ref "C1") (pin "1")))
       (net (code "2") (name "IN") (node (ref "R1") (pin "1")))
       (net (code "3") (name "GND") (node (ref "C1") (pin "2")))))'''


class WorkbenchImportTests(unittest.TestCase):
    def test_source_routes_are_connected_and_leave_circuit_unchanged(self):
        doc=Document.from_netlist(RC_DECK);before=doc.data['source'];startup_layout(doc)
        self.assertEqual(doc.data['source'],before);self.assertEqual(len(doc.data['wires']),3)
        parts={p['id']:p for p in doc.data['components']}
        for wire in doc.data['wires']:
            self.assertEqual(parts[wire['a'][0]]['nodes'][wire['a'][1]],
                             parts[wire['b'][0]]['nodes'][wire['b'][1]])
        previous=list(doc.data['wires']);source_routes(doc);self.assertEqual(doc.data['wires'],previous)

    def test_kicad_netlist_uses_actual_pin_to_net_mapping(self):
        report=import_text(NETLIST);self.assertEqual(report.format,'kicad_netlist')
        parts={p['ref']:p for p in report.document.data['components']}
        self.assertEqual(parts['R1']['nodes'],['k2','k1'])
        self.assertEqual(parts['C1']['nodes'],['k1','0'])
        self.assertEqual(len(report.document.data['wires']),1)
        self.assertNotIn('V1',report.document.data['source'])

    def test_unsupported_ics_do_not_create_partial_circuit(self):
        report=import_text(NETLIST.replace('"R1"','"U1"'))
        self.assertIsNone(report.document);self.assertIn('U1',report.warnings[0])

    def test_duplicate_net_membership_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'multiple nets'):
            import_text(NETLIST.replace('(ref "R1") (pin "1")','(ref "R1") (pin "2")'))

    def test_native_export_uses_file_context_and_preserves_positions(self):
        schematic='''(kicad_sch (symbol (property "Reference" "R1") (property "Value" "1k") (at 20 30 0))
        (symbol (property "Reference" "C1") (property "Value" "1u") (at 60 40 0)))'''
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.kicad_sch';path.write_text(schematic)
            def export(arguments, **options):
                Path(arguments[arguments.index('--output')+1]).write_text(
                    NETLIST if arguments[arguments.index('--format')+1]=='kicadsexpr' else RC_DECK)
                self.assertEqual(options['cwd'],str(path.parent));self.assertEqual(options['timeout'],30)
                return subprocess.CompletedProcess(arguments,0,'','')
            with patch('spikes_studio.kicad_import.subprocess.run',side_effect=export):
                report=import_schematic(path,cli='kicad-cli')
            self.assertIsNotNone(report.document)
            parts={p['ref']:p for p in report.document.data['components']}
            self.assertLess(parts['R1']['x'],parts['C1']['x'])
            self.assertTrue(report.document.data['metadata']['kicad_import']['warnings'])

    @unittest.skipUnless(os.environ.get('SPIKES_TEST_KICAD_CLI'),'Native KiCad CLI not configured')
    def test_actual_kicad_export_and_hierarchical_node_normalization(self):
        path=Path(__file__).resolve().parents[4]/'examples/spikes/native_import_resistor.kicad_sch'
        report=import_schematic(path,cli=os.environ['SPIKES_TEST_KICAD_CLI'])
        self.assertIsNotNone(report.document,report.warnings)
        part=report.document.data['components'][0]
        self.assertEqual(part['ref'],'R1');self.assertEqual(part['nodes'][1],'0')
        self.assertTrue(part['nodes'][0].startswith('kicad_net_'))

    @unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1','opt-in native wx test')
    def test_native_header_switches_workspaces_and_hides_unrelated_palette(self):
        import wx
        from spikes_studio.desktop import Studio
        app=wx.GetApp() or wx.App(False);frame=Studio()
        try:
            frame.Show();wx.Yield();frame.book.SetSelection(1)
            self.assertFalse(frame.workspace.IsSplit())
            self.assertFalse(frame.workflow_bar.tools.IsShown())
            frame.book.SetSelection(0)
            self.assertTrue(frame.workspace.IsSplit())
            self.assertTrue(frame.workflow_bar.tools.IsShown())
            for ident in frame.run_bar.buttons:self.assertIsNotNone(frame.run_bar.FindById(ident))
        finally:frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()


if __name__=='__main__':unittest.main()
