# SPDX-License-Identifier: Apache-2.0
"""Actual wx controls and schematic transactions for board pinout blocks."""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'standalone/spikes_project/studio/python'))


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX') == '1', 'requires real wx runtime')
class ControllerBoardUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import wx
        cls.app = wx.GetApp() or wx.App(False)

    def setUp(self):
        from spikes_studio.desktop import Studio
        from spikes_studio.controller_board_browser import ControllerBoardDialog
        self.frame = Studio(None)
        self.dialog = ControllerBoardDialog(self.frame)

    def tearDown(self):
        self.dialog.Destroy()
        self.frame.canvas.board_tools.cancel()
        self.frame.Destroy()

    def test_catalog_search_and_all_pin_controls(self):
        self.assertEqual(len(self.dialog.catalog), 17)
        self.assertEqual(self.dialog.grid.GetNumberRows(), len(self.dialog.draft['board']['pins']))
        for row, pin in enumerate(self.dialog.rows):
            self.assertEqual(self.dialog.grid.GetCellValue(row, 1), pin['label'])
            self.assertEqual(self.dialog.grid.GetCellValue(row, 2), 'NC')
            if pin['role'] not in ('gpio', 'analog'):
                self.assertTrue(self.dialog.grid.IsReadOnly(row, 2))
        self.dialog.search.ChangeValue('arduno')
        self.dialog.filter()
        self.assertTrue(any('Arduino' in board['name'] for board in self.dialog.visible))

    def test_placement_persists_bindings_labels_and_undo(self):
        from spikes_studio.document import Document
        draft = self.dialog.configuration()
        pin = next(pin for pin in draft['board']['pins'] if 'analog_input' in pin['capabilities'])
        draft['bindings'][pin['id']].update(mode='AI', node='out', reference='0')
        canvas = self.frame.canvas
        source = self.frame.doc.data['source']
        canvas.board_tools.start(draft)
        canvas.board_tools.down(SimpleNamespace(GetPosition=lambda: canvas.point(100, 100)))
        block = self.frame.doc.data['controller_boards'][0]
        self.assertEqual(block['bindings'][pin['id']]['mode'], 'AI')
        self.assertEqual(self.frame.doc.data['source'], source)
        import wx
        bitmap = wx.Bitmap(1200, 1000)
        dc = wx.MemoryDC(bitmap)
        canvas.board_tools.draw(dc, self.frame.palette)
        dc.SelectObject(wx.NullBitmap)
        self.assertEqual(len(canvas.board_tools.hits), len(block['board']['pins']))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'board.spksch'
            self.frame.doc.save(path)
            self.assertEqual(Document.load(path).data['controller_boards'], [block])
        self.frame.doc.undo()
        self.assertEqual(self.frame.doc.data['controller_boards'], [])

    def test_sampled_adapter_is_explicit_and_untrusted(self):
        from spikes_studio.controller_board_blocks import controller_config
        from spikes_studio.part_properties import parse
        draft = self.dialog.configuration()
        ai = next(pin for pin in draft['board']['pins'] if 'analog_input' in pin['capabilities'])
        do = next(pin for pin in draft['board']['pins'] if 'digital_io' in pin['capabilities'] and pin != ai)
        draft['bindings'][ai['id']].update(mode='AI', node='out', reference='0')
        draft['bindings'][do['id']].update(mode='DO', source='V1')
        config = controller_config(draft, parse(self.frame.doc.data['source']))
        self.frame.controller_panel.load_block(config)
        self.assertFalse(self.frame.controller_panel.trust.GetValue())
        self.assertEqual(self.frame.controller_panel.config()['board_block_id'], draft['id'])
        self.assertEqual(config['language'], 'C')

    def test_board_drag_is_one_undoable_transaction(self):
        canvas = self.frame.canvas
        canvas.board_tools.start(self.dialog.configuration())
        canvas.board_tools.down(SimpleNamespace(GetPosition=lambda: canvas.point(100, 100)))
        canvas.board_tools.down(SimpleNamespace(GetPosition=lambda: canvas.point(150, 120)))
        canvas.board_tools.motion(SimpleNamespace(GetPosition=lambda: canvas.point(190, 150), LeftIsDown=lambda: True))
        self.assertEqual(self.frame.doc.data['controller_boards'][0]['x'], 100)
        canvas.board_tools.up(SimpleNamespace())
        self.assertEqual(self.frame.doc.data['controller_boards'][0]['x'], 140)
        self.assertEqual(self.frame.doc.data['controller_boards'][0]['y'], 130)
        self.frame.doc.undo()
        self.assertEqual(self.frame.doc.data['controller_boards'][0]['x'], 100)


if __name__ == '__main__':
    unittest.main()
