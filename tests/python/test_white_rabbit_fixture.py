# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import base64
import hashlib
import unittest
from scripts.fetch_white_rabbit_fixture import decode_member


class FixtureIntegrityTests(unittest.TestCase):
    def test_bytes_bound_to_member_size_and_digest(self):
        payload = b'inert board fixture'
        raw = {'file_path': 'board', 'encoding': 'base64', 'size': len(payload),
               'content': base64.b64encode(payload).decode(),
               'content_sha256': hashlib.sha256(payload).hexdigest()}
        self.assertEqual(decode_member(raw, 'board')[0], payload)
        for change in ({'size': 0}, {'content_sha256': '0'*64}, {'file_path': 'other'},
                       {'encoding': 'text'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                decode_member({**raw, **change}, 'board')
