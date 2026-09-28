# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""The volume opt-in must select the unique-source-area C approximation."""

import unittest
from unittest.mock import patch

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.peec_capacitance_dispatch import estimate_branch_capacitance


class CapacitanceDispatchTests(unittest.TestCase):
    def test_default_remains_legacy_and_volume_uses_source_area(self):
        design = DesignIR()
        legacy_spec = AnalysisSpec(mode="ac")
        volume_spec = AnalysisSpec(mode="ac", options={"peec_volume_extraction": "enabled"})
        with patch("python.spike_core.quasistatic_capacitance.estimate_branch_capacitance",
                   return_value="legacy") as legacy, patch(
                   "python.spike_core.quasistatic_copper_area.estimate_branch_capacitance",
                   return_value="source-area") as source_area:
            self.assertEqual(estimate_branch_capacitance(design, legacy_spec, []), "legacy")
            self.assertEqual(estimate_branch_capacitance(design, volume_spec, []), "source-area")
        legacy.assert_called_once_with(design, legacy_spec, [])
        source_area.assert_called_once_with(design, volume_spec, [])


if __name__ == "__main__":
    unittest.main()
