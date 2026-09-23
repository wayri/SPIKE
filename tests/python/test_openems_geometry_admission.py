# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Regressions for integrated guard, including executable existing-driver evidence."""
import ast
import copy
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.openems_geometry_admission import screen_geometry, verify_screen_binding
from tests.python.test_openems_far_field import far_field_design, far_field_spec
from python.spike_core.openems_adapter_source import OPENEMS_DRIVER
from python.spike_core.external_engines import (
    ExternalEngineDescriptor, prepare_openems_case, run_openems_case,
)


class GeometryAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.design, self.spec = far_field_design(), far_field_spec()

    def codes(self):
        return {issue["code"] for issue in screen_geometry(self.design, self.spec)["issues"]}

    def pad(self, **options):
        return {"id": "pad-rf", "net_name": "RF", "at": [2, 3], "size": [4, 1],
                "shape": "rect", "layer": "F.Cu", **options}

    def test_simple_fixture_is_only_screened_not_qualified(self):
        report = screen_geometry(self.design, self.spec)
        self.assertTrue(report["screen_passed"])
        self.assertFalse(report["production_qualified"])
        self.assertFalse(report["field_accuracy_validated"])
        self.assertTrue(report["integrated_into_runtime"])
        verify_screen_binding(report, self.design, self.spec)

    def test_antipad_cannot_disappear(self):
        self.design.zones = [{"id": "plane", "net_name": "GND",
                              "points": [[0, 0], [10, 0], [10, 10], [0, 10]],
                              "holes": [[[4, 4], [6, 4], [6, 6], [4, 6]]]}]
        self.assertIn("GEOMETRY_COPPER_CUTOUT_UNMODELED", self.codes())

    def test_custom_and_curved_pads_rejected(self):
        for options, code in [({"shape": "custom"}, "GEOMETRY_PAD_CONTOUR_UNQUALIFIED"),
                              ({"shape": "roundrect"}, "GEOMETRY_PAD_CONTOUR_UNQUALIFIED"),
                              ({"rotation": "90"}, "GEOMETRY_PAD_ROTATION_INVALID"),
                              ({"drill": .3}, "GEOMETRY_PADSTACK_UNMODELED")]:
            with self.subTest(options=options):
                self.design.pads = [self.pad(**options)]
                self.assertIn(code, self.codes())

    def test_selected_vs_unselected_scope(self):
        self.design.pads = [self.pad(shape="custom", net_name="UNSELECTED")]
        self.assertTrue(screen_geometry(self.design, self.spec)["screen_passed"])
        self.spec.net_names.append("UNSELECTED")
        self.assertIn("GEOMETRY_PAD_CONTOUR_UNQUALIFIED", self.codes())

    def test_source_ready_bond_is_still_not_modeled(self):
        for status in ("ready", "unresolved", "explicit", "inferred"):
            self.design.component_bonds = [{"id": "bond", "net_name": "RF", "status": status}]
            self.assertIn("GEOMETRY_COMPONENT_BOND_UNMODELED", self.codes())
        self.design.component_bonds[0]["enabled"] = False
        self.assertNotIn("GEOMETRY_COMPONENT_BOND_UNMODELED", self.codes())

    def test_outline_via_and_track_paths_fail_closed(self):
        self.design.metadata["board_outline_mm"] = [[0, 0], [3, 0], [3, 4], [0, 4]]
        self.design.vias = [{"id": "via", "net_name": "RF", "at": [1, 1]}]
        self.design.tracks[0]["path"] = [[0, 0], [10, 10], [20, 0]]
        self.assertTrue({"GEOMETRY_BOARD_OUTLINE_UNMODELED", "GEOMETRY_VIA_PADSTACK_UNQUALIFIED",
                         "GEOMETRY_TRACK_PATH_UNMODELED"}.issubset(self.codes()))

    def test_empty_selection_and_invalid_units_fail(self):
        self.spec.net_names = []
        self.design.units = "inch"
        self.assertTrue({"GEOMETRY_SELECTION_REQUIRED", "GEOMETRY_UNITS_UNSUPPORTED"}.issubset(self.codes()))

    def test_digests_bind_sources_selection_and_report(self):
        report = screen_geometry(self.design, self.spec)
        original = copy.deepcopy(self.design)
        self.design.tracks[0]["width"] = 2
        with self.assertRaises(ValueError):
            verify_screen_binding(report, self.design, self.spec)
        self.design = original
        report["production_qualified"] = True
        with self.assertRaises(ValueError):
            verify_screen_binding(report, self.design, self.spec)

    def test_existing_driver_preserves_pad_rotation(self):
        # Execute only three pure geometry helpers from the actual driver AST.
        parsed = ast.parse(OPENEMS_DRIVER)
        helpers = ast.Module(body=[item for item in parsed.body if isinstance(item, ast.FunctionDef)
                                  and item.name in {"point", "polygon_coordinates", "pad_polygon"}],
                             type_ignores=[])
        scope = {"math": math}
        exec(compile(helpers, "existing-driver-geometry", "exec"), scope)
        lower = scope["pad_polygon"]
        self.assertNotEqual(lower(self.pad()), lower(self.pad(rotation=90)))
        # True 90-degree rotation swaps extent 4 x 1 to 1 x 4.
        polygon = lower(self.pad(rotation=90))
        self.assertAlmostEqual(max(polygon[0]) - min(polygon[0]), 1)
        self.design.pads = [self.pad(rotation=90)]
        self.assertNotIn("GEOMETRY_PAD_ROTATION_UNMODELED", self.codes())

    def test_prepared_geometry_loss_blocks_run_but_preserves_inspection(self):
        self.design.pads = [self.pad(shape="roundrect")]
        ready = ExternalEngineDescriptor(id="external.openems", name="openEMS",
            role="test", license="GPL-3.0-or-later", homepage="https://docs.openems.de/",
            state="reference_validated")
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,
            {"SPIKE_STATE_HOME": str(Path(directory) / "state")}), patch(
            "python.spike_core.external_engines._openems_descriptor", return_value=ready):
            case = Path(directory) / "case"
            prepared = prepare_openems_case(self.design, self.spec, case)
            validation = prepared["validation"]
            self.assertTrue(validation["can_prepare"])
            self.assertFalse(validation["can_run"])
            self.assertIn("GEOMETRY_PAD_CONTOUR_UNQUALIFIED",
                          {item["code"] for item in validation["run_blockers"]})
            self.assertEqual(prepared["status"], "prepared_review_required")
            with patch("python.spike_core.external_engines._run_isolated_python",
                       side_effect=RuntimeError("inspection reached worker")) as worker:
                self.assertEqual(run_openems_case(case)["status"], "blocked")
                worker.assert_not_called()
                with self.assertRaisesRegex(RuntimeError, "inspection reached worker"):
                    run_openems_case(case, setup_only=True)
                worker.assert_called_once()

    def test_run_recomputes_screen_from_authenticated_geometry(self):
        self.design.pads = [self.pad(shape="roundrect")]
        ready = ExternalEngineDescriptor(id="external.openems", name="openEMS",
            role="test", license="GPL-3.0-or-later", homepage="https://docs.openems.de/",
            state="reference_validated")
        clean = screen_geometry(far_field_design(), self.spec)
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,
            {"SPIKE_STATE_HOME": str(Path(directory) / "state")}), patch(
            "python.spike_core.external_engines._openems_descriptor", return_value=ready):
            case = Path(directory) / "case"
            # Simulate a formerly permissive prepared report. The actual geometry
            # is unchanged and authenticated; runtime must not trust this report.
            with patch("python.spike_core.external_engines.screen_geometry", return_value=clean):
                prepared = prepare_openems_case(self.design, self.spec, case)
            self.assertTrue(prepared["validation"]["can_run"])
            with patch("python.spike_core.external_engines._run_isolated_python") as worker:
                actual = run_openems_case(case)
            self.assertEqual(actual["status"], "blocked")
            self.assertFalse(actual["validation"]["geometry_screen"]["screen_passed"])
            worker.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
