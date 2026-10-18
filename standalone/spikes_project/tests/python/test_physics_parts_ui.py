# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))


class DeviceGlyphTests(unittest.TestCase):
    def test_bodies_are_real_and_do_not_change_pin_order(self):
        from spikes_studio.device_glyphs import body
        from spikes_studio.pin_geometry import pins
        mos={'id':'M1','kind':'nmos_level1','nodes':['d','s','g','b']}
        self.assertEqual([pin.label for pin in pins(mos)],['D','S','G','B'])
        self.assertTrue(any(item.get('fill') for item in body('nmos_level1')))
        self.assertTrue(any(item.get('fill') for item in body('npn_ebers_moll')))
        first=body('nmos_level1');first.clear();self.assertTrue(body('nmos_level1'))
        self.assertIsNone(body('bsim_bulk'))  # no inferred N/P polarity


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1','opt-in native wx')
class PhysicsPartsUITests(unittest.TestCase):
    def test_native_mos_canvas_bulk_and_saved_document(self):
        import wx
        from spikes_studio.desktop import Studio
        from spikes_studio.document import Document
        from spikes_studio.pin_geometry import pins
        from spikes_studio.ui_evidence import capture_window
        app=wx.GetApp() or wx.App(False);frame=Studio()
        try:
            frame.doc=Document.from_netlist('Independent bulk\nVD d 0 4\nVG g 0 3\nVB b 0 -1\n.model MN NMOS(VTO=1 KP=.02 GAMMA=.4 PHI=.6)\nM1 d g 0 b MN\n.op\n.end')
            frame.refresh_document(force_source=True);frame.Show();frame.Layout();frame.docks.Update();frame.workflow_bar.home();wx.Yield();frame.fit();wx.Yield()
            part=next(p for p in frame.doc.data['components'] if p['ref']=='M1')
            self.assertEqual(part['nodes'],['d','0','g','b'])
            self.assertEqual([p.label for p in pins(part)],['D','S','G','B'])
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'bulk.spksch';frame.doc.save(path);loaded=Document.load(path)
                self.assertEqual(loaded.data['source'],frame.doc.data['source'])
                self.assertEqual(next(p for p in loaded.data['components'] if p['ref']=='M1')['nodes'],part['nodes'])
            directory=os.environ.get('SPIKES_PHYSICS_UI_EVIDENCE')
            if directory:
                Path(directory).mkdir(parents=True,exist_ok=True)
                frame.canvas.Refresh();frame.canvas.Update();wx.Yield()
                capture_window(frame,Path(directory)/'native-mos-independent-bulk.png')
        finally:frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()

    def test_physics_browser_symbols_parameters_and_export_recipes(self):
        import wx
        from spikes_studio.desktop import Studio
        from spikes_studio.ui_evidence import capture_window
        app=wx.GetApp() or wx.App(False);frame=Studio();window=None
        try:
            window=frame.open_physics_models()
            self.assertEqual(len(window.entries),5)
            for index,entry in enumerate(window.entries):
                window.choice.SetSelection(index);window.select()
                self.assertEqual(window.model['pins'],entry['pins'])
                self.assertEqual(len(window.model['pins']),len(frame.symbols[window.model['symbol_id']]['terminals']))
                self.assertIn('generic_unqualified',window.report.GetValue())
                self.assertTrue(window.figure.axes)
            directory=os.environ.get('SPIKES_PHYSICS_UI_EVIDENCE')
            window.choice.SetSelection(1);window.select();window.SetSize((850,680));window.Layout()
            deadline=time.monotonic()+.15
            while time.monotonic()<deadline:wx.Yield();time.sleep(.01)
            window.canvas.draw();wx.Yield()
            axis=window.figure.axes[0];size=window.canvas.GetClientSize()
            for pin in frame.symbols[window.model['symbol_id']]['terminals']:
                x,y=axis.transData.transform(pin['at'])
                self.assertTrue(0<x<size.width and 0<y<size.height,(pin['name'],x,y,size))
            if directory:capture_window(window,Path(directory)/'npn-explicit-substrate-model.png')
            original=window.model
            field=next(iter(window.fields.values()));field.SetValue('-1')
            with self.assertRaises(ValueError):window.update_preview()
            self.assertIs(window.model,original)
        finally:
            if window:window.Destroy()
            frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()
