# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import verify_si_pair_geometry as verifier
from tests.python import test_si_pair_geometry as fixtures


class PairRetentionVerifierTests(unittest.TestCase):
    def fixture(self):
        design, request = fixtures.PairGeometryTests().fixture()
        return design, verifier.prepare_pair_geometry(design, request)

    def rebind(self, result):
        result.pop("preparation_digest_sha256")
        result["preparation_digest_sha256"] = verifier.content_digest(result)

    def test_complete_source_passes_without_channel_claim(self):
        design, result = self.fixture()
        row = verifier.check_preparation(design, result)
        self.assertEqual(row["retention_checks"], "passed")
        self.assertFalse(row["channel_extracted"])

    def test_rehashed_dropped_source_is_rejected(self):
        design, result = self.fixture()
        result["routes"]["signal"]["sources"]["tracks"].clear()
        self.rebind(result)
        with self.assertRaisesRegex(ValueError, "retained tracks"):
            verifier.check_preparation(design, result)

    def test_rehashed_interval_gap_is_rejected(self):
        design, result = self.fixture()
        result["track_partitions"][0]["interval"][0] = [1, 2]
        self.rebind(result)
        with self.assertRaisesRegex(ValueError, "interval lost"):
            verifier.check_preparation(design, result)

    def test_rehashed_source_mutation_is_rejected(self):
        design, result = self.fixture()
        result["source"] = deepcopy(result["source"])
        result["source"]["source_digest"] = "0" * 64
        self.rebind(result)
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            verifier.check_preparation(design, result)

    def test_qualification_claim_rejected(self):
        design, result = self.fixture()
        result["production_qualified"] = True
        with self.assertRaisesRegex(ValueError, "must not claim"):
            verifier.check_preparation(design, result)

    def test_source_pin_checked_before_import(self):
        with patch.object(Path, "read_bytes", return_value=b"not the source"):
            with self.assertRaisesRegex(ValueError, "pinned source identity"):
                verifier.evaluate_board("marble")


if __name__ == "__main__":
    unittest.main()
