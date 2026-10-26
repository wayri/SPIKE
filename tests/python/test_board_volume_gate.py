# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import json
import unittest

from scripts.parity_pisi_gate import names
from scripts.parity_board_volume_gate import build_report, suite, validate_report


class BoardVolumeGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = build_report()

    def test_exact_focused_suite_inventory(self):
        expected = names(suite())
        self.assertEqual(len(expected), 47)
        self.assertFalse(any("_FailedTest" in name for name in expected))

    def test_retained_report_and_forgery_controls(self):
        validate_report(json.loads(json.dumps(self.report, allow_nan=False)))
        changes = (
            lambda r: r["harmonic"][2]["source_request"].__setitem__("contacts", []),
            lambda r: r["generic_board_volume"]["compiled"]["coverage"].__setitem__(
                "complete_selected_geometry", False),
            lambda r: r["native_source_wrapper"]["source_evidence"].__setitem__("source_sha256", "0"*64),
        )
        for change in changes:
            forged = deepcopy(self.report); change(forged)
            with self.assertRaises(ValueError):
                validate_report(forged)


if __name__ == "__main__":
    unittest.main()
