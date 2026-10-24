# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Registered control schema does not substitute for revision/value validation."""
import json
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator

from tests.python import test_si_material_scenario as fixtures


class MaterialScenarioSchemaTests(unittest.TestCase):
    def test_registered_self_contained_schema_and_negative_controls(self):
        root = Path(__file__).resolve().parents[2] / "schemas"
        manifest = json.loads((root / "manifest.json").read_text())
        schema = json.loads((root / manifest["schemas"]["spike/si-material-scenario-request/v1"]).read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        design = fixtures.uniform_design()
        request = fixtures.scenario_request(design)
        validator.validate(request)
        for change in ({"source_digest": "not-a-digest"}, {"execute": True}, {"material_overrides": []}):
            with self.subTest(change=change):
                self.assertFalse(validator.is_valid({**request, **change}))
