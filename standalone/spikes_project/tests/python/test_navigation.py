# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import os
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.navigation import NavigationHistory


class HistoryTests(unittest.TestCase):
    def test_back_forward_new_branch_and_bound(self):
        history=NavigationHistory(limit=3)
        for index in range(4):history.visit(('workspace',index))
        self.assertEqual(len(history.entries),3)
        self.assertEqual(history.back(),('workspace',2))
        self.assertEqual(history.forward(),('workspace',3))
        history.back();history.visit(('tool',16))
        self.assertFalse(history.can_forward)
        history.visit(('tool',16));self.assertEqual(len(history.entries),3)
        self.assertEqual(history.back(),('workspace',2))

    def test_empty_history_cannot_move(self):
        history=NavigationHistory()
        self.assertIsNone(history.back());self.assertIsNone(history.forward())
        history.visit(('workspace',0));self.assertFalse(history.can_back)
        with self.assertRaises(ValueError):NavigationHistory(limit=0)
        with self.assertRaises(ValueError):history.visit(('workspace',True))


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1','opt-in native wx')
class NavigationWxTests(unittest.TestCase):
    def test_navigation_tabs_and_floating_tool_history_preserve_document(self):
        import wx
        from copy import deepcopy
        from spikes_studio.desktop import Studio
        app=wx.GetApp() or wx.App(False);frame=Studio()
        try:
            frame.Show();wx.Yield();bar=frame.workflow_bar;before=deepcopy(frame.doc.data)
            bar.views[13].activate();bar.views[2].activate()
            draft=frame.source.GetText()+'* uncommitted editor draft\n';frame.source.SetText(draft)
            bar.navigation_buttons['view.back'].activate();self.assertEqual(frame.book.GetSelection(),13)
            bar.navigation_buttons['view.forward'].activate();self.assertEqual(frame.book.GetSelection(),2)
            frame.execute_command('view.manufacturer_parts')
            self.assertEqual(bar.history.entries[-1],('tool',16))
            bar.navigation_buttons['view.back'].activate();self.assertEqual(frame.book.GetSelection(),2)
            bar.navigation_buttons['view.forward'].activate();self.assertTrue(frame.tool_windows.entries[16][0].IsShown())
            bar.navigation_buttons['view.home'].activate();self.assertEqual(frame.book.GetSelection(),0)
            frame.set_split('side_by_side');bar.home()
            self.assertFalse(frame.split_view);self.assertIs(frame.canvas.GetParent(),frame.schematic_host)
            frame.tool_windows.dock(16);self.assertIn(16,bar.views)
            frame.tool_windows.open(16);self.assertNotIn(16,bar.views)
            self.assertEqual(frame.doc.data,before)
            self.assertEqual(frame.source.GetText(),draft)
        finally:frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()
