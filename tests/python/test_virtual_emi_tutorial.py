"""Checks for the hash-bound virtual EMI documentation renderer.

SPDX-License-Identifier: MIT
Copyright (c) 2026 SigHarmonic
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import render_virtual_emi_tutorial as tutorial


class VirtualEmiTutorialTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "examples/emerge").mkdir(parents=True)
        self.run_dir = self.root / "run"
        self.run_dir.mkdir()
        self.board = self.root / "examples/emerge/antenna_example.kicad_pcb"
        self.board.write_bytes(b"test-only board")
        self.board_hash = sha256(self.board.read_bytes()).hexdigest()
        self.values = {
            "virtual_emi_setup.json": {
                "selected_nets": ["RF"], "return_nets": ["GND"],
                "frequency": {"start_hz": 3e9, "stop_hz": 4.2e9, "points": 2},
                "chamber": {"distance_m": 3},
                "net_metrics": [{"source": "illustrative"}],
            },
            "antenna_run.json": {"parameters": {
                "signal_net": "RF", "return_net": "GND", "frequency_start_hz": 3e9,
                "frequency_stop_hz": 4.2e9, "frequency_points": 2,
                "mesh_resolution_mm": 2,
            }},
            "emi-preflight.json": {"contract": "spike/emi-preflight/v1", "can_screen": True,
                                   "can_run": False, "status": "ready_to_screen"},
            "emi-screening.json": {"status": "completed_screening_only",
                                   "provenance": {"field_solver_executed": False,
                                                  "compliance_prediction": False},
                                   "screening": {"recommended_nets": [{"net": "RF", "score": 0}]}},
            "emerge_emi_evidence.json": {"board_sha256": self.board_hash,
                                         "status": "completed", "model_status": "unvalidated",
                                         "solver": "EMerge/test", "design_digest_sha256": "design-digest",
                                         "frequencies_hz": [3e9, 4.2e9], "s11_db": [-1, -2],
                                         "issue_codes": ["EMERGE_EMI_NOT_COMPLIANCE"]},
            "emerge_emi_result.json": {"status": "completed", "model_status": "unvalidated",
                                       "provenance": {"solver": "EMerge/test",
                                                      "design_digest_sha256": "design-digest"},
                                       "fields": {"radiation": {
                                           "patterns_3d": [{}, {}],
                                           "cuts": [
                                               {"angles_deg": [0, 180], "relative_amplitude_db": [0, -3]},
                                               {"angles_deg": [0, 180], "relative_amplitude_db": [0, -2]},
                                           ]}}},
        }
        for name, value in self.values.items():
            parent = self.root / "examples/emerge" if name in {"virtual_emi_setup.json", "antenna_run.json"} else self.run_dir
            (parent / name).write_text(json.dumps(value), encoding="utf-8")

    def _render(self):
        with patch.object(tutorial, "ROOT", self.root), patch.object(tutorial, "BOARD", self.board), \
             patch.object(tutorial, "EXPECTED_BOARD_SHA256", self.board_hash):
            return tutorial.render(self.run_dir, self.run_dir / "view.html")

    def test_renders_executed_but_noncompliant_review(self):
        summary = self._render()
        self.assertEqual(summary["frequency_count"], 2)
        self.assertFalse(summary["compliance_prediction"])
        self.assertIn("not an EMI-tab screenshot", (self.run_dir / "view.html").read_text(encoding="utf-8"))

    def test_rejects_board_and_result_mismatches(self):
        evidence = self.values["emerge_emi_evidence.json"]
        evidence["board_sha256"] = "wrong"
        (self.run_dir / "emerge_emi_evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "pinned KiCad board"):
            self._render()
        evidence["board_sha256"] = self.board_hash
        evidence["issue_codes"] = []
        (self.run_dir / "emerge_emi_evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unvalidated evidence"):
            self._render()


if __name__ == "__main__":
    unittest.main()
