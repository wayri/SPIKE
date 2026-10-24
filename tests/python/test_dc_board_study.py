# SPDX-License-Identifier: Apache-2.0
"""Source-to-volume replay validates geometry, contacts and saved full fields."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from python.spike_core.dc_board_study import board_model, solve_board_model, validate_board_run, solve_source_board, validate_source_board_run
from tests.python.test_dc_board_source import source_model, FIXTURE


class BoardStudyTests(unittest.TestCase):
    def test_saved_source_model_fields_and_coverage_replay(self):
        model = board_model(source_model(), target_mm=1., max_cells=5000)
        before = deepcopy(model); run = solve_board_model(model)
        self.assertEqual(model, before)
        saved = json.loads(json.dumps(run)); validate_board_run(saved)
        self.assertEqual(saved["source_authentication"], "not_performed_by_pure_model_solver")
        self.assertFalse(saved["result"]["current_density_observable"]["complete_board_physical_volume"])
        for change in (lambda r: r["coverage"].__setitem__("complete_selected_geometry", False),
                       lambda r: r["coverage"]["volumes"][0].__setitem__("mesh_volume_mm3", 0.),
                       lambda r: r["source_model"]["contacts"][0].__setitem__("current_a", 2.),
                       lambda r: r["result"]["source_request"]["mesh"]["vertices"][0].__setitem__(0, 100.),
                       lambda r: r.__setitem__("source_authentication", "forged")):
            bad = deepcopy(saved); change(bad)
            with self.assertRaises(ValueError): validate_board_run(bad)

    def test_authenticated_source_wrapper_actual_fields_and_source_identity(self):
        prepared = source_model()
        config = {"contract": "spike/source-board-volume-study/v1", "source_path": str(FIXTURE),
                  "source_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), "net_names": ["VDD"],
                  "electrodes": prepared["source_evidence"]["electrodes"], "plating_thickness_mm": .025,
                  "conductivity_s_m": 5.8e7, "target_mm": 1., "max_cells": 5000}
        run = solve_source_board(config)
        validate_source_board_run(json.loads(json.dumps(run)))
        validate_board_run(json.loads(json.dumps(run["run"])))
        self.assertTrue(run["source_revalidated_after_solve"])
        self.assertTrue(run["source_evidence"]["native_via_inventory_authenticated"])
        self.assertFalse(run["full_board_pisi_ready"])
        changed = deepcopy(config); changed["source_sha256"] = "0"*64
        with self.assertRaises(ValueError): solve_source_board(changed)


if __name__ == "__main__": unittest.main()
