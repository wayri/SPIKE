"""Independent checks for the illustrative Marble R293 topology tutorial.

SPDX-License-Identifier: MIT
Copyright (c) 2026 SigHarmonic
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from scripts.run_marble_r293_si_tutorial import (
    BOARD_SHA256, FPGA_NET, ILLUSTRATIVE_IBIS, PADS, PHY_NET, illustrative_channel,
    series_impedance_network, verify_board,
)
from python.spike_core.si_ibis import parse_ibis


class MarbleR293TutorialTests(unittest.TestCase):
    def test_illustrative_ibis_declares_required_file_component_and_input_fields(self):
        text = ILLUSTRATIVE_IBIS.read_text(encoding="utf-8")
        self.assertIn("[File Rev] 0.1", text)
        self.assertEqual(text.count("[Manufacturer] SigHarmonic Teaching Model"), 2)
        self.assertEqual(text.count("[Voltage Range] 1.8 1.7 1.9"), 2)
        inventory = parse_ibis(text, ILLUSTRATIVE_IBIS.name)
        self.assertEqual(set(inventory["components"]), {"EXAMPLE_PHY", "EXAMPLE_FPGA"})

    def test_series_resistor_two_port_matches_voltage_wave_oracle(self):
        network = series_impedance_network(np.array([0.0, 1e9]), 22.0)
        s = network.s_parameters()
        np.testing.assert_allclose(s[:, 1, 0], 100 / 122, atol=1e-15)
        np.testing.assert_allclose(s[:, 0, 0], 22 / 122, atol=1e-15)
        self.assertLessEqual(np.linalg.svd(s[0], compute_uv=False).max(), 1 + 1e-15)
        with self.assertRaises(ValueError):
            series_impedance_network(np.array([0.0]), -1.0)

    def test_cascaded_fitted_resistor_reduces_through_transfer(self):
        baseline = illustrative_channel(0.0)
        fitted = illustrative_channel(22.0)
        self.assertEqual(len(baseline.frequencies_hz), 513)
        ratio = abs(fitted.s_parameters()[0, 1, 0] / baseline.s_parameters()[0, 1, 0])
        self.assertAlmostEqual(20 * np.log10(ratio), -1.7240696875, delta=2e-6)

    def test_board_hash_and_four_pad_map_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            board = Path(directory) / "Marble.kicad_pcb"
            board.write_text("not the pinned board", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                verify_board(board)
            design_path = Path(directory) / "design.json"
            design = {"metadata": {"source_sha256": BOARD_SHA256},
                      "pads": [{"component_pad": key, "net_name": net} for key, net in PADS.items()],
                      "components": [{"reference": "R293", "pad_count": 2}],
                      "tracks": [{"net_name": PHY_NET}, {"net_name": FPGA_NET}],
                      "vias": [{"net_name": FPGA_NET}]}
            design_path.write_text(json.dumps(design), encoding="utf-8")
            with patch("scripts.run_marble_r293_si_tutorial._sha", return_value=BOARD_SHA256):
                self.assertEqual(verify_board(board, design_json=design_path)["pads"], PADS)
                design["pads"][-1]["net_name"] = PHY_NET
                design_path.write_text(json.dumps(design), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "pad-net map changed"):
                    verify_board(board, design_json=design_path)


if __name__ == "__main__":
    unittest.main()
