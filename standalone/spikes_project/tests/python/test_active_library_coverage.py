# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "studio/python"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from spikes_studio.active_library_coverage import (
    ACTIVE_CATEGORIES,
    EVIDENCE_CONTRACT,
    LOGIC_MANIFEST_CONTRACT,
    audit_active_library,
    format_coverage_report,
)
from spikes_studio.component_catalog import catalog as generic_catalog
from spikes_studio.manufacturer_parts import load_catalog


_DIGEST = "a" * 64


def evidence(*, execution="passed", qualification="passed"):
    return {
        "contract": EVIDENCE_CONTRACT,
        "model_sha256": _DIGEST,
        "execution": {
            "status": execution,
            "backend": "native-spikes-test",
            "artifact": "validation/model-execution.json",
            "artifact_sha256": "b" * 64,
            "checked_on": "2026-10-12",
        },
        "qualification": {
            "status": qualification,
            "scope": "DC, AC, transient, supply and temperature envelope",
            "reviewer": "knowledgeable human reviewer",
            "artifact": "validation/model-qualification.json",
            "artifact_sha256": "c" * 64,
            "checked_on": "2026-10-12",
        },
    }


class ActiveLibraryCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.default_records = load_catalog()["records"]

    def test_default_catalog_reports_discovery_but_no_active_execution(self):
        result = audit_active_library(self.default_records)
        self.assertEqual(set(result["categories"]), set(ACTIVE_CATEGORIES))
        self.assertGreaterEqual(result["categories"]["opamp"]["discovered"], 9)
        self.assertGreaterEqual(result["categories"]["bjt"]["discovered"], 5)
        self.assertGreaterEqual(result["categories"]["npn"]["discovered"], 3)
        self.assertGreaterEqual(result["categories"]["pnp"]["discovered"], 2)
        self.assertGreaterEqual(result["categories"]["mosfet"]["discovered"], 6)
        for item in result["categories"].values():
            self.assertEqual(item["target"], 100)
            self.assertEqual(item["executable"], 0)
            self.assertEqual(item["qualified"], 0)
            self.assertEqual(item["status"], "not_met")
        self.assertEqual(result["logic_54_74"]["discovered"], 20)
        self.assertIsNone(result["logic_54_74"]["target"])
        self.assertEqual(result["logic_54_74"]["status"], "unknown_universe")

    def test_generic_parameter_grids_do_not_count_as_mpns(self):
        baseline = audit_active_library(self.default_records)
        augmented = audit_active_library(self.default_records + generic_catalog()["records"])
        self.assertEqual(augmented["distinct_mpn_count"], baseline["distinct_mpn_count"])
        self.assertEqual(augmented["categories"], baseline["categories"])

    def test_digest_bound_evidence_promotes_only_the_exact_mpn(self):
        record = deepcopy(next(r for r in self.default_records if r["category"] == "operational_amplifier"))
        record["coverage_evidence"] = evidence()
        result = audit_active_library([record])
        self.assertEqual(result["categories"]["opamp"]["discovered"], 1)
        self.assertEqual(result["categories"]["opamp"]["executable"], 1)
        self.assertEqual(result["categories"]["opamp"]["qualified"], 1)
        self.assertEqual(result["categories"]["opamp"]["gap"], 99)

    def test_malformed_or_optimistic_statuses_fail_closed(self):
        record = deepcopy(next(r for r in self.default_records if r["category"] == "mosfet"))
        record["model"]["readiness"] = "executable_and_qualified"
        record["coverage_evidence"] = evidence(execution="ready")
        result = audit_active_library([record])
        self.assertEqual(result["categories"]["mosfet"]["discovered"], 1)
        self.assertEqual(result["categories"]["mosfet"]["executable"], 0)
        self.assertEqual(result["categories"]["mosfet"]["qualified"], 0)
        self.assertTrue(any("executable claim excluded" in issue for issue in result["issues"]))

        record["coverage_evidence"] = evidence(qualification="approved")
        result = audit_active_library([record])
        self.assertEqual(result["categories"]["mosfet"]["executable"], 1)
        self.assertEqual(result["categories"]["mosfet"]["qualified"], 0)
        self.assertTrue(any("qualification claim excluded" in issue for issue in result["issues"]))

    def test_duplicate_package_rows_collapse_by_manufacturer_and_mpn(self):
        record = deepcopy(next(r for r in self.default_records if r["category"] == "operational_amplifier"))
        duplicate = deepcopy(record)
        duplicate["package"] = "duplicate package presentation"
        result = audit_active_library([record, duplicate])
        self.assertEqual(result["categories"]["opamp"]["discovered"], 1)
        self.assertTrue(any("duplicate rows collapsed" in issue for issue in result["issues"]))

    def test_54_74_completeness_requires_an_authoritative_manifest(self):
        logic_records = [r for r in self.default_records if r["category"] == "logic_ic"]
        expected = [{"manufacturer": r["manufacturer"], "mpn": r["mpn"]} for r in logic_records]
        manifest = {
            "contract": LOGIC_MANIFEST_CONTRACT,
            "source": {
                "url": "https://example.invalid/authoritative-logic-index",
                "accessed_on": "2026-10-12",
                "document": "Authoritative enumerated 54/74 product universe",
            },
            "expected": expected,
        }
        discovery_only = audit_active_library(logic_records, logic_manifest=manifest)["logic_54_74"]
        self.assertIsNone(discovery_only["target"])
        self.assertTrue(discovery_only["manifest_verified"])
        self.assertEqual(discovery_only["missing_mpn_count"], 0)
        self.assertEqual(discovery_only["missing_executable_mpn_count"], len(logic_records))
        self.assertEqual(discovery_only["missing_qualified_mpn_count"], len(logic_records))
        self.assertEqual(discovery_only["status"], "incomplete")
        self.assertEqual(discovery_only["qualification_status"], "incomplete")

        executable_records = deepcopy(logic_records)
        for record in executable_records:
            record["coverage_evidence"] = evidence(qualification="not_reviewed")
        complete = audit_active_library(executable_records, logic_manifest=manifest)["logic_54_74"]
        self.assertEqual(complete["status"], "complete")
        self.assertEqual(complete["missing_executable_mpn_count"], 0)
        self.assertEqual(complete["qualification_status"], "incomplete")
        self.assertEqual(complete["missing_qualified_mpn_count"], len(logic_records))

        incomplete = audit_active_library(logic_records[:-1], logic_manifest=manifest)["logic_54_74"]
        self.assertEqual(incomplete["status"], "incomplete")
        self.assertEqual(incomplete["missing_mpn_count"], 1)
        self.assertEqual(incomplete["missing_executable_mpn_count"], len(logic_records))

    def test_text_report_states_all_three_levels(self):
        text = format_coverage_report(audit_active_library(self.default_records))
        self.assertIn("discovery", text)
        self.assertIn("executable", text)
        self.assertIn("qualified", text)
        self.assertIn("no invented numeric target", text)


if __name__ == "__main__":
    unittest.main()
