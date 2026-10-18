# SPDX-License-Identifier: Apache-2.0
"""Member metadata extraction preserves existing package naming semantics."""
import unittest
from python.spike_core.project_package import _media_type, _member_role
from python.spike_core.project_member_metadata import media_type, member_role


class ProjectMemberMetadataTests(unittest.TestCase):
    def test_existing_private_imports_and_mime_values_are_preserved(self):
        self.assertIs(_media_type, media_type)
        self.assertIs(_member_role, member_role)
        expected = {'json': 'application/json', 'jsonl': 'application/x-ndjson',
                    'arrow': 'application/vnd.apache.arrow.file', 'html': 'text/html',
                    'pdf': 'application/pdf', 'csv': 'text/csv', 'step': 'model/step',
                    'stp': 'model/step', 'gltf': 'model/gltf+json', 'glb': 'model/gltf-binary',
                    'spkshape': 'application/vnd.spike.package-shape'}
        for suffix, mime in expected.items():
            self.assertEqual(media_type('models/original.'+suffix.upper()), mime)
        self.assertEqual(media_type('models/unknown.bin'), 'application/octet-stream')
        self.assertEqual(member_role('models/parts/original.step'), 'models')
