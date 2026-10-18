# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1','opt-in native wx')
class FuzzyNativeTests(unittest.TestCase):
    def test_actual_parts_and_canvas_queries_preserve_source(self):
        import wx
        from spikes_studio.desktop import Studio
        from spikes_studio.quick_insert_popup import QuickInsert
        app=wx.GetApp() or wx.App(False);frame=Studio();popup=None
        try:
            frame.Show();before=frame.doc.data['source'];panel=frame.manufacturer_panel
            panel.search.SetValue('lm385');panel.refresh()
            self.assertTrue(any(r['mpn']=='LM358P' for r in panel.rows))
            panel.search.SetValue('LM358P');panel.refresh();self.assertEqual(panel.rows[0]['mpn'],'LM358P')
            catalog=frame.catalog_panel;catalog.search.SetValue('capaciotr');catalog.filter()
            self.assertTrue(any(r['family']=='capacitor' for r in catalog.list.rows))
            popup=QuickInsert(frame,(600,400));popup.query.SetValue('resistr')
            self.assertEqual(popup.rows[0]['payload'],'generic.resistor.001')
            self.assertEqual(frame.doc.data['source'],before)
        finally:
            if popup and not popup.closed:popup.close()
            frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()


if __name__=='__main__':unittest.main()
