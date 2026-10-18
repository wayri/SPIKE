# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import sys
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1','opt-in native wx')
class SMPSStabilityUITests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('SPIKES_TEST_SMPS_LIBRARY'),'native analysis library required')
    def test_native_default_background_analysis(self):
        import wx
        from spikes_studio.desktop import Studio
        from spikes_studio.ui_evidence import capture_window
        app=wx.GetApp() or wx.App(False)
        owner=Studio(library=os.environ['SPIKES_TEST_SMPS_LIBRARY']);window=None
        try:
            window=owner.frequency.smps_stability()
            self.assertEqual(window.backend.GetSelection(),0)
            window.request();deadline=time.monotonic()+15
            while window.busy and time.monotonic()<deadline:wx.Yield();time.sleep(.01)
            self.assertFalse(window.busy)
            self.assertIsNotNone(window.result,window.report.GetValue())
            self.assertIn('C++',window.result['backend'])
            directory=os.environ.get('SPIKES_SMPS_UI_EVIDENCE')
            if directory:
                Path(directory).mkdir(parents=True,exist_ok=True)
                wx.Yield();capture_window(window,Path(directory)/'native-smps-wide.png')
                window.SetSize((900,680));wx.Yield()
                capture_window(window,Path(directory)/'native-smps-narrow.png')
        finally:
            if window and not window.closed:window.close(None)
            owner.timer.Stop();owner.autosave_timer.Stop();owner.Destroy();wx.Yield()
    def test_model_fields_background_plots_and_project_undo(self):
        import wx
        from spikes_studio.desktop import Studio
        from spikes_studio.smps_stability_view import VIEWS
        from spikes_studio.ui_evidence import capture_window
        app=wx.GetApp() or wx.App(False);owner=Studio();window=None
        try:
            window=owner.frequency.smps_stability()
            window.backend.SetSelection(1)  # Explicit reference test; no silent native fallback.
            source=owner.doc.data['source'];window.request()
            deadline=time.monotonic()+15
            while window.busy and time.monotonic()<deadline:wx.Yield();time.sleep(.01)
            self.assertFalse(window.busy);self.assertIsNotNone(window.result,window.report.GetValue())
            self.assertIn('rational-model',window.report.GetValue())
            self.assertEqual(owner.doc.data['source'],source)
            directory=os.environ.get('SPIKES_SMPS_UI_EVIDENCE')
            if directory:
                Path(directory).mkdir(parents=True,exist_ok=True)
                window.Refresh();wx.Yield();capture_window(window,Path(directory)/'smps-loop-bode.png')
            for view in VIEWS:
                window.view.SetStringSelection(view);window.draw()
                self.assertTrue(window.figure.axes)
            window.SetSize((900,680));window.view.SetStringSelection('Poles / zeros');window.draw();wx.Yield()
            if directory:capture_window(window,Path(directory)/'smps-poles-narrow.png')
            window.save_setup();self.assertEqual(owner.doc.data['metadata']['smps_stability_setup'],window.config())
            owner.doc.undo();self.assertNotIn('smps_stability_setup',owner.doc.data['metadata'])
            self.assertEqual(owner.doc.data['source'],source)
            previous=window.result;window.fields['duty_cycle'].SetValue('2');window.request()
            deadline=time.monotonic()+15
            while window.busy and time.monotonic()<deadline:wx.Yield();time.sleep(.01)
            self.assertIs(window.result,previous);self.assertIn('failed',window.report.GetValue().lower())
        finally:
            if window and not window.closed:window.close(None)
            owner.timer.Stop();owner.autosave_timer.Stop();owner.Destroy();wx.Yield()

    def test_disabled_fields_and_worker_close(self):
        import wx
        from spikes_studio.desktop import Studio
        app=wx.GetApp() or wx.App(False);owner=Studio();window=None
        try:
            window=owner.frequency.smps_stability()
            window.backend.SetSelection(1)
            self.assertFalse(window.fields['turns_ratio'].IsEnabled())
            window.topology.SetSelection(3);window.reflect()
            self.assertTrue(window.fields['turns_ratio'].IsEnabled())
            window.controller.SetSelection(0);window.reflect()
            self.assertFalse(window.fields['pole1_hz'].IsEnabled())
            window.request();window.close(None);wx.Yield()
            self.assertTrue(window.closed)
        finally:
            if window and not window.closed:window.close(None)
            owner.timer.Stop();owner.autosave_timer.Stop();owner.Destroy();wx.Yield()
