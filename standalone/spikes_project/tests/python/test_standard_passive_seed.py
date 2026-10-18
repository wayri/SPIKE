# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "studio/python"))

from spikes_studio.manufacturer_parts import load_catalog, validate_record
from spikes_studio.standard_passive_seed import records


class StandardPassiveSeedTests(unittest.TestCase):
    def test_records_are_valid_distinct_additions(self):
        additions = records()
        self.assertGreaterEqual(len(additions), 12)
        identities = {(r["manufacturer"].casefold(), r["mpn"].casefold()) for r in additions}
        self.assertEqual(len(identities), len(additions))
        self.assertEqual(len({r["id"] for r in additions}), len(additions))
        base = load_catalog(Path(__file__).resolve().parents[2] / "studio/library/manufacturer-parts-v1.json")["records"]
        self.assertTrue(identities.isdisjoint({(r["manufacturer"].casefold(), r["mpn"].casefold()) for r in base}))
        for row in additions:
            validate_record(row)
            self.assertEqual(row["source"]["accessed_on"], "2026-10-12")

    def test_model_readiness_is_fail_closed_for_kelvin_shunts(self):
        for row in records():
            if row["manufacturer"] == "Isabellenhuette":
                self.assertEqual(row["model"]["kind"], "none")
                self.assertEqual(row["model"]["readiness"], "vendor_model_required")
                self.assertEqual([p["role"] for p in row["pins"]], [
                    "force_positive", "sense_positive", "sense_negative", "force_negative"
                ])
            else:
                self.assertEqual(row["model"]["readiness"], "placeable_ideal_nominal")

    def test_precision_and_footprint_variety(self):
        rows = records()
        self.assertTrue(any(r["tolerance"].get("value") == 0.1 for r in rows))
        self.assertTrue(any("0402" in r["package"] for r in rows))
        self.assertTrue(any("0603" in r["package"] for r in rows))
        self.assertTrue({"resistor", "capacitor", "inductor"}.issubset({r["category"] for r in rows}))
        inductors = [r for r in rows if r["category"] == "inductor"]
        self.assertGreaterEqual(len(inductors), 4)
        self.assertTrue(all(r["nominal"]["unit"] == "H" for r in inductors))
        self.assertTrue(all(r["model"]["kind"] == "ideal_nominal_inductor" for r in inductors))

    def test_records_are_fresh(self):
        first = records()
        first[0]["nominal"]["value"] = -1
        self.assertGreater(records()[0]["nominal"]["value"], 0)


if __name__ == "__main__":
    unittest.main()
