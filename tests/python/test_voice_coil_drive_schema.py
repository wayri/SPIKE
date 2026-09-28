# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator


class VoiceCoilSchemaTests(unittest.TestCase):
    def test_example_and_invalid_requests(self):
        root = Path(__file__).resolve().parents[2]
        schema = json.loads((root / 'schemas/voice-coil-drive-v1.schema.json').read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        request = json.loads((root / 'examples/actuator/voice-coil-drive.json').read_text())
        validator.validate(request)
        for key, value in [('mass_kg', 0), ('inductance_h', -1), ('duration_s', 0),
                           ('provenance', '  '), ('voltage_v', True), ('unknown', 1)]:
            with self.subTest(key=key):
                malformed = dict(request, **{key: value})
                self.assertTrue(list(validator.iter_errors(malformed)))
