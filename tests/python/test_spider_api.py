# SPDX-License-Identifier: Apache-2.0
"""Focused acceptance tests for bounded SpiDeR interoperability operations."""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from python.spike_core.spider_api import (
    document_for_legacy_worker, handle_spider_request, normalize_document,
)


ROOT = Path(__file__).resolve().parents[2]


class SpiDeRApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.v1 = json.loads((ROOT / "examples/tutorial_pi_si/straight_trace.design.json").read_text(encoding="utf-8"))
        cls.v2 = json.loads((ROOT / "examples/esp32/evidence/si_geometry_design.json").read_text(encoding="utf-8"))
        cls.result_schema = json.loads((ROOT / "schemas/spider-api-result-v1.schema.json").read_text(encoding="utf-8"))
        cls.request_schema = json.loads((ROOT / "schemas/spider-api-request-v1.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.request_schema)
        Draft202012Validator.check_schema(cls.result_schema)
        cls.result_validator = Draft202012Validator(cls.result_schema)

    def assertResult(self, result: dict) -> None:
        self.result_validator.validate(result)
        self.assertEqual(result["contract"], "spider/api-result/v1")

    def test_actual_v1_and_v2_fixtures_validate_with_revision_evidence(self) -> None:
        for document, expected in ((self.v1, "spike/v1"), (self.v2, "spike/design-ir/v2")):
            result = handle_spider_request("validate_spider", {"document": document})
            self.assertResult(result)
            self.assertTrue(result["ok"], result["issues"])
            self.assertEqual(result["document_contract"], expected)
            self.assertRegex(result["document_revision"], r"^[0-9a-f]{64}$")
            self.assertTrue(result["source_revision"])

    def test_malformed_duplicate_nonfinite_units_and_dangling_refs_fail(self) -> None:
        cases = []
        dangling = deepcopy(self.v2)
        dangling["tracks"][0]["net_id"] = "missing-net"
        cases.append((dangling, "spider.dangling_reference"))
        duplicate = deepcopy(self.v2)
        duplicate["tracks"][1]["id"] = duplicate["tracks"][0]["id"]
        cases.append((duplicate, "spider.duplicate_entity_id"))
        nonfinite = deepcopy(self.v1)
        nonfinite["tracks"][0]["width"] = math.inf
        cases.append((nonfinite, "spider.invalid_json_value"))
        units = deepcopy(self.v1)
        units["units"] = "inch"
        cases.append((units, "spider.unsupported_units"))
        malformed = deepcopy(self.v2)
        malformed["tracks"] = {}
        cases.append((malformed, "spider.invalid_collection"))
        for document, code in cases:
            result = handle_spider_request("validate_spider", {"document": document})
            self.assertFalse(result["ok"])
            self.assertIn(code, {item["code"] for item in result["issues"]})

    def test_typed_physical_values_and_geometry_do_not_coerce(self) -> None:
        cases = []
        material = deepcopy(self.v2)
        material["materials"][0]["conductivity_s_per_m"] = "gold"
        cases.append((material, "spider.invalid_number"))
        negative = deepcopy(self.v2)
        negative["materials"][0]["relative_permittivity"] = -1.0
        cases.append((negative, "spider.invalid_physical_value"))
        boolean_coordinate = deepcopy(self.v2)
        boolean_coordinate["tracks"][0]["start_mm"][0] = True
        cases.append((boolean_coordinate, "spider.invalid_number"))
        extensions = deepcopy(self.v2)
        extensions["tracks"][0]["extensions"] = False
        cases.append((extensions, "spider.invalid_extensions"))
        metadata = deepcopy(self.v2)
        metadata["metadata"] = []
        cases.append((metadata, "spider.invalid_object"))
        for document, code in cases:
            result = handle_spider_request("validate_spider", {"document": document})
            self.assertFalse(result["ok"])
            self.assertIn(code, {item["code"] for item in result["issues"]})

    def test_malformed_filters_return_diagnostics_instead_of_raising(self) -> None:
        for method, params in (
            ("query_spider", {"document": self.v2, "entity_types": [["tracks"]]}),
            ("query_spider", {"document": self.v2, "ids": [["id"]]}),
            ("compare_spider", {"before": self.v2, "after": self.v2, "entity_types": [{}]}),
        ):
            result = handle_spider_request(method, params)
            self.assertResult(result)
            self.assertFalse(result["ok"])
            self.assertTrue(result["issues"])

    def test_query_is_stably_paginated_and_revision_guarded(self) -> None:
        first = handle_spider_request("query_spider", {
            "document": self.v2, "entity_types": ["tracks"], "limit": 2,
        })
        second = handle_spider_request("query_spider", {
            "document": self.v2, "entity_types": ["tracks"], "limit": 2, "offset": 2,
            "expected_revision": first["document_revision"],
        })
        repeated = handle_spider_request("query_spider", {
            "document": self.v2, "entity_types": ["tracks"], "limit": 2,
        })
        self.assertResult(first)
        self.assertTrue(first["ok"] and second["ok"])
        self.assertEqual(first["entities"], repeated["entities"])
        self.assertEqual(first["page"]["next_offset"], 2)
        self.assertFalse({row["id"] for row in first["entities"]} & {row["id"] for row in second["entities"]})
        for row in first["entities"]:
            self.assertEqual(row["id"], row["entity"]["id"])
            self.assertEqual(row["source_id"], row["entity"]["source_id"])
            self.assertTrue(all(ref["id"] for ref in row["references"]))
        conflict = handle_spider_request("query_spider", {
            "document": self.v2, "expected_revision": "0" * 64,
        })
        self.assertFalse(conflict["ok"])
        self.assertEqual(conflict["issues"][-1]["code"], "spider.revision_conflict")

    def test_diff_is_deterministic_and_reports_source_frame_drift(self) -> None:
        after = deepcopy(self.v2)
        after["tracks"][0]["width_mm"] += 0.01
        after["source"]["source_digest"] = "f" * 64
        after["frame"]["transform"][3] = 1.0
        params = {"before": self.v2, "after": after, "entity_types": ["tracks"], "limit": 1}
        first = handle_spider_request("compare_spider", params)
        repeated = handle_spider_request("compare_spider", params)
        self.assertResult(first)
        self.assertEqual(first, repeated)
        self.assertTrue(first["drift"]["source"])
        self.assertTrue(first["drift"]["frame"])
        self.assertEqual(first["changes"][0]["change"], "changed")
        self.assertIn("width_mm", first["changes"][0]["changed_fields"])
        self.assertFalse(first["projection"]["lossy"])

    def test_lossy_projection_is_disclosed_and_strict_legacy_helper_rejects(self) -> None:
        document = deepcopy(self.v2)
        document["constraints"] = [{
            "id": "constraint-id", "source_id": "constraint-source", "name": "rule",
            "extensions": {}, "kind": "clearance", "data": {"value_mm": 0.2},
        }]
        normalized = normalize_document(document, target_contract="spike/v1")
        self.assertTrue(normalized["ok"])
        self.assertTrue(normalized["projection"]["lossy"])
        self.assertIn("constraints", normalized["projection"]["losses"])
        strict = document_for_legacy_worker(document)
        self.assertFalse(strict["ok"])
        self.assertIsNone(strict["document"])
        self.assertEqual(strict["report"]["issues"][-1]["code"], "spider.lossy_projection")

    def test_stale_v1_extension_snapshots_are_never_accepted_as_lossless(self) -> None:
        typed = normalize_document(self.v1, target_contract="spike/design-ir/v2")["normalized_document"]
        for mutate in (
            lambda value: value["tracks"][0].update({"end_mm": [99.0, 99.0]}),
            lambda value: value["materials"][0].update({"conductivity_s_per_m": 123.0}),
        ):
            changed = deepcopy(typed)
            mutate(changed)
            result = document_for_legacy_worker(changed)
            self.assertFalse(result["ok"])
            self.assertTrue(any(item.startswith("semantic_roundtrip:") for item in result["report"]["projection"]["losses"]))

    def test_component_position_snapshot_change_is_rejected(self) -> None:
        source = deepcopy(self.v1)
        source["components"] = [{"id": "U1", "reference": "U1", "at": [1.0, 2.0]}]
        typed = normalize_document(source, target_contract="spike/design-ir/v2")["normalized_document"]
        typed["components"][0]["position_mm"] = [7.0, 8.0]
        result = document_for_legacy_worker(typed)
        self.assertFalse(result["ok"])
        self.assertTrue(any("components" in item for item in result["report"]["projection"]["losses"]))

    def test_schemas_validate_requests_and_emitted_results(self) -> None:
        request = {"method": "spider_capabilities", "params": {}}
        Draft202012Validator(self.request_schema).validate(request)
        results = [
            handle_spider_request("spider_capabilities", {}),
            handle_spider_request("validate_spider", {"document": self.v1}),
            handle_spider_request("normalize_spider", {"document": self.v1}),
            handle_spider_request("query_spider", {"document": self.v2, "limit": 1}),
            handle_spider_request("compare_spider", {"before": self.v1, "after": self.v1}),
        ]
        for result in results:
            self.assertResult(result)
        self.assertIsNone(handle_spider_request("unknown", {}))


if __name__ == "__main__":
    unittest.main()
