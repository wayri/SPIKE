# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import sys
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1' and os.environ.get('SPIKES_TEST_LIBRARY'),'native wx/library required')
class AnalysisPlotWindowTests(unittest.TestCase):
    def test_real_native_samples_background_calculation_and_errors(self):
        import wx
        from spikes_studio.desktop import Studio
        from spikes_studio.run_control import native_batch
        from spikes_studio.signal_math import SignalMath
        from spikes_studio.analysis_plot_window import AnalysisPlotWindow
        app=wx.GetApp() or wx.App(False);frame=Studio();window=None
        try:
            result=native_batch(frame.doc.data['source'],os.environ['SPIKES_TEST_LIBRARY'])
            self.assertEqual(result['status'],'completed');frame.math=SignalMath.from_result(result)
            frame.expression.SetValue('v(out)');frame.Show();window=AnalysisPlotWindow(frame)
            for kind in ('FFT peak amplitude','Cumulative integral','XY / phase portrait','Histogram'):
                window.view.SetStringSelection(kind);window.reflect();window.request()
                deadline=time.monotonic()+5
                while window.busy and time.monotonic()<deadline:wx.Yield();time.sleep(.01)
                self.assertFalse(window.busy);self.assertEqual(window.last_data['view'],kind)
                self.assertTrue(window.figure.axes[0].lines)
            captured=window.engine;frame.math=None;self.assertIs(window.engine,captured)
            window.SetSize((780,600));window.Layout();wx.Yield();window.draw(window.last_data)
            self.assertLessEqual(window.canvas.GetPosition().y+window.canvas.GetSize().height,window.report.GetPosition().y)
            from unittest.mock import patch
            from spikes_studio.context_menus import ContextMenu
            targeted=[]
            def check_popup(menu,target,position=None):
                targeted.append(target);menu.menu.Destroy()
            with patch.object(ContextMenu,'popup',check_popup):
                event=wx.ContextMenuEvent(wx.wxEVT_CONTEXT_MENU);event.SetPosition(wx.DefaultPosition);window.context(event)
            self.assertEqual(targeted,[window.canvas])
            window.fields['signal'].SetValue('v(no_such_net)');window.request()
            deadline=time.monotonic()+5
            while window.busy and time.monotonic()<deadline:wx.Yield();time.sleep(.01)
            self.assertIn('failed',window.report.GetValue().lower())
        finally:
            if window:window.Close()
            frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()


if __name__=='__main__':unittest.main()
