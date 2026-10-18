# SPDX-License-Identifier: Apache-2.0
"""Malformed external clipboard blocks must never trigger unbounded reads."""
import ctypes
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'studio/python'))
from spikes_studio import clipboard_text


class ClipboardReadTests(unittest.TestCase):
    def transport(self, raw, size=None):
        buffer = ctypes.create_string_buffer(raw)
        user = SimpleNamespace(IsClipboardFormatAvailable=Mock(return_value=True),
            GetClipboardData=Mock(return_value=1), CloseClipboard=Mock())
        kernel = SimpleNamespace(GlobalSize=Mock(return_value=len(raw) if size is None else size),
            GlobalLock=Mock(return_value=ctypes.addressof(buffer)), GlobalUnlock=Mock())
        return buffer, user, kernel

    def read(self, user, kernel):
        with patch.object(clipboard_text, '_windows_functions', return_value=(ctypes, user, kernel)), \
             patch.object(clipboard_text, '_open_windows'):
            return clipboard_text._read_windows(object())

    def test_unicode_ends_at_aligned_nul_before_allocation_padding(self):
        raw = 'RΩ 😀'.encode('utf-16-le') + b'\0\0\xff\xff'
        buffer, user, kernel = self.transport(raw)
        self.assertEqual(self.read(user, kernel), 'RΩ 😀')
        kernel.GlobalUnlock.assert_called_once_with(1)
        user.CloseClipboard.assert_called_once()

    def test_invalid_sizes_are_rejected_before_locking_or_reading(self):
        for size in (0, 3, clipboard_text.MAX_CLIPBOARD_BYTES + 2):
            with self.subTest(size=size):
                buffer, user, kernel = self.transport(b'\0\0', size)
                with self.assertRaises(ValueError): self.read(user, kernel)
                kernel.GlobalLock.assert_not_called()
                user.CloseClipboard.assert_called_once()

    def test_unterminated_and_invalid_utf16_release_the_block(self):
        for raw in (b'A\0B\0', b'\0\xd8\0\0'):
            with self.subTest(raw=raw):
                buffer, user, kernel = self.transport(raw)
                with self.assertRaises(ValueError): self.read(user, kernel)
                kernel.GlobalUnlock.assert_called_once_with(1)
                user.CloseClipboard.assert_called_once()

    def test_nontext_clipboard_is_ignored_and_closed(self):
        buffer, user, kernel = self.transport(b'\0\0')
        user.IsClipboardFormatAvailable.return_value = False
        self.assertIsNone(self.read(user, kernel))
        kernel.GlobalLock.assert_not_called()
        user.CloseClipboard.assert_called_once()


if __name__ == '__main__': unittest.main()
