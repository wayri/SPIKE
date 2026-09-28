import unittest
import json
from pathlib import Path


from python.spike_core.contracts import DesignIR
from python.spike_core.emi import (
    EMI_PREFLIGHT_CONTRACT,
    EMI_SETUP_CONTRACT,
    EMI_WORKFLOW_CONTRACT,
    screen_emi_setup,
    validate_emi_setup,
)
from python.spike_core.solver_plugins import default_solver_registry


class EmiWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.design = DesignIR(
            name="EMI fixture",
            source_format="fixture",
            layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
            nets=[{"id": 1, "name": "SW"}, {"id": 2, "name": "CLK"}, {"id": 3, "name": "GND"}],
            tracks=[
                {"start": [0, 0], "end": [20, 0], "width": 0.5, "layer": "F.Cu", "net_name": "SW"},
                {"start": [0, 3], "end": [30, 3], "width": 0.2, "layer": "F.Cu", "net_name": "CLK"},
            ],
            pads=[
                {"position": [0, 0], "size": [1, 1], "layer": "F.Cu", "net_name": "SW"},
                {"position": [0, 3], "size": [1, 1], "layer": "F.Cu", "net_name": "CLK"},
            ],
            zones=[{"layer": "B.Cu", "net_name": "GND", "outline": [[-2, -2], [32, -2], [32, 5], [-2, 5]]}],
            stackup=[
                {"name": "F.Cu", "type": "copper", "thickness": 0.035},
                {"name": "dielectric 1", "type": "core", "thickness": 1.53, "epsilon_r": 4.2, "loss_tangent": 0.02},
                {"name": "B.Cu", "type": "copper", "thickness": 0.035},
            ],
        )
        self.solvers = default_solver_registry().catalog()
        self.setup = {
            "contract": EMI_SETUP_CONTRACT,
            "selected_nets": ["SW", "CLK"],
            "return_nets": ["GND"],
            "requested_analyses": ["conducted_screening", "near_field", "far_field"],
            "frequency": {"start_hz": 1e6, "stop_hz": 1e9, "points": 101},
            "environment": {"kind": "free_space"},
            "mesh": {"resolution_mm": 0.25, "padding_cells": 8},
            "max_solver_time_s": 3600,
            "excitation": {
                "mode": "explicit_ports",
                "ports": [{
                    "id": "P1", "name": "Input", "start": [0, 0, 0], "stop": [0, 0, -1],
                    "direction": "z", "impedance_ohm": 50, "excite": True,
                }],
            },
            "net_metrics": [
                {"net": "SW", "source": "transient", "dv_dt_v_per_s": 2e9, "di_dt_a_per_s": 5e8, "peak_current_a": 8, "loop_area_mm2": 90, "return_discontinuities": 2},
                {"net": "CLK", "source": "transient", "dv_dt_v_per_s": 1e9, "di_dt_a_per_s": 1e7, "peak_current_a": 0.05, "loop_area_mm2": 10, "return_discontinuities": 0},
            ],
        }

    def test_preflight_separates_screening_from_solver_readiness(self):
        result = validate_emi_setup(self.design, self.setup, self.solvers)
        self.assertEqual(result["contract"], EMI_PREFLIGHT_CONTRACT)
        self.assertTrue(result["can_screen"])
        self.assertTrue(result["can_prepare"])
        if result["can_run"]:
            self.assertNotIn("EMI_SOLVER_UNAVAILABLE", {item["code"] for item in result["issues"]})
            far_field = next(item for item in result["stages"] if item["id"] == "far_field")
            self.assertEqual(far_field["state"], "reference_fixture_validated")
        else:
            self.assertIn("EMI_SOLVER_UNAVAILABLE", {item["code"] for item in result["issues"]})
        self.assertEqual(result["validity"]["model_status"], "screening_only")

    def test_chamber_preview_preserved_without_claiming_fixture_physics(self):
        setup = {**self.setup, "chamber": {"distance_m": 3, "orientation": "upright", "polarization": "vertical"}}
        result = validate_emi_setup(self.design, setup, self.solvers)
        self.assertEqual(result["normalized"]["chamber"]["orientation"], "upright")
        self.assertEqual(result["normalized"]["chamber"]["table_height_m"], .8)
        self.assertIn("EMI_CHAMBER_PREVIEW", {item["code"] for item in result["issues"]})
        self.assertTrue(result["can_prepare"])

    def test_invalid_chamber_dimensions_block_case_preparation(self):
        for value in [-3, float("nan"), float("inf"), True]:
            with self.subTest(value=value):
                result = validate_emi_setup(self.design, {**self.setup, "chamber": {"distance_m": value}}, self.solvers)
                self.assertFalse(result["can_prepare"])
                self.assertIn("EMI_CHAMBER_RANGE", {item["code"] for item in result["issues"]})

    def test_radiated_emissions_reference_profiles_are_metadata_only(self):
        selections = [
            *({"id": "cispr-25-2021", "classification": classification} for classification in ("1", "2", "3", "4", "5")),
            {"id": "cispr-32-2015-amd1-2019", "classification": "A"},
            {"id": "cispr-32-2015-amd1-2019", "classification": "B"},
            *({"id": edition, "platform": platform}
              for edition in ("mil-std-461h-2026-re102", "mil-std-461g-2015-re102")
              for platform in ("ground", "surface_ship", "submarine", "aircraft", "space")),
        ]
        schema = json.loads((Path(__file__).resolve().parents[2] / "schemas" / "emi-setup-v1.schema.json").read_text(encoding="utf-8"))
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            validator = None
        else:
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema)
        baseline = validate_emi_setup(self.design, self.setup, self.solvers)
        for selection in selections:
            with self.subTest(selection=selection):
                setup = {**self.setup, "radiated_emissions_standard": selection}
                if validator is not None:
                    validator.validate(setup)
                result = validate_emi_setup(self.design, setup, self.solvers)
                self.assertEqual(result["can_run"], baseline["can_run"])
                self.assertEqual(result["normalized"]["radiated_emissions_standard"], selection)
                self.assertEqual(result["reference_standard"]["comparison_status"], "unavailable")
                self.assertEqual(result["reference_standard"]["limit_data_status"], "not_bundled")
                self.assertFalse(result["reference_standard"]["compliance_available"])
                self.assertFalse(screen_emi_setup(self.design, setup, self.solvers)["provenance"]["compliance_prediction"])

    def test_invalid_radiated_emissions_references_fail_closed(self):
        cases = [
            ({"id": "cispr-25-2021", "classification": "A"}, "EMI_STANDARD_CLASS"),
            ({"id": "cispr-32-2015-amd1-2019", "classification": "1"}, "EMI_STANDARD_CLASS"),
            ({"id": "mil-std-461h-2026-re102"}, "EMI_STANDARD_PLATFORM"),
            ({"id": "mil-431"}, "EMI_STANDARD_NOT_RE"),
            ({"id": "mil-std-461i-re102", "platform": "ground"}, "EMI_STANDARD_UNKNOWN"),
            ({"id": [], "platform": "ground"}, "EMI_STANDARD_UNKNOWN"),
            ({"id": "cispr-32-2015-amd1-2019", "classification": "A", "limit_dbuv_m": 0}, "EMI_STANDARD_INVALID"),
            (None, "EMI_STANDARD_INVALID"),
        ]
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            validator = None
        else:
            schema = json.loads((Path(__file__).resolve().parents[2] / "schemas" / "emi-setup-v1.schema.json").read_text(encoding="utf-8"))
            validator = Draft202012Validator(schema)
        for selection, code in cases:
            with self.subTest(selection=selection):
                if validator is not None:
                    self.assertFalse(validator.is_valid({**self.setup, "radiated_emissions_standard": selection}))
                result = validate_emi_setup(self.design, {**self.setup, "radiated_emissions_standard": selection}, self.solvers)
                self.assertFalse(result["can_prepare"])
                self.assertIsNone(result["reference_standard"])
                self.assertIn(code, {item["code"] for item in result["issues"]})

    def test_screening_is_traceable_and_does_not_claim_field_results(self):
        result = screen_emi_setup(self.design, self.setup, self.solvers)
        self.assertEqual(result["contract"], EMI_WORKFLOW_CONTRACT)
        self.assertEqual(result["status"], "completed_screening_only")
        self.assertEqual(result["screening"]["recommended_nets"][0]["net"], "SW")
        self.assertFalse(result["provenance"]["field_solver_executed"])
        self.assertFalse(result["provenance"]["compliance_prediction"])
        self.assertEqual(result["screening"]["recommended_nets"][0]["geometry"]["tracks"], 1)

    def test_unknown_net_and_missing_metrics_block_workflow(self):
        setup = {**self.setup, "selected_nets": ["MISSING"], "net_metrics": []}
        result = validate_emi_setup(self.design, setup, self.solvers)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["can_screen"])
        self.assertIn("EMI_NET_UNKNOWN", {item["code"] for item in result["issues"]})

    def test_empty_dynamic_metrics_do_not_produce_a_ranking(self):
        setup = {
            **self.setup,
            "net_metrics": [
                {"net": "SW", "loop_area_mm2": 90},
                {"net": "CLK", "loop_area_mm2": 10},
            ],
        }
        result = screen_emi_setup(self.design, setup, self.solvers)
        self.assertEqual(result["status"], "blocked")
        self.assertIsNone(result["screening"])
        self.assertIn("EMI_DYNAMIC_METRICS_EMPTY", {item["code"] for item in result["preflight"]["issues"]})


if __name__ == "__main__":
    unittest.main()
