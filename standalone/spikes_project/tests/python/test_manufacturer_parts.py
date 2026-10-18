# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile
import unittest
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "studio/python"))

from spikes_studio.document import Document
from spikes_studio.manufacturer_parts import (
    CONTRACT, ManufacturerPartError, ModelUnavailableError, as_component_record,
    find_record, format_record, install, is_placeable, load_catalog,
    prepare_install, query, source_pins, store_vendor_model, validate_catalog,
)


class ManufacturerPartsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()
        cls.records = cls.catalog["records"]

    def test_focused_seed_is_exact_sourced_and_not_claimed_complete(self):
        self.assertEqual(self.catalog["contract"], CONTRACT)
        self.assertGreaterEqual(len(self.records), 20)
        self.assertIn("not a complete", self.catalog["scope"])
        self.assertIn("No manufacturer SPICE is redistributed", self.catalog["limitations"])
        manufacturers = {record["manufacturer"] for record in self.records}
        self.assertTrue({
            "Murata", "Yageo", "Texas Instruments", "Analog Devices",
            "Infineon", "STMicroelectronics", "Vishay", "TDK", "Littelfuse",
        }.issubset(manufacturers))
        identities = {(r["manufacturer"], r["mpn"]) for r in self.records}
        self.assertEqual(len(identities), len(self.records))
        for required in ("LM358P", "LM741CN/NOPB", "LM393P", "IRLZ44NPBF", "STP55NF06", "TSAL6200"):
            self.assertEqual(find_record(required, self.records)["mpn"], required)

    def test_every_record_has_units_pins_ratings_and_official_https_provenance(self):
        allowed_hosts = (
            "murata.com", "yageo.com", "ti.com", "analog.com", "infineon.com",
            "st.com", "vishay.com", "tdk.com", "littelfuse.com",
            "onsemi.com", "nexperia.com",
            "panasonic.com", "kyocera-avx.com", "samsungsem.com", "coilcraft.com", "pulseelectronics.com", "isabellenhuette.de", "murata.co.jp",
        )
        for record in self.records:
            source = record["source"]
            self.assertTrue(source["url"].startswith("https://"), record["mpn"])
            hostname = urlparse(source['url']).hostname or ''
            self.assertTrue(any(hostname == host or hostname.endswith('.'+host) for host in allowed_hosts), record['mpn'])
            self.assertRegex(source["accessed_on"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertTrue(source["fields"])
            self.assertTrue(record["ratings"])
            self.assertGreaterEqual(len(record["pins"]), 2)
            self.assertTrue(record["nominal"]["unit"])

    def test_local_search_combines_text_and_exact_filters(self):
        rows = query(self.records, "10 kohm", manufacturer="Yageo", category="resistor")
        self.assertEqual([r["mpn"] for r in rows], ["RC0075FR-0710KL"])
        rows = query(self.records, "lm3", manufacturer="Texas Instruments", readiness="vendor_model_required")
        self.assertEqual({r["mpn"] for r in rows}, {"LM358P", "LM393P"})
        with self.assertRaises(ManufacturerPartError): query(self.records, "x" * 513)

    def test_only_sourced_nominal_rlc_are_placeable(self):
        placeable = [r for r in self.records if is_placeable(r)]
        self.assertGreaterEqual(len(placeable), 7)
        self.assertEqual({r["category"] for r in placeable}, {"resistor", "capacitor", "inductor"})
        for record in placeable:
            adapted = as_component_record(record)
            self.assertEqual(adapted["exact_mpn"], record["mpn"])
            self.assertIn("ideal", adapted["limitations"].lower())
            self.assertEqual(source_pins(record), ["P", "N"])
        for mpn in ("LM358P", "LM741CN/NOPB", "LM393P", "B57237S0259M000", "0218002.MXP"):
            with self.assertRaisesRegex(ModelUnavailableError, "no bundled executable model"):
                source_pins(find_record(mpn, self.records))

    def test_exact_mpn_passive_install_uses_existing_atomic_insertion(self):
        doc = Document.from_netlist("Manufacturer install\nV1 in 0 1\nRLOAD in 0 1k\n.op\n.end\n")
        before = doc.data["source"]
        preview = prepare_install(doc, "RC0075FR-0710KL", {"P": "in", "N": "0"})
        self.assertEqual(doc.data["source"], before)
        self.assertEqual(preview["manufacturer_part"]["mpn"], "RC0075FR-0710KL")
        resistor = install(doc, "RC0075FR-0710KL", {"P": "in", "N": "0"})
        capacitor = install(doc, "GRM21BR61A106KE19L", {"P": "in", "N": "0"})
        physical=next(p for p in doc.data['components'] if p['ref'].startswith('XCAT2:'))
        self.assertEqual(physical['parameters']['manufacturer_part']['mpn'],'GRM21BR61A106KE19L')
        self.assertEqual(physical['limits']['voltage_v'],10)
        self.assertEqual(resistor["refs"], ["XCAT1"])
        self.assertEqual(capacitor["refs"], ["XCAT2"])
        self.assertIn("manufacturer_yageo_rc0075fr-0710kl", doc.data["source"])
        self.assertIn("manufacturer_murata_grm21br61a106ke19l", doc.data["source"])
        self.assertEqual(doc.data["metadata"]["library_browser"]["recent"][0], "manufacturer.murata.grm21br61a106ke19l")
        doc.undo()
        self.assertNotIn("manufacturer_murata_grm21br61a106ke19l", doc.data["source"])

    @unittest.skipUnless(os.environ.get("SPIKES_TEST_LIBRARY"), "Native SPIKES library not configured")
    def test_inserted_exact_passives_execute_through_native_solver(self):
        from python.spikes.native_runner import run_native_project
        from python.spikes.netlist import parse_netlist
        doc = Document.from_netlist("Manufacturer native smoke\nV1 supply 0 1\n.op\n.end\n")
        install(doc, "RC0075FR-0710KL", {"P": "supply", "N": "0"})
        install(doc, "GRM21BR61A106KE19L", {"P": "supply", "N": "0"})
        result = run_native_project(
            parse_netlist(doc.data["source"], native_extensions=True),
            os.environ["SPIKES_TEST_LIBRARY"],
        ).to_dict()
        self.assertEqual(result["status"], "completed")
        self.assertAlmostEqual(result["data"]["node_voltage_v"]["supply"], 1.0, places=9)

    def test_user_supplied_vendor_model_preserves_hash_license_and_exact_pins(self):
        source = ".subckt LM358_EXACT 1OUT 1INM 1INP VM 2INP 2INM 2OUT VP\nR1 1OUT VM 1k\n.ends LM358_EXACT\n"
        expected_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        doc = Document.from_netlist("Vendor intake\nV1 in 0 1\nR1 in 0 1k\n.op\n.end\n")
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            path = Path(directory) / "lm358-user.lib"
            path.write_text(source, encoding="utf-8", newline="")
            key = store_vendor_model(
                doc, path, "LM358P", "TI download terms supplied with this local file",
                "https://www.ti.com/lit/zip/slcj009",
            )
        self.assertEqual(key, expected_hash)
        review = doc.data["metadata"]["manufacturer_models"][key]
        self.assertEqual(review["content_sha256"], expected_hash)
        self.assertEqual(review["original_source"], source)
        self.assertEqual(review["provenance"]["part_number"], "LM358P")
        self.assertEqual(review["provenance"]["source_url"], "https://www.ti.com/lit/zip/slcj009")
        self.assertEqual(review["license"]["declared_by_user"], "TI download terms supplied with this local file")
        self.assertEqual(review["subcircuits"][0]["pins"], ["1OUT", "1INM", "1INP", "VM", "2INP", "2INM", "2OUT", "VP"])
        self.assertEqual(review["execution"], "not_approved")
        self.assertEqual(review["fitted_draft_status"], "not_qualified")

    def test_preview_states_model_limits_and_source(self):
        text = format_record(find_record("LM393P", self.records))
        self.assertIn("vendor_model_required", text)
        self.assertIn("Official source: https://www.ti.com/", text)
        self.assertIn("Fitted drafts are not qualified", text)
        self.assertIn("1OUT", text)

    def test_catalog_validation_rejects_tampering(self):
        payload = json.loads(json.dumps(self.catalog))
        payload["records"][0]["source"]["url"] = "file:///tmp/fake"
        with self.assertRaises(ManufacturerPartError): validate_catalog(payload)
        payload = json.loads(json.dumps(self.catalog))
        payload["records"][1]["mpn"] = payload["records"][0]["mpn"]
        payload["records"][1]["manufacturer"] = payload["records"][0]["manufacturer"]
        with self.assertRaisesRegex(ManufacturerPartError, "Duplicate"):
            validate_catalog(payload)


if __name__ == "__main__":
    unittest.main()
