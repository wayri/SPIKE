# SPDX-License-Identifier: Apache-2.0
"""Native wx coverage for preview, rotation, repeat placement and Escape."""
import gc
import os
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'studio/python'))


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX') == '1', 'opt-in native wx')
class SchematicClipboardUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import wx
        cls.app = wx.GetApp() or wx.App(False)
        cls.app.SetExitOnFrameDelete(False)

    def test_process_app_survives_predecessor_window_for_clipboard(self):
        import wx
        from spikes_studio.desktop import Studio

        predecessor = Studio()
        # Reopen the same sheet in the successor window. Cross-document fragment
        # paste is deliberately rejected; this test checks clipboard ownership.
        from spikes_studio.document import Document
        reopened=Document(predecessor.doc.data)
        predecessor.canvas.selected = {predecessor.doc.data['components'][1]['id']}
        # Copy is context-sensitive. A preceding test can leave a text editor
        # focused; explicitly focus the intended canvas before using Ctrl+C's
        # actual command path instead of reusing stale system clipboard data.
        predecessor.Show();wx.Yield();predecessor.canvas.SetFocus();wx.Yield()
        self.assertIs(wx.Window.FindFocus(),predecessor.canvas)
        predecessor.copy_circuit()
        import json
        from spikes_studio.clipboard_text import read_text
        self.assertEqual(json.loads(read_text(predecessor))['source_document_id'],reopened.data['id'],
                         'Copy must write the intended source-sheet payload')
        predecessor.timer.Stop();predecessor.autosave_timer.Stop();predecessor.Destroy();wx.Yield()
        expected_app = wx.GetApp()
        self.assertIsNotNone(expected_app)
        gc.collect()
        self.assertIs(wx.GetApp(), expected_app)

        frame = Studio()
        try:
            frame.doc=reopened;frame.refresh_document(force_source=True)
            frame.Show();wx.Yield()
            frame.canvas.SetFocus();wx.Yield()
            self.assertIs(wx.Window.FindFocus(),frame.canvas)
            self.assertEqual(json.loads(read_text(frame))['source_document_id'],reopened.data['id'],
                             'System clipboard changed while constructing the successor window')
            frame.paste()
            self.assertIsNotNone(frame.canvas.fragment_plan)
        finally:
            frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()

    def test_clipboard_preview_escape_rotate_repeat_and_undo(self):
        import wx
        from spikes_studio.desktop import Studio

        app = wx.GetApp() or wx.App(False)
        frame = Studio()
        try:
            frame.Show();wx.Yield()
            selected = {part['id'] for part in frame.doc.data['components'][1:]}
            frame.canvas.selected = selected;frame.refresh_inspector();frame.context_tools();frame.canvas.SetFocus()
            before = deepcopy(frame.doc.data);component_count = len(frame.doc.data['components'])
            undo_count = len(frame.doc.undo_stack)

            # Exercise the actual system clipboard path used by Ctrl+C/Ctrl+V.
            frame.copy_circuit();frame.paste()
            self.assertIsNotNone(frame.canvas.fragment_plan)
            self.assertEqual(len(frame.doc.data['components']), component_count)
            frame.rotate_fragment_placement()
            self.assertEqual(frame.canvas.fragment_plan['quarter_turns'], 1)
            frame.canvas.Refresh();frame.canvas.Update();wx.Yield()
            preview_ids={part['id'] for part in frame.canvas.fragment_plan['components']}
            self.assertTrue(preview_ids.isdisjoint(part['id'] for _,part in frame.canvas.hits))
            self.assertTrue(preview_ids.isdisjoint(ident for _,ident,_ in frame.canvas.wire_pins))
            frame.canvas.placement_key(SimpleNamespace(GetKeyCode=lambda: wx.WXK_ESCAPE))
            self.assertIsNone(frame.canvas.fragment_plan)
            self.assertEqual(len(frame.doc.undo_stack), undo_count)
            self.assertEqual(frame.doc.data, before)

            frame.duplicate_selection()
            frame.commit_fragment_placement((700, 420))
            self.assertEqual(len(frame.doc.data['components']), component_count + len(selected))
            self.assertIsNotNone(frame.canvas.fragment_plan)
            frame.commit_fragment_placement((950, 420))
            self.assertEqual(len(frame.doc.data['components']), component_count + 2 * len(selected))
            frame.canvas.placement_key(SimpleNamespace(GetKeyCode=lambda: wx.WXK_ESCAPE))
            self.assertIsNone(frame.canvas.fragment_plan)
            frame.doc.undo();frame.doc.undo();frame.refresh_document()
            self.assertEqual(len(frame.doc.data['components']), component_count)
        finally:
            frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()


if __name__ == '__main__':
    unittest.main()
