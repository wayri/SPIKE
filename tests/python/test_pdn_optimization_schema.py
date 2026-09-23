"""Focused structural tests for the solver-independent PDN optimization schema."""

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "pdn-optimization-v1.schema.json"


class PdnOptimizationSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def test_schema_is_draft_2020_12_and_strict_at_every_contract_record(self):
        self.assertEqual(self.schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(self.schema["$id"], "https://spike.local/schemas/pdn-optimization-v1.schema.json")
        definitions = self.schema["$defs"]
        self.assertFalse(definitions["request"]["additionalProperties"])
        self.assertFalse(definitions["result"]["additionalProperties"])
        self.assertFalse(definitions["candidatePort"]["additionalProperties"])
        self.assertFalse(definitions["capacitor"]["additionalProperties"])

    def test_request_requires_explicit_ports_capacitor_lcr_mounting_and_ratings(self):
        definitions = self.schema["$defs"]
        self.assertEqual(definitions["request"]["properties"]["contract"]["const"], "spike/pdn-optimization/v1")
        self.assertTrue({"positive_terminal", "negative_terminal", "mounting"}.issubset(
            definitions["candidatePort"]["required"]
        ))
        self.assertTrue({
            "capacitance_f", "esr_ohm", "esl_h", "mounting", "min_count", "max_count",
            "unit_cost", "voltage_rating_v", "ripple_current_rating_a",
        }.issubset(definitions["capacitor"]["required"]))
        self.assertTrue({"target_violation_weight", "count_weight", "cost_weight"}.issubset(
            definitions["objectives"]["required"]
        ))

    def test_result_preserves_source_status_and_blocks_optimum_claims_for_non_exhaustive_search(self):
        result = self.schema["$defs"]["result"]
        self.assertIn("source_model_status", result["required"])
        self.assertEqual(result["properties"]["source_model_status"]["$ref"], "#/$defs/modelStatus")
        conditional = result["allOf"][0]
        self.assertEqual(conditional["if"]["properties"]["search_scope"]["const"], "exhaustive")
        self.assertEqual(conditional["else"]["properties"]["claim"]["const"], "recommendation")
        self.assertIn("global_optimum", result["properties"]["claim"]["enum"])


if __name__ == "__main__":
    unittest.main()
