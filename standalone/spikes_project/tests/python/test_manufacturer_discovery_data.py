# SPDX-License-Identifier: Apache-2.0
"""Contract checks for the sourced manufacturer-discovery catalog."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = (
    PROJECT_ROOT / "studio" / "library" / "manufacturer-discovery-v1.json"
)

EXPECTED_MANUFACTURERS = {
    "Analog Devices",
    "Texas Instruments",
    "Infineon",
    "Monolithic Power Systems",
    "Wolfspeed",
    "Vishay",
    "Nordic Semiconductor",
    "Arduino",
    "Microchip",
    "Atmel (legacy)",
    "Littelfuse",
    "STMicroelectronics",
    "Allegro MicroSystems",
    "NXP Semiconductors",
    "Renesas",
    "Lattice Semiconductor",
    "onsemi",
    "Nexperia",
    "ROHM Semiconductor",
}

OFFICIAL_HOSTS = {
    "Analog Devices": {"www.analog.com"},
    "Texas Instruments": {"www.ti.com"},
    "Infineon": {"www.infineon.com"},
    "Monolithic Power Systems": {"www.monolithicpower.com"},
    "Wolfspeed": {"www.wolfspeed.com"},
    "Vishay": {"www.vishay.com"},
    "Nordic Semiconductor": {"www.nordicsemi.com"},
    "Arduino": {"docs.arduino.cc"},
    "Microchip": {"www.microchip.com"},
    "Atmel (legacy)": {"www.microchip.com"},
    "Littelfuse": {"www.littelfuse.com"},
    "STMicroelectronics": {"www.st.com"},
    "Allegro MicroSystems": {"www.allegromicro.com"},
    "NXP Semiconductors": {"www.nxp.com"},
    "Renesas": {"www.renesas.com"},
    "Lattice Semiconductor": {"www.latticesemi.com"},
    "onsemi": {"www.onsemi.com"},
    "Nexperia": {"www.nexperia.com"},
    "ROHM Semiconductor": {"www.rohm.com"},
}


class ManufacturerDiscoveryDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        cls.records = cls.catalog["records"]

    def test_versioned_contract_and_explicit_boundaries(self) -> None:
        self.assertEqual(self.catalog["contract"], "spikes/manufacturer-discovery/v1")
        self.assertEqual(self.catalog["generated_on"], "2026-10-20")
        self.assertIn("product identities", self.catalog["scope"])
        self.assertIn("not electrical models", self.catalog["scope"])
        limitations = " ".join(self.catalog["limitations"]).casefold()
        for boundary in ("does not establish", "does not qualify", "no model"):
            self.assertIn(boundary, limitations)

    def test_catalog_has_broad_requested_coverage(self) -> None:
        self.assertGreaterEqual(len(self.records), 200)
        manufacturers = {record["manufacturer"] for record in self.records}
        self.assertEqual(manufacturers, EXPECTED_MANUFACTURERS)
        counts = {
            manufacturer: sum(
                record["manufacturer"] == manufacturer for record in self.records
            )
            for manufacturer in EXPECTED_MANUFACTURERS
        }
        self.assertGreaterEqual(counts["Analog Devices"], 10)
        self.assertGreaterEqual(counts["Texas Instruments"], 10)
        self.assertGreaterEqual(counts["Infineon"], 10)
        self.assertTrue(all(count >= 6 for count in counts.values()))

    def test_record_identity_and_fields_are_unique_and_bounded(self) -> None:
        required = {
            "id",
            "manufacturer",
            "part_number",
            "category",
            "description",
            "product_url",
            "model_url",
            "model_status",
            "checked_on",
        }
        allowed = required | {"source_urls"}
        ids = set()
        manufacturer_parts = set()
        for record in self.records:
            self.assertEqual(set(record), required if "source_urls" not in record else allowed)
            for key in required - {"model_url"}:
                self.assertIsInstance(record[key], str)
                self.assertTrue(record[key].strip(), (record["id"], key))
            self.assertIn(record["checked_on"], {"2026-10-19", "2026-10-20"})
            self.assertLessEqual(len(record["description"]), 160)
            self.assertNotIn(record["id"], ids)
            ids.add(record["id"])
            identity = (
                record["manufacturer"].casefold(),
                record["part_number"].casefold(),
            )
            self.assertNotIn(identity, manufacturer_parts)
            manufacturer_parts.add(identity)

    def test_links_are_https_and_on_official_manufacturer_hosts(self) -> None:
        for record in self.records:
            expected_hosts = OFFICIAL_HOSTS[record["manufacturer"]]
            urls = [record["product_url"]]
            if record["model_url"] is not None:
                urls.append(record["model_url"])
            source_urls = record.get("source_urls", [])
            self.assertIsInstance(source_urls, list)
            urls.extend(source_urls)
            for url in urls:
                parsed = urlparse(url)
                self.assertEqual(parsed.scheme, "https", (record["id"], url))
                self.assertIn(parsed.hostname, expected_hosts, (record["id"], url))
                self.assertTrue(parsed.path, (record["id"], url))

    def test_model_status_is_explicit_and_consistent(self) -> None:
        statuses = {"model_not_reviewed", "source_identified_not_qualified"}
        identified_sources = 0
        for record in self.records:
            self.assertIn(record["model_status"], statuses)
            if record["model_url"] is None:
                self.assertEqual(record["model_status"], "model_not_reviewed")
            else:
                self.assertIsInstance(record["model_url"], str)
                self.assertEqual(
                    record["model_status"], "source_identified_not_qualified"
                )
                identified_sources += 1
        self.assertGreaterEqual(identified_sources, 1)

    def test_catalog_makes_no_executable_or_qualification_claims(self) -> None:
        forbidden = (
            "validated model",
            "qualified model",
            "executable model",
            "simulation-ready",
            "firmware emulation",
        )
        for record in self.records:
            prose = f"{record['category']} {record['description']}".casefold()
            for claim in forbidden:
                self.assertNotIn(claim, prose, record["id"])

    def test_representative_exact_identities_are_present(self) -> None:
        identities = {
            (record["manufacturer"], record["part_number"])
            for record in self.records
        }
        for identity in {
            ("Analog Devices", "AD620"),
            ("Texas Instruments", "TPS5430"),
            ("Infineon", "IRLZ44N"),
            ("Nordic Semiconductor", "nRF52840"),
            ("Arduino", "ABX00080"),
            ("Microchip", "PIC16F877A"),
            ("STMicroelectronics", "STM32F407VG"),
            ("Lattice Semiconductor", "LFE5U-45F-6BG381C"),
            ("onsemi", "CAT24C256"),
            ("Nexperia", "BAS316"),
            ("ROHM Semiconductor", "BH2220FVM"),
        }:
            self.assertIn(identity, identities)

    def test_dated_expansion_is_real_identity_metadata_not_renamed_models(self) -> None:
        added = [record for record in self.records if record["checked_on"] == "2026-10-20"]
        self.assertGreaterEqual(len(added), 100)
        self.assertGreaterEqual(len({record["manufacturer"] for record in added}), 16)
        for record in added:
            self.assertEqual(record["model_status"], "model_not_reviewed")
            self.assertIsNone(record["model_url"])
            self.assertIn("identity", record["description"].casefold())


if __name__ == "__main__":
    unittest.main()
