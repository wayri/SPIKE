# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
import json
from pathlib import Path
import tempfile
import unittest
from scripts.run_multiboard_cross_heating import prepare
from python.spike_core.openfoam_multiregion_execution import load_verified_runnable_case


class CrossHeatingPreparationTests(unittest.TestCase):
    def test_new_case_zeroes_only_upper_source_without_mutating_template(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request, result = prepare(root)
            powers = {item["solid_region_id"]: item["power_w"] for item in request["heat_sources"]}
            self.assertEqual(powers, {"board": .1, "board2": 0})
            upper = next(item for item in request["heat_sources"] if item["solid_region_id"] == "board2")
            self.assertEqual(upper["fv_option"]["volumetric_power_w_m3"], 0)
            template = json.loads((root / "template/case/spike_multiregion_case.json").read_text())
            self.assertEqual(next(item for item in template["heat_sources"] if item["solid_region_id"] == "board2")["power_w"], .1)
            self.assertNotEqual(template["request_digest"], result["manifest"]["request_digest"])
            load_verified_runnable_case(root / "template/case")
            load_verified_runnable_case(root / "case")


if __name__ == "__main__":
    unittest.main()
