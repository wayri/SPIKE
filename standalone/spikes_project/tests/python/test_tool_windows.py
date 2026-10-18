# SPDX-License-Identifier: Apache-2.0
"""Native lifecycle checks for the same stateful specialist page."""
import os
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1','opt-in native wx')
class ToolWindowTests(unittest.TestCase):
    def test_component_browser_direct_opener_floats_and_unpins(self):
        import wx
        from spikes_studio.desktop import Studio
        app=wx.GetApp() or wx.App(False);frame=Studio()
        try:
            frame.Show();frame.book.SetSelection(0);frame.show_browser();wx.Yield()
            window=frame.tool_windows.entries[11][0]
            self.assertTrue(window.IsShown())
            self.assertIs(frame.catalog_host.GetParent(),window)
            self.assertEqual(frame.book.GetSelection(),0)
            frame.pin_browser(True)
            self.assertTrue(frame.browser_pinned)
            frame.show_browser();wx.Yield()
            self.assertFalse(frame.browser_pinned)
            self.assertIs(frame.catalog_panel.GetParent(),frame.catalog_host)
            self.assertTrue(window.IsShown())
            self.assertIs(frame.tool_windows.entries[11][0],window)
        finally:
            frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()

    def test_main_selector_and_float_hide_reopen_dock(self):
        import wx
        from spikes_studio.desktop import Studio
        from spikes_studio.workbench_header import PRIMARY_VIEWS
        app=wx.GetApp() or wx.App(False);frame=Studio()
        try:
            frame.Show();wx.Yield()
            self.assertEqual([frame.workflow_bar.choice.GetString(i) for i in range(frame.workflow_bar.choice.GetCount())],[name for name,_ in PRIMARY_VIEWS])
            page=frame.book.GetPage(7)
            frame.tool_windows.open(7);window=frame.tool_windows.entries[7][0]
            self.assertIs(page.GetParent(),window)
            self.assertEqual(frame.book.FindPage(page),7)
            window.Close();wx.Yield();self.assertFalse(window.IsShown())
            self.assertIs(frame.tool_windows.open(7),window)
            self.assertEqual(frame.book.GetSelection(),0)
            frame.tool_windows.dock(7)
            self.assertIs(frame.book.GetPage(7),page)
            self.assertIs(page.GetParent(),frame.book)
            self.assertEqual(frame.book.GetSelection(),7)
            self.assertNotIn(7,frame.tool_windows.entries)
        finally:
            frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()
