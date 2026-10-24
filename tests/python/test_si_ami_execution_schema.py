# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Structural native execution contract does not grant executable trust."""
import json
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator


class AmiExecutionSchemaTests(unittest.TestCase):
    def test_registered_local_contract_and_strict_admission_shape(self):
        root = Path(__file__).resolve().parents[2] / "schemas"
        manifest = json.loads((root / "manifest.json").read_text())
        schema = json.loads((root / manifest["schemas"]["spike/si-ami-execution-request/v1"]).read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        value = {"contract": "spike/si-ami-execution-request/v1", "platform": "windows-x86_64", "direction": "rx",
                 "model_file": {"path": "C:/reviewed/model.dll", "sha256": "a" * 64}, "dependencies": [],
                 "trust": {"acknowledgement": "trusted-native-code-with-current-user-access",
                           "license_reviewed": True, "dependency_reviewed": True},
                 "parameter_text": "(Original)", "sample_interval_s": 1e-12, "symbol_time_s": 1e-10,
                 "impulse_response": [1e12, 0], "wave_blocks": [[0., 1.]], "timeout_s": 10, "memory_limit_mib": 128}
        validator.validate(value)
        for change in ({"execute": True}, {"dependencies": ["unknown.dll"]}, {"platform": "linux-x86_64"},
                       {"timeout_s": 301}, {"memory_limit_mib": True}, {"sample_interval_s": "1e-12"},
                       {"model_file": {**value["model_file"], "unknown": True}},
                       {"trust": {**value["trust"], "license_reviewed": 1}}):
            with self.subTest(change=change):
                self.assertFalse(validator.is_valid({**value, **change}))
