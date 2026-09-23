# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Actual generated multi-board topology and translation, not executed CFD."""
import tempfile
from pathlib import Path
import unittest

from python.spike_core.openfoam_fan_fixture import build_fan_heated_fixture


class MultiBoardFixtureTests(unittest.TestCase):
    def test_two_boards_share_air_but_not_heat_source_zones(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "two"
            result = build_fan_heated_fixture(root, board_count=2, divisions=2,
                delta_t_s=.002, end_time_s=2, write_interval_steps=10)
            self.assertEqual(result["prepared"]["status"], "prepared_runnable_case")
            self.assertEqual(set(result["meshes"]), {"board", "board2", "air"})
            request = result["request"]
            self.assertEqual(sum(item["power_w"] for item in request["heat_sources"]), .2)
            self.assertEqual({item["fv_option"]["cell_zone"] for item in request["heat_sources"]}, {"board_source", "board2_source"})
            self.assertEqual(len(request["interfaces"]), 2)
            for region, peer, patch in (("board", "air", "air_board"), ("board2", "air", "air_board2"), ("air", "board2", "board2_air")):
                boundary = (root / "case/constant" / region / "polyMesh/boundary").read_text()
                self.assertIn(peer, boundary)
                self.assertIn(patch, boundary)
            upper_t = (root / "case/0/board2/T").read_text()
            self.assertIn("turbulentTemperatureRadCoupledMixed", upper_t)
            self.assertIn("solidThermo", upper_t)
            self.assertIn("board2_source", (root / "case/constant/board2/polyMesh/cellZones").read_text())
            self.assertIn("625000", (root / "case/system/board2/fvOptions").read_text())
            self.assertEqual(request["numerics"]["delta_t_s"], .002)
            self.assertEqual(request["numerics"]["end_time_s"], 2)
            self.assertEqual(request["numerics"]["write_interval_steps"], 10)
            self.assertFalse(result["qualification"]["executed_cfd"])

    def test_default_one_board_remains_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            result = build_fan_heated_fixture(Path(directory) / "one", divisions=1)
            self.assertEqual(result["prepared"]["status"], "prepared_runnable_case")
            self.assertEqual(set(result["meshes"]), {"board", "air"})
            self.assertEqual(result["request"]["numerics"]["end_time_s"], 10)

    def test_bad_controls_rejected_before_output_creation(self):
        for controls in ({"board_count": 3}, {"board_count": True}, {"delta_t_s": 0},
                         {"end_time_s": float("nan")}, {"delta_t_s": 11},
                         {"write_interval_steps": 0}, {"write_interval_steps": True}):
            with self.subTest(controls=controls), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "bad"
                with self.assertRaises(ValueError):
                    build_fan_heated_fixture(root, **controls)
                self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
