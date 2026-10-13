# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original synthetic conservation/closed-form oracles; not SAS cooling data."""
import json
import math
import unittest
from copy import deepcopy
from unittest.mock import patch

from python.spike_core.transient_resistive_electrothermal import (
    CONTRACT, run_transient_resistive_electrothermal,
)


def request(alpha=0.0, dt=0.1, end=2.0):
    return {
        "contract": CONTRACT,
        "circuit": {"contract": "spike/native-mna-request/v1", "request_id": "synthetic-rc",
                    "ground_node": "0", "analysis": {"mode": "operating_point"}, "elements": [
                        {"id": "I", "type": "current_source", "positive_node": "0", "negative_node": "p", "dc_value": 1.0},
                        {"id": "R", "type": "resistor", "positive_node": "p", "negative_node": "0", "resistance_ohm": 2.0}]},
        "thermal": {"ambient_temperature_k": 300.0,
                    "nodes": [{"id": "body", "capacitance_j_per_k": 2.0, "initial_temperature_k": 300.0,
                               "minimum_temperature_k": 290.0, "maximum_temperature_k": 400.0}],
                    "links": [{"id": "cool", "from_id": "body", "to_id": "ambient", "resistance_k_per_w": 1.0}]},
        "loss_mappings": [{"element_id": "R", "thermal_node_id": "body", "reference_temperature_k": 300.0,
                           "temperature_coefficient_per_k": alpha}],
        "loss_ledger": [{"element_id": "R", "disposition": "joule_heat", "reason": "All synthetic resistor heat deposited."},
                        {"element_id": "I", "disposition": "external_ideal_source", "reason": "Ideal external fixture supply."}],
        "time": {"stop_time_s": end, "maximum_time_step_s": dt},
        "iteration": {"max_iterations": 30, "relaxation": 1.0, "temperature_tolerance_k": 1e-9,
                      "power_tolerance_w": 1e-9, "balance_tolerance_w": 1e-8,
                      "electrical_relative_tolerance": 1e-10, "time_limit_s": 120.0},
    }


def eight_branch_request(dt=0.2, end=5.0):
    """Synthetic shared sink, explicitly NOT an installed SAS heatsink model."""
    value = request(dt=dt, end=end)
    value["circuit"]["elements"] = []
    value["loss_mappings"] = []
    value["loss_ledger"] = []
    value["thermal"]["nodes"] = []
    value["thermal"]["links"] = []
    for index in range(8):
        identifier = str(index)
        value["circuit"]["elements"] += [
            {"id": "I" + identifier, "type": "current_source", "positive_node": "0", "negative_node": "p" + identifier, "dc_value": 1.0},
            {"id": "R" + identifier, "type": "resistor", "positive_node": "p" + identifier, "negative_node": "0", "resistance_ohm": 3.0}]
        value["thermal"]["nodes"].append({"id": identifier, "capacitance_j_per_k": 1.0,
            "initial_temperature_k": 300.0, "minimum_temperature_k": 290.0, "maximum_temperature_k": 500.0})
        value["thermal"]["links"].append({"id": identifier, "from_id": identifier, "to_id": "synthetic_sink", "resistance_k_per_w": 2.0})
        value["loss_mappings"].append({"element_id": "R" + identifier, "thermal_node_id": identifier,
                                      "reference_temperature_k": 300.0, "temperature_coefficient_per_k": 0.01})
        value["loss_ledger"] += [
            {"element_id": "R" + identifier, "disposition": "joule_heat", "reason": "Synthetic resistor."},
            {"element_id": "I" + identifier, "disposition": "external_ideal_source", "reason": "Synthetic external supply."}]
    value["thermal"]["nodes"].append({"id": "synthetic_sink", "capacitance_j_per_k": 2.0,
        "initial_temperature_k": 300.0, "minimum_temperature_k": 290.0, "maximum_temperature_k": 500.0})
    value["thermal"]["links"].append({"id": "sink-air", "from_id": "synthetic_sink", "to_id": "ambient", "resistance_k_per_w": 0.5})
    return value


class TransientResistiveElectrothermalTests(unittest.TestCase):
    def run_case(self, value):
        before = deepcopy(value)
        result = run_transient_resistive_electrothermal(value)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(value, before)
        self.assertFalse(result["qualification"]["hardware_pass"])
        self.assertFalse(result["qualification"]["production_qualified"])
        json.dumps(result, allow_nan=False)
        for record in result["history"]:
            self.assertLessEqual(record["nodal_balance_residual_w"], value["iteration"]["balance_tolerance_w"])
            self.assertLessEqual(abs(record["global_balance_residual_w"]), value["iteration"]["balance_tolerance_w"])
        return result

    def blocked(self, value, code):
        result = run_transient_resistive_electrothermal(value)
        self.assertEqual(result["status"], "blocked", result)
        self.assertEqual(result["samples"], [])
        self.assertEqual(result["issues"][0]["code"], "TRE_" + code, result)

    def test_constant_power_matches_discrete_be_and_continuous_rc_refinement(self):
        errors = []
        for dt in (0.2, 0.1, 0.05):
            result = self.run_case(request(dt=dt))
            temperature = result["samples"][-1]["temperature_k"]["body"]
            n = result["steps"]
            expected_be = 300 + 2 * (1 - (1 + dt / 2) ** -n)
            self.assertAlmostEqual(temperature, expected_be, places=10)
            errors.append(abs(temperature - (300 + 2 * (1 - math.exp(-1)))))
        self.assertLess(errors[1], errors[0] * 0.55)
        self.assertLess(errors[2], errors[1] * 0.55)

    def test_temperature_resistance_current_feedback_analytical_transient(self):
        # C*dtheta/dt=P0-(1/Rth-alpha*P0)*theta. P0=2 W, gain=.04.
        errors = []
        for dt in (0.2, 0.1, 0.05):
            result = self.run_case(request(alpha=0.02, dt=dt))
            theta = result["samples"][-1]["temperature_k"]["body"] - 300
            expected = 2 / 0.96 * (1 - math.exp(-0.96))
            errors.append(abs(theta - expected))
            self.assertGreater(result["samples"][-1]["electrical"]["node_voltage_v"]["p"], 2.0)
            expected_be = 2 / 0.96 * (1 - (1 + dt * 0.96 / 2) ** -result["steps"])
            self.assertAlmostEqual(theta, expected_be, places=8)
        self.assertLess(errors[1], errors[0] * 0.55)
        self.assertLess(errors[2], errors[1] * 0.55)

    def test_eight_synthetic_branches_shared_sink_closed_form_and_refinement(self):
        # Symmetry reduces nine nodes to [device,sink]. Independent eigenmode
        # solution of A=[[-.47,.5],[2,-3]], forcing b=[3,0].
        trace, determinant = -3.47, 0.41
        root = math.sqrt(trace * trace - 4 * determinant)
        l1, l2 = (trace + root) / 2, (trace - root) / 2
        steady_device, steady_sink = 18 / 0.82, 12 / 0.82
        def exact_device(t):
            a = (3 + l2 * steady_device) / (l1 - l2)
            b = -steady_device - a
            return steady_device + a * math.exp(l1 * t) + b * math.exp(l2 * t)
        errors = []
        for dt in (0.2, 0.1, 0.05):
            result = self.run_case(eight_branch_request(dt))
            values = result["samples"][-1]["temperature_k"]
            self.assertLess(max(values[str(i)] for i in range(8)) - min(values[str(i)] for i in range(8)), 1e-10)
            errors.append(abs(values["0"] - 300 - exact_device(5)))
        self.assertLess(errors[1], errors[0] * 0.6)
        self.assertLess(errors[2], errors[1] * 0.6)
        result = self.run_case(eight_branch_request(1.0, 200.0))
        final = result["samples"][-1]["temperature_k"]
        self.assertAlmostEqual(final["0"], 300 + steady_device, places=6)
        self.assertAlmostEqual(final["synthetic_sink"], 300 + steady_sink, places=6)

    def test_missing_duplicate_mapping_and_incomplete_ledger(self):
        value = request()
        value["loss_mappings"].append(deepcopy(value["loss_mappings"][0]))
        self.blocked(value, "MAPPING")
        value = eight_branch_request()
        value["loss_mappings"].pop()
        self.blocked(value, "MAPPING")
        value = request()
        value["loss_ledger"].pop()
        self.blocked(value, "LEDGER")

    def test_nonconvergence_cannot_be_hidden_by_small_relaxation(self):
        value = request(alpha=0.02)
        value["iteration"].update(max_iterations=2, relaxation=1e-12)
        self.blocked(value, "NONCONVERGENCE")

    def test_independent_conservation_check_rejects_corrupted_kernel_output(self):
        from python.spike_core.thermal_network import estimate_lumped_thermal_network
        from python.spike_core.native_mna import run_native_mna
        def corrupted_thermal(scenario):
            result = estimate_lumped_thermal_network(scenario)
            result["transient"][-1]["temperatures_c"]["body"] += 1.0
            return result
        value = request()
        value["iteration"].update(max_iterations=2, temperature_tolerance_k=10.0)
        with patch("python.spike_core.transient_resistive_electrothermal.estimate_lumped_thermal_network", side_effect=corrupted_thermal):
            self.blocked(value, "NONCONVERGENCE")
        def corrupted_electrical(circuit):
            result = run_native_mna(circuit)
            result["data"]["element_power_w"]["I"] += 0.5
            return result
        with patch("python.spike_core.transient_resistive_electrothermal.run_native_mna", side_effect=corrupted_electrical):
            self.blocked(request(), "ELECTRICAL_BALANCE")

    def test_voltage_drive_reaches_closed_form_temperature_and_derates_current(self):
        value = request(alpha=0.02, dt=1.0, end=100.0)
        value["circuit"]["elements"][0].update(type="voltage_source", positive_node="p", negative_node="0", dc_value=2.0)
        result = self.run_case(value)
        # theta = V^2 Rth / [R0*(1+alpha*theta)].
        expected = 4 / (1 + math.sqrt(1 + 4 * 0.02 * 2))
        self.assertAlmostEqual(result["samples"][-1]["temperature_k"]["body"] - 300, expected, places=8)
        self.assertLess(result["samples"][-1]["electrical"]["element_current_a"]["R"], 1.0)

    def test_temperature_range_floating_network_and_nonfinite_inputs(self):
        value = request()
        value["thermal"]["nodes"][0]["maximum_temperature_k"] = 300.01
        self.blocked(value, "TEMPERATURE_RANGE")
        value = eight_branch_request()
        value["thermal"]["links"].pop()
        self.blocked(value, "THERMAL_SOLVE")
        for number in (float("nan"), float("inf"), -1.0, True):
            value = request()
            value["thermal"]["nodes"][0]["capacitance_j_per_k"] = number
            self.blocked(value, "NUMBER")

    def test_unknown_fields_and_unsupported_devices_are_blocked(self):
        for path in ((), ("thermal",), ("iteration",), ("circuit",), ("circuit", "elements", 0), ("loss_mappings", 0)):
            value = request()
            target = value
            for key in path:
                target = target[key]
            target["inferred_cooling"] = 1
            self.blocked(value, "FIELDS")
        value = request()
        value["circuit"]["elements"][1]["type"] = "capacitor"
        self.blocked(value, "ELECTRICAL_SCOPE")

    def test_nonambient_initial_state_and_zero_power_cooling(self):
        value = request()
        value["circuit"]["elements"][0]["dc_value"] = 0.0
        value["thermal"]["nodes"][0]["initial_temperature_k"] = 310.0
        result = self.run_case(value)
        expected = 300 + 10 * (1 + 0.1 / 2) ** -20
        self.assertAlmostEqual(result["samples"][-1]["temperature_k"]["body"], expected, places=10)

    def test_bounds_cancellation_and_timeout(self):
        value = request(dt=1e-10)
        self.blocked(value, "BOUNDS")
        result = run_transient_resistive_electrothermal(request(), cancel_check=lambda: True)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["samples"], [])
        with patch("python.spike_core.transient_resistive_electrothermal.time.monotonic", side_effect=(0.0, 200.0)):
            self.blocked(request(), "TIMEOUT")

    def test_missing_or_unexpected_thermal_nodes_are_structured_failures(self):
        from python.spike_core.thermal_network import estimate_lumped_thermal_network
        for mutation in ("missing", "extra", "malformed"):
            def corrupt(scenario):
                result = estimate_lumped_thermal_network(scenario)
                values = result["transient"][-1]["temperatures_c"]
                if mutation == "missing":
                    values.pop("body")
                elif mutation == "extra":
                    values["undeclared"] = 25.0
                else:
                    result["transient"][-1]["temperatures_c"] = None
                return result
            with patch("python.spike_core.transient_resistive_electrothermal.estimate_lumped_thermal_network", side_effect=corrupt):
                self.blocked(request(), "NUMERICAL_FAILURE")

    def test_malformed_native_data_cannot_escape_or_pass(self):
        from python.spike_core.native_mna import run_native_mna
        for mutation in ("missing_data", "missing_power", "missing_diagnostics", "bad_collection"):
            def corrupt(circuit):
                result = run_native_mna(circuit)
                if mutation == "missing_data":
                    result.pop("data")
                elif mutation == "missing_power":
                    result["data"]["element_power_w"].pop("R")
                elif mutation == "missing_diagnostics":
                    result["diagnostics"] = None
                else:
                    result["data"]["element_current_a"] = [1.0]
                return result
            with patch("python.spike_core.transient_resistive_electrothermal.run_native_mna", side_effect=corrupt):
                self.blocked(request(), "NUMERICAL_FAILURE")

    def test_serialized_input_and_output_caps_withhold_samples(self):
        value = request()
        input_size = len(json.dumps(value).encode("utf-8"))
        with patch("python.spike_core.transient_resistive_electrothermal.MAX_JSON_BYTES", input_size - 1):
            self.blocked(value, "INPUT_BYTES")
        with patch("python.spike_core.transient_resistive_electrothermal.MAX_JSON_BYTES", input_size + 100):
            result = run_transient_resistive_electrothermal(value)
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["issues"][0]["code"], "TRE_RESULT_BYTES")
            self.assertEqual(result["samples"], [])
            self.assertEqual(result["history"], [])
            self.assertLessEqual(len(json.dumps(result).encode("utf-8")), input_size + 100)


if __name__ == "__main__":
    unittest.main()
