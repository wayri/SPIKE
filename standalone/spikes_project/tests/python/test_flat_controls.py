# SPDX-License-Identifier: Apache-2.0
"""Opt-in actual wx controls: activation, disabled state and accessibility."""
import os
import unittest


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX') == '1', 'Opt-in wx control test')
class FlatControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import wx
        cls.app = wx.GetApp() or wx.App(False)

    def test_keyboard_toggle_and_disabled(self):
        import wx
        from spikes_studio.flat_controls import ActionButton
        frame = wx.Frame(None); control = ActionButton(frame, label='Inspector', toggle=True)
        calls = []
        control.Bind(wx.EVT_TOGGLEBUTTON, lambda event: calls.append(event.IsChecked()))
        try:
            key = wx.KeyEvent(wx.wxEVT_CHAR_HOOK);key.SetKeyCode(wx.WXK_SPACE)
            control.GetEventHandler().ProcessEvent(key)
            self.assertEqual(calls, [True]); self.assertTrue(control.GetValue())
            control.Disable(); control.activate()
            self.assertEqual(calls, [True])
            control.Enable(); control.activate()
            self.assertEqual(calls, [True, False])
            self.assertGreaterEqual(control.GetBestSize().height, 32)
            if hasattr(wx, 'Accessible'):
                accessible = control.GetAccessible()
                self.assertEqual(accessible.GetRole(0), (wx.ACC_OK, wx.ROLE_SYSTEM_PUSHBUTTON))
                self.assertEqual(accessible.GetName(0), (wx.ACC_OK, 'Inspector'))
        finally: frame.Destroy()
