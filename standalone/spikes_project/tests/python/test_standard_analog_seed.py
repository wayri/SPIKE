# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "studio/python"))

from spikes_studio.manufacturer_parts import load_catalog, validate_record
from spikes_studio.standard_analog_seed import records
from spikes_studio.component_library_choices import matching_parts


class StandardAnalogSeedTests(unittest.TestCase):
    def test_records_are_valid_distinct_non_executable_additions(self):
        additions = records()
        self.assertGreaterEqual(len(additions), 12)
        self.assertEqual(len({record["id"] for record in additions}), len(additions))
        identities = {
            (record["manufacturer"].casefold(), record["mpn"].casefold())
            for record in additions
        }
        self.assertEqual(len(identities), len(additions))

        existing = {
            (record["manufacturer"].casefold(), record["mpn"].casefold())
            for record in load_catalog(Path(__file__).resolve().parents[2] / 'studio/library/manufacturer-parts-v1.json')["records"]
        }
        self.assertTrue(identities.isdisjoint(existing))
        installed = {(r['manufacturer'].casefold(), r['mpn'].casefold()) for r in load_catalog()['records']}
        self.assertTrue(identities.issubset(installed))
        for record in additions:
            validate_record(record)
            self.assertEqual(record["model"]["kind"], "none")
            self.assertEqual(record["model"]["readiness"], "vendor_model_required")
            self.assertIn("Discovery/review", record["model"]["limitations"])
            self.assertEqual(record["source"]["accessed_on"], "2026-10-12")
            self.assertTrue(record["ratings"])

    def test_expected_analog_families_and_package_specific_pins_are_present(self):
        additions = records()
        categories = {record["category"] for record in additions}
        self.assertTrue({
            "operational_amplifier", "instrumentation_amplifier",
            "bipolar_transistor", "mosfet",
        }.issubset(categories))
        by_mpn = {record["mpn"]: record for record in additions}
        self.assertEqual(
            [(pin["number"], pin["name"]) for pin in by_mpn["INA128P"]["pins"]],
            [("1", "RG"), ("2", "IN-"), ("3", "IN+"), ("4", "V-"),
             ("5", "REF"), ("6", "OUT"), ("7", "V+"), ("8", "RG")],
        )
        self.assertEqual(by_mpn["2N3904BU"]["package"], "TO-92-3 LF (case 135AN)")
        self.assertEqual(
            [pin["name"] for pin in by_mpn["2N7002,215"]["pins"]],
            ["G", "S", "D"],
        )

    def test_records_returns_fresh_data(self):
        first = records()
        first[0]["model"]["readiness"] = "changed"
        self.assertEqual(records()[0]["model"]["readiness"], "vendor_model_required")

    def test_polarity_specific_component_choices(self):
        self.assertEqual(len(matching_parts('npn',records=records())),3)
        self.assertEqual(len(matching_parts('pnp',records=records())),2)


if __name__ == "__main__":
    unittest.main()
