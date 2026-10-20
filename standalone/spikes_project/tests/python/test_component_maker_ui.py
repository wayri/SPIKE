# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1','opt-in native wx')
class ComponentMakerUITests(unittest.TestCase):
    def setUp(self):
        import wx
        from spikes_studio.desktop import Studio
        from spikes_studio.component_maker import ComponentMaker
        from spikes_studio.component_package import ComponentStore
        self.app=wx.GetApp() or wx.App(False);self.owner=Studio();self.maker=ComponentMaker(self.owner)
        self.temp=tempfile.TemporaryDirectory();self.maker.store=ComponentStore(self.temp.name)
    def tearDown(self):
        import wx
        self.maker.closed=True;self.maker.executor.shutdown(wait=False,cancel_futures=True);self.maker.Destroy()
        self.owner.timer.Stop();self.owner.autosave_timer.Stop();self.owner.Destroy();wx.Yield();self.temp.cleanup()

    def test_visual_pin_geometry_source_and_library_roundtrip(self):
        maker=self.maker;value=maker.value();self.assertEqual(value['implementation']['language'],'SPICE')
        self.assertEqual(len(maker.designer.symbol['terminals']),2);self.assertFalse(maker.trust.GetValue())
        maker.install();maker.search.SetValue('user componnet');maker.refresh_library()
        self.assertEqual(len(maker.library_rows),1)
        self.assertIn('Component maker',self.owner.commands.commands['view.component_maker'].label)
        for width,height in ((1100,800),(800,560)):
            maker.SetSize((width,height));maker.Show();maker.Layout();self.app.Yield()
            self.assertGreater(maker.designer.canvas.GetSize().width,100)
            self.assertGreater(maker.designer.canvas.GetSize().height,70)
            maker.designer.canvas.fit()
            canvas=maker.designer.canvas
            for corner in maker.designer.symbol['body_keepout'].values():
                x,y=canvas.point(corner)
                self.assertGreaterEqual(x,0);self.assertLessEqual(x,canvas.GetSize().width)
                self.assertGreaterEqual(y,0);self.assertLessEqual(y,canvas.GetSize().height)
        maker.validate();self.assertEqual(maker.book.GetSelection(),3)
        self.assertIn('Interface valid',maker.report.GetValue())

    def test_cpp_attach_clears_trust_without_execution(self):
        from spikes_studio.component_package import new_component,controller_config
        from spikes_studio.controller_block import DEFAULT_CODE
        value=new_component();value['implementation']={'language':'C++','entry':'control_step','source':DEFAULT_CODE,
            'controller':controller_config(value['symbol'],DEFAULT_CODE)}
        self.maker.load_value(value);self.maker.place()
        self.assertIsNone(self.owner.controller_panel.compiled);self.assertFalse(self.owner.controller_panel.trust.GetValue())
        self.assertEqual(self.owner.controller_panel.config()['source'],DEFAULT_CODE)

    def test_dirty_draft_cancel_and_no_declared_model(self):
        from unittest.mock import patch
        import wx
        maker=self.maker;maker.designer.select(1)
        self.assertTrue(maker.confirm_replace())  # selecting a pin is not an edit
        maker.fields['name'].SetValue('Unsaved name')
        with patch('wx.MessageBox',return_value=wx.CANCEL):self.assertFalse(maker.confirm_replace())
        with patch.object(maker,'save',return_value=False),patch('wx.MessageBox',return_value=wx.YES):self.assertFalse(maker.confirm_replace())
        with self.assertRaisesRegex(ValueError,'(?i)No .MODEL or .SUBCKT'):maker.import_text('R1 a b 1k\n')

    def test_pending_pin_edits_apply_on_validation(self):
        maker=self.maker;maker.designer.fields['number'].SetValue('99')
        value=maker.value();self.assertEqual(value['symbol']['terminals'][0]['id'],'99')

    def test_owner_close_preserves_cancelled_draft_and_running_build(self):
        from spikes_studio.component_maker import prepare_owner_close
        from unittest.mock import patch
        maker=self.maker
        maker.busy=True;self.assertFalse(prepare_owner_close(self.owner));maker.busy=False
        with patch.object(maker,'confirm_replace',return_value=False):self.assertFalse(prepare_owner_close(self.owner))
        with patch.object(maker,'confirm_replace',return_value=True):self.assertTrue(prepare_owner_close(self.owner))

    def test_context_menu_capture_disabled_without_selection_and_busy(self):
        import wx
        from spikes_studio.schematic_context import build
        event=wx.MouseEvent(wx.wxEVT_RIGHT_UP);event.SetPosition(wx.Point(10,10));canvas=self.owner.canvas
        menu=build(canvas,event,canvas.world(event.GetPosition()))
        try:
            sub=next(item.GetSubMenu() for item in menu.menu.GetMenuItems() if item.GetItemLabelText()=='Components / compile circuit')
            capture=next(item for item in sub.GetMenuItems() if item.GetItemLabelText()=='Make component from selected circuit…')
            self.assertFalse(capture.IsEnabled())
        finally:menu.menu.Destroy()
        self.owner.job_running=True
        with self.assertRaisesRegex(ValueError,'Stop'):self.maker.place()
        self.owner.job_running=False


if __name__=='__main__':unittest.main()
