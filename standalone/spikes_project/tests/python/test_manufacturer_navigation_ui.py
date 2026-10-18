# SPDX-License-Identifier: Apache-2.0
"""Product discovery and admitted electrical records retain distinct routes."""
import os
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1','opt-in native wx')
class ManufacturerNavigationTests(unittest.TestCase):
    def test_product_hub_and_electrical_parts_keep_working_navigation(self):
        import wx
        from spikes_studio.desktop import Studio
        from spikes_studio.quick_insert_popup import QuickInsert
        app=wx.GetApp() or wx.App(False);frame=Studio();popup=None
        try:
            frame.Show();wx.Yield();before=frame.doc.data['source']
            self.assertIs(frame.manufacturer_panel,frame.manufacturer_hub.parts)
            frame.show_manufacturer_library();wx.Yield()
            self.assertEqual(frame.manufacturer_hub.book.GetSelection(),0)
            frame.show_manufacturer_parts();wx.Yield()
            self.assertEqual(frame.manufacturer_hub.book.GetSelection(),1)
            frame.manufacturer_panel.search.SetValue('LM358P');frame.manufacturer_panel.refresh()
            self.assertEqual(frame.manufacturer_panel.rows[0]['mpn'],'LM358P')
            popup=QuickInsert(frame,(600,400));popup.query.SetValue('resistr')
            self.assertEqual(popup.rows[0]['payload'],'generic.resistor.001')
            self.assertEqual(frame.doc.data['source'],before)
        finally:
            if popup and not popup.closed:popup.close()
            frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()
