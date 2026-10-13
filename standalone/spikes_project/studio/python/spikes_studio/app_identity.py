# SPDX-License-Identifier: Apache-2.0
"""Stable shell identity and multi-resolution application window icons."""
import sys
import warnings
from .resources import resource_dir

APP_USER_MODEL_ID = 'SPIKES.Studio'


def configure_process_identity():
    """Call before creating GUI windows; source runs must not group as Python."""
    if sys.platform != 'win32': return None
    import ctypes
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    set_id = shell.SetCurrentProcessExplicitAppUserModelID
    set_id.argtypes = [ctypes.c_wchar_p]
    set_id.restype = ctypes.c_long
    result = set_id(APP_USER_MODEL_ID)
    if result != 0:
        warnings.warn(f'Windows application identity failed: HRESULT {result & 0xffffffff:#010x}')
    return result


def set_window_icons(window):
    import wx
    directory = resource_dir('library')
    ico = directory / 'spikes-studio.ico'
    if ico.is_file():
        bundle = wx.IconBundle(str(ico), wx.BITMAP_TYPE_ICO)
        if bundle.GetIconCount():
            window.SetIcons(bundle)
            return ico
    png = directory / 'spikes-studio.png'
    if png.is_file():
        icon = wx.Icon(str(png), wx.BITMAP_TYPE_PNG)
        if icon.IsOk():
            window.SetIcon(icon)
            return png
    warnings.warn('SPIKES Studio application icon is missing or invalid')
    return None
