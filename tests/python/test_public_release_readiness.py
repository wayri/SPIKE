# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path
import unittest

from python.spike_core.public_release_readiness import (
    BLOCKED_EXTERNAL,
    _schema_check,
    _version_check,
    evaluate_public_release,
)


ROOT = Path(__file__).resolve().parents[2]
REPORT = (
    ROOT / "artifacts" / "releases" / "public-rc-hardening-0.3.0-beta.1-v2"
    / "SPIKES-0.3.0-beta.1-release.json"
)


class PublicReleaseReadinessTests(unittest.TestCase):
    def test_version_and_schema_surfaces_are_coherent(self) -> None:
        self.assertEqual(_version_check(ROOT)["status"], "PASS")
        self.assertEqual(_schema_check(ROOT)["status"], "PASS")

    def test_current_candidate_is_technical_but_externally_blocked(self) -> None:
        report = evaluate_public_release(ROOT, engine_report=REPORT)
        self.assertEqual(report["status"], BLOCKED_EXTERNAL)
        self.assertTrue(report["technical_candidate"])
        self.assertFalse(report["public_distribution_authorized"])
        self.assertFalse(report["failures"])
        codes = {item["code"] for item in report["external_blockers"]}
        self.assertIn("PUBLIC_RELEASE_OWNERSHIP_APPROVAL_REQUIRED", codes)
        self.assertIn("PUBLIC_RELEASE_SIGNATURE_REQUIRED", codes)
        self.assertTrue(all(value is False for value in report["claim_boundary"].values()))


if __name__ == "__main__":
    unittest.main()
