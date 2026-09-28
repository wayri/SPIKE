# SPDX-License-Identifier: Apache-2.0
"""KiCad layer forms must not create false openEMS admission errors."""
from __future__ import annotations

import unittest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

from extensions.openems_suite.engine import _validate_openems_case, prepare_openems_case, run_openems_case
from extensions.openems_suite.openems_validation import validate_port_geometry
from python.spike_core.contracts import AnalysisSpec
from tests.python.test_external_engines import openems_design


class OpenemsRealBoardLayersTests(unittest.TestCase):
    def test_mask_paste_layers_and_via_tuple_are_not_unmapped_copper(self):
        design = openems_design()
        design.pads = [{"id": "pad-1", "net_name": "RF", "at": [10.0, 0.0],
                        "size": [1.0, 1.0], "shape": "rect",
                        "layers": ["F.Cu", "F.Paste", "F.Mask"]}]
        design.vias = [{"id": "via-1", "net_name": "RF", "at": [10.0, 0.0],
                        "size": 0.6, "drill": 0.3, "layers": ("F.Cu", "B.Cu")}]
        spec = AnalysisSpec(net_names=["RF"], frequency_start_hz=1e8,
                            frequency_stop_hz=1e9, frequency_points=11)
        validation = _validate_openems_case(design, spec)
        self.assertNotIn("OPENEMS_LAYER_MAPPING_REQUIRED",
                         {issue["code"] for issue in validation["errors"]})
        self.assertTrue(validation["can_prepare"])
        self.assertFalse(validation["can_run"])  # Explicit port and via model still required.

    def test_unmapped_copper_layer_still_fails(self):
        design = openems_design()
        design.pads = [{"id": "pad-1", "net_name": "RF", "at": [10.0, 0.0],
                        "size": [1.0, 1.0], "shape": "rect",
                        "layers": ["In5.Cu", "F.Mask"]}]
        spec = AnalysisSpec(net_names=["RF"], frequency_start_hz=1e8,
                            frequency_stop_hz=1e9, frequency_points=11)
        validation = _validate_openems_case(design, spec)
        self.assertIn("OPENEMS_LAYER_MAPPING_REQUIRED",
                      {issue["code"] for issue in validation["errors"]})

    def test_missing_stackup_reports_primary_blocker_once(self):
        design = openems_design()
        design.stackup = []
        spec = AnalysisSpec(net_names=["RF"], frequency_start_hz=1e8,
                            frequency_stop_hz=1e9, frequency_points=11)
        validation = _validate_openems_case(design, spec)
        codes = {issue["code"] for issue in validation["errors"]}
        self.assertIn("OPENEMS_STACKUP_REQUIRED", codes)
        self.assertNotIn("OPENEMS_LAYER_MAPPING_REQUIRED", codes)

    def test_unfilled_zone_intent_is_translation_blocker(self):
        design = openems_design()
        design.zones = [{"id": "zone:intent", "net_name": "RF", "layer": "F.Cu",
                         "source_kind": "zone_outline_intent", "points": [],
                         "source_zone_outline_paths_mm": [[[0, 0], [1, 0], [1, 1]]]}]
        spec = AnalysisSpec(net_names=["RF"], frequency_start_hz=1e8,
                            frequency_stop_hz=1e9, frequency_points=11)
        validation = _validate_openems_case(design, spec)
        self.assertNotIn("OPENEMS_GEOMETRY_INVALID",
                         {issue["code"] for issue in validation["errors"]})
        self.assertIn("GEOMETRY_ZONE_FILL_MISSING",
                      {issue["code"] for issue in validation["run_blockers"]})
        self.assertFalse(validation["can_run"])

    def test_via_tuple_can_supply_port_contact(self):
        design = openems_design()
        design.tracks = []
        design.vias = [
            {"id": "rf-via", "net_name": "RF", "at": [0.0, 0.0],
             "size": 0.6, "drill": 0.3, "layers": ("F.Cu", "B.Cu")},
            {"id": "gnd-via", "net_name": "GND", "at": [2.0, 0.0],
             "size": 0.6, "drill": 0.3, "layers": ("F.Cu", "B.Cu")},
        ]
        spec = AnalysisSpec(net_names=["RF", "GND"])
        port = {"start": [0.0, 0.0, 0.0], "stop": [2.0, 0.0, 0.0]}
        self.assertEqual(validate_port_geometry(design, spec, [port], 0.5), [])

    def test_setup_only_blocks_known_geometry_loss_before_launch(self):
        design = openems_design()
        design.vias = [{"id": "via-1", "net_name": "RF", "at": [10.0, 0.0],
                        "size": 0.6, "drill": 0.3, "layers": ("F.Cu", "B.Cu")}]
        spec = AnalysisSpec(net_names=["RF"], frequency_start_hz=1e8,
                            frequency_stop_hz=1e9, frequency_points=11)
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"SPIKE_STATE_HOME": str(Path(directory) / "state")}
        ):
            case = prepare_openems_case(design, spec, Path(directory) / "case")
            self.assertEqual(case["status"], "prepared_review_required")
            result = run_openems_case(case["case_dir"], setup_only=True)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["validation"]["run_blockers"][0]["code"],
                         "GEOMETRY_VIA_PADSTACK_UNQUALIFIED")


if __name__ == "__main__":
    unittest.main()
