# SPDX-License-Identifier: Apache-2.0
"""Non-solving setup checks against the component adapter admission contract."""

import copy
import unittest
from unittest.mock import patch

from python.spike_core.component_thermal import validate_component_thermal
from python.spike_core.service_assembly_handlers import ASSEMBLY_SCOPED_METHODS
from python.spike_core.service_simulation_handlers import handle_simulation_request


def request():
    return {"scenario": {"mode": "steady_state"},
            "components": [{"component_ref": "U1", "power_w": 2}]}


class ComponentThermalPreflightTests(unittest.TestCase):
    def test_missing_path_then_explicit_path_ready_without_solving(self):
        data = request()
        original = copy.deepcopy(data)
        with patch("python.spike_core.component_thermal.estimate_lumped_thermal_network", side_effect=AssertionError("must not estimate")), \
             patch("python.spike_core.component_thermal.estimate_surface_thermal_network", side_effect=AssertionError("must not estimate")), \
             patch("python.spike_core.thermal_network._solve_linear", side_effect=AssertionError("must not solve")):
            result = validate_component_thermal(data)
            self.assertFalse(result["can_solve"])
            self.assertEqual(result["issues"][0]["code"], "THERMAL_NETWORK_AMBIENT_PATH_REQUIRED")
            self.assertEqual(result["issues"][0]["path"], "components[0]")
            self.assertEqual(data, original)
            data["components"][0]["resistance_top_c_per_w"] = 8
            self.assertEqual(validate_component_thermal(data), {"can_solve": True, "issues": []})

    def test_surface_conduction_connection_is_not_itself_a_sink(self):
        data = request()
        data["components"].append({"component_ref": "U2", "power_w": 0})
        data["surfaces"] = [{"id": "contact", "object_ref": "U1", "surface": "case", "kind": "conduction",
                             "target_ref": "U2", "resistance_c_per_w": 2}]
        blocked = validate_component_thermal(data)
        self.assertFalse(blocked["can_solve"])
        self.assertEqual(len(blocked["issues"]), 2)
        data["surfaces"].append({"id": "cooling", "object_ref": "U2", "surface": "whole", "kind": "convection",
                                 "heat_transfer_coefficient_w_m2_k": 10, "area_mm2": 200})
        with patch("python.spike_core.thermal_network._solve_linear", side_effect=AssertionError("must not solve")):
            self.assertTrue(validate_component_thermal(data)["can_solve"])
        data["surfaces"][1]["enabled"] = False
        self.assertFalse(validate_component_thermal(data)["can_solve"])

    def test_unit_bearing_and_nonfinite_values_rejected(self):
        for value in ("2W", -1, float("nan"), float("inf"), True, None):
            with self.subTest(value=value):
                data = request()
                data["components"][0].update(power_w=value, resistance_top_c_per_w=8)
                self.assertFalse(validate_component_thermal(data)["can_solve"])
        for value in (None, [], {"scenario": []}, {"components": []}):
            self.assertFalse(validate_component_thermal(value)["can_solve"])

    def test_transient_missing_capacity_and_invalid_controls(self):
        data = request()
        data["components"][0]["resistance_top_c_per_w"] = 8
        data["scenario"]["mode"] = "transient"
        self.assertFalse(validate_component_thermal(data)["can_solve"])
        data["components"][0]["thermal_capacitance_j_per_c"] = 4
        self.assertTrue(validate_component_thermal(data)["can_solve"])
        for run in ({"end_time_s": 0}, {"write_interval_s": "1 s"},
                    {"end_time_s": 1e7, "write_interval_s": 0.001}):
            with self.subTest(run=run):
                data["scenario"]["run"] = run
                self.assertFalse(validate_component_thermal(data)["can_solve"])

    def test_admitted_surface_coefficient_overflow_is_rejected(self):
        data = request()
        data["surfaces"] = [{"id": "sink", "object_ref": "U1", "surface": "whole", "kind": "convection",
                             "heat_transfer_coefficient_w_m2_k": 1e300, "area_mm2": 1e300}]
        self.assertFalse(validate_component_thermal(data)["can_solve"])

    def test_existing_surface_dense_work_budget_blocks_without_factorization(self):
        data = request()
        data["components"].append({"component_ref": "U2", "power_w": 0})
        data["surfaces"] = [{"id": "contact", "object_ref": "U1", "surface": "case", "kind": "conduction",
                             "target_ref": "U2", "resistance_c_per_w": 2},
                            {"id": "sink", "object_ref": "U2", "surface": "case", "kind": "conduction",
                             "target_ref": "ambient", "resistance_c_per_w": 2}]
        with patch("python.spike_core.thermal_network.MAX_SURFACE_DENSE_WORK", 1), \
             patch("python.spike_core.thermal_network._solve_linear", side_effect=AssertionError("must not solve")):
            self.assertFalse(validate_component_thermal(data)["can_solve"])
        self.assertTrue(validate_component_thermal(data)["can_solve"])

    def test_worker_dispatch_and_scope_registration(self):
        self.assertIn("validate_component_thermal", ASSEMBLY_SCOPED_METHODS)
        result = handle_simulation_request("validate_component_thermal", request(), assembly_scope={}, solver_registry=None)
        self.assertTrue(result["ok"])
        self.assertFalse(result["result"]["can_solve"])
        self.assertNotIn("nodes", result["result"])


if __name__ == "__main__":
    unittest.main()
