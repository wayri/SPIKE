# SPDX-License-Identifier: MIT
"""Independent resistance and RC analytical oracles; synthetic SI-unit data."""

import copy
import math
import unittest
from unittest.mock import patch

from python.spike_core.component_thermal import run_component_thermal
from python.spike_core.service_simulation_handlers import handle_simulation_request


def request(mode="steady_state", step=1, end=60):
    return {"scenario": {"mode": mode, "ambient_temperature_c": 25, "run": {"end_time_s": end, "write_interval_s": step}},
            "components": [{"component_ref": "U1", "power_w": 6, "resistance_top_c_per_w": 10,
                            "resistance_bottom_c_per_w": 5, "thermal_capacitance_j_per_c": 3}]}


class ComponentThermalTests(unittest.TestCase):
    def test_parallel_paths_and_energy_balance(self):
        result = run_component_thermal(request())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["model_status"], "approximate")
        node = result["nodes"][0]
        self.assertAlmostEqual(node["temperature_c"], 45, places=12)
        self.assertAlmostEqual(node["heat_flow_top_w"], 2, places=12)
        self.assertAlmostEqual(node["heat_flow_bottom_w"], 4, places=12)
        self.assertAlmostEqual(result["summary"]["steady_energy_balance_error_w"], 0, places=12)
        self.assertFalse(result["provenance"]["field_result_produced"])

    def test_kelvin_per_watt_scaling_and_open_side(self):
        data = request()
        del data["components"][0]["resistance_bottom_c_per_w"]
        result = run_component_thermal(data)
        self.assertAlmostEqual(result["nodes"][0]["temperature_c"], 85)
        self.assertEqual(result["nodes"][0]["heat_flow_bottom_w"], 0)
        data["components"][0]["resistance_top_c_per_w"] = 1
        self.assertAlmostEqual(run_component_thermal(data)["nodes"][0]["temperature_c"], 31)

    def test_independent_components_keep_identity(self):
        data = request()
        data["components"].append({"component_ref": "R7", "power_w": 1, "resistance_top_c_per_w": 3})
        nodes = run_component_thermal(data)["nodes"]
        self.assertEqual([node["component_ref"] for node in nodes], ["U1", "R7"])
        self.assertAlmostEqual(nodes[1]["temperature_c"], 28)

    def test_transient_backward_euler_discrete_energy_and_steady_limit(self):
        result = run_component_thermal(request("transient", step=1, end=200))
        frames = result["transient"]
        self.assertEqual(frames[0]["temperatures_c"]["U1"], 25)
        for previous, current in zip(frames, frames[1:]):
            old = previous["temperatures_c"]["U1"]
            new = current["temperatures_c"]["U1"]
            storage_w = 3 * (new - old) / (current["time_s"] - previous["time_s"])
            self.assertAlmostEqual(storage_w + (new - 25) * 0.3, 6, places=11)
            self.assertGreaterEqual(new, old)
        self.assertAlmostEqual(result["nodes"][0]["temperature_c"], 45, places=6)

    def test_transient_cooling_and_first_order_convergence(self):
        errors = []
        exact = 25 + 20 * math.exp(-1)  # Req=10/3 K/W, C=3 J/K, tau=10 s.
        for step in (1, 0.5, 0.25):
            data = request("transient", step=step, end=10)
            data["components"][0].update(power_w=0, initial_temperature_c=45)
            result = run_component_thermal(data)
            values = [frame["temperatures_c"]["U1"] for frame in result["transient"]]
            self.assertTrue(all(25 <= after <= before for before, after in zip(values, values[1:])))
            errors.append(abs(values[-1] - exact))
        self.assertGreater(errors[0] / errors[1], 1.9)
        self.assertGreater(errors[1] / errors[2], 1.9)
        self.assertLess(errors[2], 0.1)

    def test_invalid_numeric_inputs_and_duplicate_refs_fail_closed(self):
        for field, bad in (("power_w", -1), ("power_w", float("nan")), ("power_w", True),
                           ("resistance_top_c_per_w", 0), ("resistance_bottom_c_per_w", -1),
                           ("thermal_capacitance_j_per_c", 0), ("initial_temperature_c", -274)):
            with self.subTest(field=field, bad=bad):
                data = request("transient")
                data["components"][0][field] = bad
                self.assertEqual(run_component_thermal(data)["status"], "blocked")
        data = request()
        duplicate = copy.deepcopy(data["components"][0])
        duplicate["component_ref"] = "u1"
        data["components"].append(duplicate)
        self.assertEqual(run_component_thermal(data)["status"], "blocked")

    def test_resource_limits_and_missing_transient_capacity(self):
        for data in (request("transient", step=0), request("transient", step=0.00001), request("transient", step=float("nan"))):
            self.assertEqual(run_component_thermal(data)["status"], "blocked")
        data = request("transient")
        del data["components"][0]["thermal_capacitance_j_per_c"]
        self.assertEqual(run_component_thermal(data)["status"], "blocked")
        data = request("transient", end=1000)
        data["components"] = [dict(data["components"][0], component_ref=f"U{i}") for i in range(101)]
        self.assertEqual(run_component_thermal(data)["status"], "blocked")

    def test_surface_convection_units_and_independent_sink_temperature(self):
        data = request()
        data["components"] = [{"component_ref": "U1", "power_w": 2}]
        data["surfaces"] = [{"id": "air", "object_ref": "U1", "surface": "+Z", "kind": "convection",
                             "area_mm2": 10000, "heat_transfer_coefficient_w_m2_k": 10, "ambient_temperature_c": 30}]
        result = run_component_thermal(data)
        self.assertEqual(result["status"], "completed", result)
        self.assertAlmostEqual(result["nodes"][0]["temperature_c"], 50)
        self.assertAlmostEqual(result["surfaces"][0]["heat_flow_w"], 2)
        self.assertAlmostEqual(result["summary"]["steady_energy_balance_error_w"], 0)

    def test_interobject_conduction_and_parallel_surface_paths(self):
        data = request()
        data["components"] = [{"component_ref": "U1", "power_w": 2}, {"component_ref": "sink", "power_w": 0}]
        data["surfaces"] = [
            {"id": "contact", "object_ref": "U1", "surface": "-Z", "kind": "conduction", "target_ref": "sink", "resistance_c_per_w": 5},
            {"id": "sink-air", "object_ref": "sink", "surface": "whole", "kind": "convection", "area_mm2": 10000, "heat_transfer_coefficient_w_m2_k": 10},
        ]
        result = run_component_thermal(data)
        self.assertEqual(result["status"], "completed", result)
        self.assertAlmostEqual(result["nodes"][0]["temperature_c"], 55)
        self.assertAlmostEqual(result["nodes"][1]["temperature_c"], 45)
        self.assertAlmostEqual(result["summary"]["steady_energy_balance_error_w"], 0, places=10)
        for item in result["surfaces"]:
            self.assertAlmostEqual(item["heat_flow_w"], 2)
        data["components"][0]["resistance_top_c_per_w"] = 15
        self.assertAlmostEqual(run_component_thermal(data)["nodes"][0]["temperature_c"], 40)

    def test_radiation_analytical_fourth_root_and_hot_surroundings(self):
        for power, sink in ((3, 25), (0, 90), (3, -273.15)):
            data = request()
            data["components"] = [{"component_ref": "U1", "power_w": power}]
            data["surfaces"] = [{"id": "rad", "object_ref": "U1", "surface": "whole", "kind": "radiation",
                                 "area_mm2": 20000, "emissivity": 0.8, "surroundings_temperature_c": sink}]
            result = run_component_thermal(data)
            self.assertEqual(result["status"], "completed", result)
            exact = ((sink + 273.15) ** 4 + power / (5.670374419e-8 * 0.8 * 0.02)) ** 0.25 - 273.15
            self.assertAlmostEqual(result["nodes"][0]["temperature_c"], exact, places=7)
            self.assertAlmostEqual(result["surfaces"][0]["heat_flow_w"], power, places=8)

    def test_mixed_boundary_transient_discrete_energy_and_step_convergence(self):
        ends = []
        for step in (0.2, 0.1, 0.05):
            data = request("transient", step=step, end=5)
            data["components"] = [{"component_ref": "U1", "power_w": 3, "thermal_capacitance_j_per_c": 2}]
            data["surfaces"] = [
                {"id": "conv", "object_ref": "U1", "surface": "+Z", "kind": "convection", "area_mm2": 20000, "heat_transfer_coefficient_w_m2_k": 10},
                {"id": "rad", "object_ref": "U1", "surface": "+Z", "kind": "radiation", "area_mm2": 20000, "emissivity": 0.8},
            ]
            result = run_component_thermal(data)
            self.assertEqual(result["status"], "completed", result)
            for old, new in zip(result["transient"], result["transient"][1:]):
                old_t, new_t = old["temperatures_c"]["U1"], new["temperatures_c"]["U1"]
                storage = 2 * (new_t - old_t) / (new["time_s"] - old["time_s"])
                radiation = 5.670374419e-8 * 0.8 * 0.02 * ((new_t + 273.15) ** 4 - 298.15 ** 4)
                self.assertAlmostEqual(storage + 0.2 * (new_t - 25) + radiation, 3, places=8)
                self.assertGreaterEqual(new_t, old_t)
            ends.append(result["nodes"][0]["temperature_c"])
        self.assertGreater((ends[1] - ends[0]) / (ends[2] - ends[1]), 1.9)

    def test_bad_surface_properties_and_floating_objects_fail_closed(self):
        data = request()
        data["components"] = [{"component_ref": "U1", "power_w": 1}]
        boundary = {"id": "rad", "object_ref": "U1", "surface": "whole", "kind": "radiation", "area_mm2": 10000, "emissivity": 0.8}
        for key, value in (("emissivity", 1.1), ("emissivity", 0), ("emissivity", True), ("area_mm2", -1),
                           ("surroundings_temperature_c", -274), ("object_ref", "unknown"), ("kind", "unknown"), ("enabled", "yes")):
            data["surfaces"] = [dict(boundary, **{key: value})]
            self.assertEqual(run_component_thermal(data)["status"], "blocked", (key, value))
        for boundaries in ([dict(boundary, enabled=False)], [boundary, boundary], [boundary] * 2049,
                           [{"id": "self", "kind": "conduction", "object_ref": "U1", "target_ref": "U1", "resistance_c_per_w": 1}]):
            data["surfaces"] = boundaries
            self.assertEqual(run_component_thermal(data)["status"], "blocked")

    def test_coupled_work_limit_fails_before_factorization_and_recovers(self):
        data = request("transient", step=1, end=2000)
        data["components"] = [dict(data["components"][0], component_ref=f"U{i}") for i in range(32)]
        data["surfaces"] = [{"id": "contact", "kind": "conduction", "object_ref": "U0", "target_ref": "U1", "resistance_c_per_w": 5}]
        with patch("python.spike_core.thermal_network._solve_linear", side_effect=AssertionError("oversized coupled run must fail before solving")):
            result = run_component_thermal(data)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("dense work-unit limit", result["issues"][0]["message"])
        data["scenario"]["run"]["write_interval_s"] = 100
        result = run_component_thermal(data)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(len(result["transient"]), 21)

    def test_nonlinear_iterations_charge_coupled_work_budget(self):
        data = request()
        data["components"] = [{"component_ref": "U1", "power_w": 3}, {"component_ref": "sink", "power_w": 0}]
        data["surfaces"] = [
            {"id": "contact", "kind": "conduction", "object_ref": "U1", "target_ref": "sink", "resistance_c_per_w": 5},
            {"id": "rad", "kind": "radiation", "object_ref": "sink", "area_mm2": 10000, "emissivity": 0.8},
        ]
        # Two nodes cost 8 units per dense factorization. Permit the first
        # iteration; the genuinely nonlinear problem requires additional work.
        with patch("python.spike_core.thermal_network.MAX_SURFACE_DENSE_WORK", 8):
            result = run_component_thermal(data)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("dense work-unit limit", result["issues"][0]["message"])
        self.assertEqual(run_component_thermal(data)["status"], "completed")

    def test_legacy_uncoupled_route_ignores_dense_surface_budget(self):
        with patch("python.spike_core.thermal_network.MAX_SURFACE_DENSE_WORK", 0), patch(
            "python.spike_core.component_thermal.estimate_surface_thermal_network", side_effect=AssertionError("legacy path must remain independent")
        ):
            result = run_component_thermal(request("transient"))
        self.assertEqual(result["status"], "completed")

    @patch("python.spike_core.service_simulation_handlers.openfoam_capabilities", side_effect=AssertionError("OpenFOAM is not required"))
    @patch("python.spike_core.service_simulation_handlers.run_case", side_effect=AssertionError("OpenFOAM is not required"))
    def test_worker_route_needs_no_external_engine(self, _run, _capabilities):
        response = handle_simulation_request("run_component_thermal", request(), assembly_scope={}, solver_registry=None)
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
