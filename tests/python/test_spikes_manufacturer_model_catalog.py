# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from spikes.manufacturer_model_catalog import (
    CANONICAL_CATEGORIES,
    ManufacturerCatalogError,
    catalog,
    coverage_summary,
    propose_user_model_admission,
    search_catalog,
    validate_catalog,
)


class ManufacturerModelCatalogTests(unittest.TestCase):
    def test_catalog_is_valid_non_runnable_and_mutation_isolated(self) -> None:
        rows = catalog()
        self.assertEqual(validate_catalog(rows)["issues"], [])
        self.assertTrue(all(row["runnable"] is False for row in rows))
        self.assertTrue(all(row["redistribution_approved"] is False for row in rows))
        rows[0]["mpn"] = "changed-by-caller"
        self.assertNotEqual(catalog()[0]["mpn"], "changed-by-caller")

    def test_expected_curated_counts_and_overlap_are_exact(self) -> None:
        summary = coverage_summary()
        self.assertEqual(summary["unique_records"], 133)
        self.assertEqual(summary["runnable_records"], 0)
        self.assertEqual(summary["counts"], {
            "opamp": 14,
            "bjt": 20,
            "npn": 10,
            "pnp": 10,
            "mosfet": 20,
            "nmos": 12,
            "pmos": 8,
            "ganfet": 18,
            "sicfet": 16,
            "mesfet": 4,
            "pin_diode": 9,
            "diode": 29,
            "schottky": 10,
            "controller": 12,
            "pwm": 12,
        })
        self.assertEqual(summary["counts"]["bjt"], summary["counts"]["npn"] + summary["counts"]["pnp"])
        self.assertEqual(summary["counts"]["mosfet"], summary["counts"]["nmos"] + summary["counts"]["pmos"])
        self.assertGreater(
            summary["counts"]["diode"],
            summary["counts"]["pin_diode"] + summary["counts"]["schottky"],
        )
        self.assertTrue(all(not met for met in summary["targets_met"].values()))
        self.assertEqual(summary["shortfalls"]["mesfet"], 96)

    def test_common_and_precision_opamps_are_traceable(self) -> None:
        opamps = {row["mpn"]: row for row in search_catalog(category="operational_amplifier")}
        for mpn in ("LM358", "LM741", "TL072", "NE5532", "OPA197", "AD811", "ADA4522-1"):
            self.assertIn(mpn, opamps)
        self.assertEqual(opamps["LM358"]["model_download_url"], "https://www.ti.com/lit/zip/SNOM268")
        self.assertEqual(opamps["LM741"]["model_download_url"], "https://www.ti.com/lit/zip/SNOM211B")
        self.assertEqual(opamps["AD811"]["model_readiness"], "manufacturer_clickthrough_unreviewed")
        self.assertFalse(opamps["AD811"]["redistribution_approved"])

    def test_search_filters_canonical_overlapping_categories(self) -> None:
        npn = search_catalog(manufacturer="Nexperia", category="npn")
        self.assertEqual(len(npn), 5)
        self.assertTrue(all({"bjt", "npn"}.issubset(row["categories"]) for row in npn))
        pmos = search_catalog(category="p_channel_mosfet")
        self.assertEqual(len(pmos), 8)
        self.assertTrue(all({"mosfet", "pmos"}.issubset(row["categories"]) for row in pmos))
        pin = search_catalog("BAR64", category="pin")
        self.assertEqual(len(pin), 5)
        self.assertTrue(all({"diode", "pin_diode"}.issubset(row["categories"]) for row in pin))

    def test_catalog_validation_rejects_promoted_or_placeholder_rows(self) -> None:
        promoted = catalog()[:1]
        promoted[0]["runnable"] = True
        promoted[0]["redistribution_approved"] = True
        result = validate_catalog(promoted)
        self.assertFalse(result["valid"])
        self.assertTrue(any("must not be runnable" in issue for issue in result["issues"]))
        self.assertTrue(any("redistribution must remain unapproved" in issue for issue in result["issues"]))

        placeholder = catalog()[:1]
        placeholder[0]["mpn"] = "GENERIC-MPN500"
        result = validate_catalog(placeholder)
        self.assertFalse(result["valid"])
        self.assertTrue(any("placeholder MPN" in issue for issue in result["issues"]))

    def test_user_model_evidence_is_hashed_without_admission_or_copy(self) -> None:
        payload = b"untrusted vendor model bytes; never parsed or executed\n"
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            source = Path(directory) / "LM358_vendor.lib"
            source.write_bytes(payload)
            result = propose_user_model_admission(
                source,
                manufacturer="Texas Instruments",
                mpn="LM358",
                categories=("opamp",),
                license_evidence=("https://www.ti.com/legal/terms-conditions/terms-of-sale.html",),
            )
            self.assertEqual(result["state"], "unapproved")
            self.assertEqual(result["original_sha256"], sha256(payload).hexdigest())
            self.assertEqual(result["original_size_bytes"], len(payload))
            self.assertEqual(result["original_path"], str(source.resolve()))
            self.assertFalse(result["copied"])
            self.assertFalse(result["parsed"])
            self.assertFalse(result["imported"])
            self.assertFalse(result["executed"])
            self.assertFalse(result["runnable"])
            self.assertEqual(list(Path(directory).iterdir()), [source])

    def test_user_model_evidence_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            source = Path(directory) / "model.lib"
            source.write_text("model", encoding="ascii")
            with self.assertRaisesRegex(ManufacturerCatalogError, "non-placeholder"):
                propose_user_model_admission(
                    source,
                    manufacturer="Example",
                    mpn="placeholder-mpn500",
                    categories=("opamp",),
                    license_evidence=("license.txt",),
                )
            with self.assertRaisesRegex(ManufacturerCatalogError, "license-evidence"):
                propose_user_model_admission(
                    source,
                    manufacturer="Texas Instruments",
                    mpn="LM358",
                    categories=("opamp",),
                    license_evidence=(),
                )
            with self.assertRaisesRegex(ManufacturerCatalogError, "Unknown"):
                propose_user_model_admission(
                    source,
                    manufacturer="Texas Instruments",
                    mpn="LM358",
                    categories=("not_a_real_family",),
                    license_evidence=("license.txt",),
                )

    def test_all_categories_have_explicit_gap_targets(self) -> None:
        summary = coverage_summary()
        self.assertEqual(set(summary["counts"]), set(CANONICAL_CATEGORIES))
        self.assertEqual(set(summary["shortfalls"]), set(CANONICAL_CATEGORIES))
        for category in CANONICAL_CATEGORIES:
            self.assertEqual(summary["counts"][category] + summary["shortfalls"][category], 100)


if __name__ == "__main__":
    unittest.main()
