# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import sys
import time
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'studio/python'))


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX') == '1', 'opt-in native wx')
class CompiledICUITests(unittest.TestCase):
    def test_visual_fields_and_parameter_validation(self):
        import wx
        from spikes_studio.compiled_ic_dialog import CompiledICDialog
        from spikes_studio.ui_evidence import capture_window
        app = wx.GetApp() or wx.App(False)
        dialog = CompiledICDialog(None)
        def capture(path):
            dialog.Layout();dialog.Refresh()
            deadline=time.monotonic()+.2
            while time.monotonic()<deadline:
                wx.Yield();time.sleep(.01)
            capture_window(dialog,path)
        try:
            dialog.Show(); wx.Yield()
            self.assertEqual(dialog.configuration()['pins'][2]['source'], 'VPWM')
            dialog.fields['switching_period_s'].SetValue('0.00001')
            with self.assertRaisesRegex(ValueError, 'two ticks'):
                dialog.configuration()
            dialog.fields['switching_period_s'].SetValue('0.001')
            directory = os.environ.get('SPIKES_IC_UI_EVIDENCE')
            if directory:
                Path(directory).mkdir(parents=True, exist_ok=True)
                capture(Path(directory)/'pwm-library.png')
            dialog.choice.SetSelection(1); dialog.refresh_fields()
            dialog.SetSize((550, 650)); wx.Yield()
            self.assertEqual(dialog.configuration()['pins'][2]['source'], 'VCOMMAND')
            if directory:
                capture(Path(directory)/'pi-library-narrow.png')
            dialog.fields['kp'].SetValue('nan')
            with self.assertRaises(ValueError):
                dialog.configuration()
            if directory:
                dialog.choice.SetSelection(0);dialog.refresh_fields()
                dialog.SetSize((720,620));wx.Yield()
                dialog.Hide()
                failures=[]
                def modal_capture():
                    try:
                        capture(Path(directory)/'pwm-library.png')
                    except Exception as error:
                        failures.append(error)
                    finally:
                        dialog.EndModal(wx.ID_CANCEL)
                wx.CallLater(600,modal_capture)
                dialog.ShowModal()
                if failures:raise failures[0]
        finally:
            dialog.Destroy(); wx.Yield()

    def test_loading_is_inert_resets_trust_and_preserves_circuit(self):
        import wx
        from spikes_studio.desktop import Studio
        from spikes_studio.compiled_ic_library import configuration
        app = wx.GetApp() or wx.App(False)
        frame = Studio()
        try:
            panel = frame.controller_panel
            source = frame.doc.data['source']
            panel.trust.SetValue(True); panel.enabled.SetValue(True)
            config = configuration('generic.sampled_pwm')
            panel.load_block(config)
            self.assertEqual(panel.config(), config)
            self.assertFalse(panel.trust.GetValue()); self.assertFalse(panel.enabled.GetValue())
            self.assertIsNone(panel.compiled)
            self.assertEqual(frame.doc.data['source'], source)
            self.assertIsNone(frame.doc.data['controller_setup'])
            panel.apply()
            self.assertEqual(frame.doc.data['controller_setup'], config)
            frame.doc.undo()
            self.assertIsNone(frame.doc.data['controller_setup'])
        finally:
            frame.timer.Stop(); frame.autosave_timer.Stop(); frame.Destroy(); wx.Yield()
