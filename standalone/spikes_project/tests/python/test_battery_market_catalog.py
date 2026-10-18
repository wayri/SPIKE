# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path
import unittest
from urllib.parse import urlparse


CATALOG_PATH = (
    Path(__file__).resolve().parents[2]
    / "studio"
    / "library"
    / "battery-market-catalog.json"
)


class BatteryMarketCatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        cls.records = cls.catalog["records"]

    def test_schema_ids_and_market_coverage(self):
        self.assertEqual("spikes/battery-market-catalog/v1", self.catalog["schema"])
        self.assertGreaterEqual(len(self.records), 15)
        ids = [record["id"] for record in self.records]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(ids))
        chemistries = {record["chemistry"] for record in self.records}
        for expected in (
            "nickel-cadmium",
            "nickel-metal hydride",
            "silver oxide",
            "zinc-air",
            "lithium thionyl chloride",
            "valve-regulated lead-acid AGM",
        ):
            self.assertIn(expected, chemistries)

    def test_records_are_sourced_unqualified_ratings(self):
        forbidden_keys = {
            "assignedFullModel",
            "fittedModel",
            "modelParameters",
            "qualified",
            "qualification",
        }
        for record in self.records:
            with self.subTest(record=record["id"]):
                self.assertEqual("datasheet_seed_unqualified", record["status"])
                self.assertFalse(forbidden_keys.intersection(record))
                self.assertGreater(record["nominalV"], 0)
                self.assertIsInstance(record["rechargeable"], bool)
                self.assertTrue(record["manufacturer"])
                self.assertTrue(record["mpn"])
                self.assertTrue(record["format"])
                self.assertTrue(record["applicationTags"])
                source = urlparse(record["sourceURL"])
                self.assertEqual("https", source.scheme)
                self.assertTrue(source.netloc)
                gaps = " ".join(record["evidenceGaps"]).lower()
                for missing in ("ocv", "impedance", "thermal", "aging"):
                    self.assertIn(missing, gaps)

    def test_capacity_is_never_a_context_free_number(self):
        for record in self.records:
            if "capacity" not in record:
                continue
            with self.subTest(record=record["id"]):
                capacity = record["capacity"]
                self.assertGreater(capacity["value"], 0)
                self.assertIn(capacity["unit"], {"mAh", "Ah"})
                self.assertTrue(capacity["kind"])
                self.assertTrue(capacity["testConditions"])


if __name__ == "__main__":
    unittest.main()
