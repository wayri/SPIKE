# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from test_net_labels import HIERARCHY


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1','opt-in native wx')
class ScopedCanvasTests(unittest.TestCase):
    def test_scope_navigation_actual_ports_and_label_tool_cancel(self):
        import wx
        from spikes_studio.desktop import Studio
        from spikes_studio.document import Document
        from spikes_studio.hierarchy_views import open_sheet,parent,instances
        from spikes_studio.net_labels import attach
        app=wx.GetApp() or wx.App(False);frame=Studio()
        try:
            frame.doc=Document.from_netlist(HIERARCHY);frame.refresh_document(force_source=True);frame.Show();wx.Yield()
            part=next(p for p in frame.doc.data['components'] if p['ref']=='X1:R1')
            attach(frame.doc,'hierarchical','input',[part['id'],0]);open_sheet(frame,'X1');wx.Yield()
            self.assertTrue(all(p['ref'].startswith('X1:') for p in frame.canvas.visible_parts()))
            self.assertEqual(len(instances(frame.doc.data['source'])),2)
            frame.canvas.Refresh();frame.canvas.Update();wx.Yield();self.assertEqual(len(frame.canvas.label_hits),1)
            self.assertEqual({p['id'] for rect,p in frame.canvas.hits},{p['id'] for p in frame.canvas.visible_parts()})
            frame.start_net_label();self.assertTrue(frame.canvas.label_mode)
            from types import SimpleNamespace
            frame.canvas.placement_key(SimpleNamespace(GetKeyCode=lambda:wx.WXK_ESCAPE))
            self.assertFalse(frame.canvas.label_mode)
            parent(frame);self.assertIsNone(frame.canvas.sheet_scope)
            frame.toggle_wire_hops();self.assertTrue(frame.doc.data['metadata']['wire_hops']);frame.doc.undo();self.assertFalse(frame.doc.data['metadata'].get('wire_hops',False))
        finally:frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()
