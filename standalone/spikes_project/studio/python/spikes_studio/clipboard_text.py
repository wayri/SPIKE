# SPDX-License-Identifier: Apache-2.0
"""Immediate-rendered Unicode text clipboard access for Studio windows."""
from __future__ import annotations

import sys
import time


CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
MAX_CLIPBOARD_BYTES = 64 * 1024 * 1024


def _window_handle(owner) -> int:
    handle = int(owner.GetHandle())
    if not handle:
        raise ValueError('Clipboard requires a live owner window')
    return handle


def _windows_functions():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.GetOpenClipboardWindow.argtypes = []
    user32.GetOpenClipboardWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HANDLE]
    kernel32.GlobalFree.restype = wintypes.HANDLE
    kernel32.GlobalSize.argtypes = [wintypes.HANDLE]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    return ctypes, user32, kernel32


def _windows_error(action: str, ctypes_module) -> ValueError:
    code = ctypes_module.get_last_error()
    detail = ctypes_module.FormatError(code).strip() if code else 'operation failed'
    return ValueError(f'{action}: {detail}')


def _open_windows(user32, owner, ctypes_module) -> None:
    # Clipboard viewers and shell integrations commonly hold the clipboard for
    # a few milliseconds. Keep the UI deterministic without waiting unboundedly.
    for delay in (0.0, 0.01, 0.02, 0.04, 0.08, 0.16):
        if delay:
            time.sleep(delay)
        ctypes_module.set_last_error(0)
        if user32.OpenClipboard(_window_handle(owner)):
            return
    holder = user32.GetOpenClipboardWindow()
    if holder:
        from ctypes import wintypes
        process = wintypes.DWORD()
        user32.GetWindowThreadProcessId(holder, ctypes_module.byref(process))
        raise ValueError(f'Clipboard is busy (owner window {int(holder)}, process {process.value})')
    raise _windows_error('Clipboard is busy', ctypes_module)


def _write_windows(owner, text: str) -> None:
    if '\0' in text:
        raise ValueError('Clipboard text cannot contain NUL characters')
    ctypes, user32, kernel32 = _windows_functions()
    payload = text.encode('utf-16-le') + b'\0\0'
    memory = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(payload))
    if not memory:
        raise _windows_error('Unable to allocate clipboard text', ctypes)
    transferred = False
    opened = False
    try:
        pointer = kernel32.GlobalLock(memory)
        if not pointer:
            raise _windows_error('Unable to lock clipboard text', ctypes)
        try:
            ctypes.memmove(pointer, payload, len(payload))
        finally:
            kernel32.GlobalUnlock(memory)
        _open_windows(user32, owner, ctypes)
        opened = True
        if not user32.EmptyClipboard():
            raise _windows_error('Unable to clear clipboard', ctypes)
        if not user32.SetClipboardData(CF_UNICODETEXT, memory):
            raise _windows_error('Unable to copy circuit', ctypes)
        # SetClipboardData transfers the HGLOBAL to the system on success.
        transferred = True
    finally:
        if opened:
            user32.CloseClipboard()
        if not transferred:
            kernel32.GlobalFree(memory)


def _read_windows(owner) -> str | None:
    ctypes, user32, kernel32 = _windows_functions()
    _open_windows(user32, owner, ctypes)
    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return None
        memory = user32.GetClipboardData(CF_UNICODETEXT)
        if not memory:
            raise _windows_error('Unable to read clipboard text', ctypes)
        size = kernel32.GlobalSize(memory)
        if not size or size > MAX_CLIPBOARD_BYTES or size % 2:
            raise ValueError('Clipboard Unicode text has an invalid size')
        pointer = kernel32.GlobalLock(memory)
        if not pointer:
            raise _windows_error('Unable to lock clipboard text', ctypes)
        try:
            raw = ctypes.string_at(pointer, size)
            end = next((index for index in range(0, size - 1, 2)
                        if raw[index:index + 2] == b'\0\0'), None)
            if end is None:
                raise ValueError('Clipboard Unicode text is not NUL terminated')
            return raw[:end].decode('utf-16-le')
        finally:
            kernel32.GlobalUnlock(memory)
    finally:
        user32.CloseClipboard()


def write_text(owner, text: str) -> None:
    if sys.platform == 'win32':
        _write_windows(owner, text)
        return
    import wx
    if not wx.TheClipboard.Open():
        raise ValueError('Clipboard is busy')
    try:
        if not wx.TheClipboard.SetData(wx.TextDataObject(text)):
            raise ValueError('Unable to copy circuit')
        wx.TheClipboard.Flush()
    finally:
        wx.TheClipboard.Close()


def read_text(owner) -> str | None:
    if sys.platform == 'win32':
        return _read_windows(owner)
    import wx
    if not wx.TheClipboard.Open():
        raise ValueError('Clipboard is busy')
    try:
        data = wx.TextDataObject()
        return data.GetText() if wx.TheClipboard.GetData(data) else None
    finally:
        wx.TheClipboard.Close()
