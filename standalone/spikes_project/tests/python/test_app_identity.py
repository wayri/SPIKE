# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'studio/python'))


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX') == '1', 'Opt-in native wx icon test')
class AppIdentityTests(unittest.TestCase):
    def test_native_icon_bundle_and_shell_identity(self):
        import wx
        from spikes_studio.app_identity import configure_process_identity, set_window_icons, APP_USER_MODEL_ID
        self.assertEqual(APP_USER_MODEL_ID, 'SPIKES.Studio')
        status = configure_process_identity()
        if sys.platform == 'win32': self.assertEqual(status, 0)
        app = wx.GetApp() or wx.App(False)
        frame = wx.Frame(None)
        try:
            path = set_window_icons(frame)
            self.assertEqual(path.suffix, '.ico')
            icons = frame.GetIcons()
            self.assertGreaterEqual(icons.GetIconCount(), 3)
            for size in (16, 32, 48):
                icon = icons.GetIcon(wx.Size(size, size))
                self.assertTrue(icon.IsOk())
                self.assertEqual((icon.GetWidth(), icon.GetHeight()), (size, size))
            if sys.platform == 'win32':
                import ctypes
                user = ctypes.WinDLL('user32')
                send = user.SendMessageW
                send.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
                send.restype = ctypes.c_ssize_t
                # WM_GETICON: check actual native HWND small and large handles.
                self.assertNotEqual(send(frame.GetHandle(), 0x007f, 0, 0), 0)
                self.assertNotEqual(send(frame.GetHandle(), 0x007f, 1, 0), 0)
        finally: frame.Destroy()
