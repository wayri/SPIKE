# SPDX-License-Identifier: Apache-2.0
"""Core toolbar names, command routing and split-editor tool regression."""
import os
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1','opt-in native wx')
class CoreToolbarTests(unittest.TestCase):
    def test_readable_labels_availability_and_split_tool_actions(self):
        import wx
        from spikes_studio.desktop import Studio
        app=wx.GetApp() or wx.App(False);frame=Studio()
        try:
            frame.Show();wx.Yield();buttons={command:control for control,command in frame.command_controls}
            self.assertEqual(len(buttons),9)
            self.assertTrue(all(control.GetLabel() for control in buttons.values()))
            frame.context_tools()
            self.assertFalse(buttons['edit.rotate'].IsEnabled())
            self.assertFalse(buttons['edit.duplicate'].IsEnabled())
            self.assertIn('Select',buttons['edit.rotate'].GetToolTipText())
            part=frame.doc.data['components'][1];frame.canvas.selected={part['id']};frame.refresh_inspector();frame.context_tools()
            self.assertTrue(buttons['edit.rotate'].IsEnabled())
            self.assertTrue(buttons['edit.duplicate'].IsEnabled())
            buttons['edit.rotate'].activate()
            self.assertEqual(frame.doc.data['components'][1]['rotation'],90)
            frame.set_split('side_by_side');buttons['edit.wire'].activate()
            self.assertTrue(frame.canvas.wire_mode)
            self.assertTrue(buttons['edit.wire'].GetValue())
            self.assertEqual(frame.book.GetSelection(),1)
            buttons['probe.voltage'].activate()
            self.assertFalse(frame.canvas.wire_mode)
            self.assertEqual(frame.canvas.probe_mode,'voltage')
            self.assertEqual(frame.book.GetSelection(),1)
            buttons['edit.box_select'].activate()
            self.assertIsNone(frame.canvas.probe_mode)
            buttons['view.component_catalog'].activate()
            self.assertTrue(frame.tool_windows.entries[11][0].IsShown())
        finally:frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()
