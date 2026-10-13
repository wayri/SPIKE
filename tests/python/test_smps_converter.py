# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SPIKE contributors
"""Original synthetic analytical and time-refinement oracles; no vendor data."""
import copy
import json
import math
from pathlib import Path
import unittest

from python.spike_core.smps_converter import (
    REQUEST_CONTRACT, SmpsConverterError, _phase, evaluate_smps_converter,
)


def request(topology="synchronous_buck", losses=False):
    return {"contract": REQUEST_CONTRACT, "block_id": "supply-1", "topology": topology,
            "input_voltage_v": 12., "output_voltage_v": 5. if topology == "synchronous_buck" else
            24. if topology == "synchronous_boost" else -12., "output_current_a": 3.,
            "switching_frequency_hz": 100000.,
            "switches": [{"role": role, "devices": [{"occurrence_id": "board-A", "component_ref": ref}],
                          "series_count": 1, "parallel_count": 1, "rds_on_ohm": .02 if losses else 0.,
                          "rise_time_s": 10e-9 if losses else 0., "fall_time_s": 20e-9 if losses else 0.,
                          "gate_charge_c": 20e-9 if losses else 0., "gate_drive_v": 10.,
                          "voltage_rating_v": 100., "current_rating_a": 100.}
                         for role, ref in (("on", "Q1"), ("off", "Q2"))],
            "inductor": {"occurrence_id": "board-A", "component_ref": "L1", "inductance_h": 100e-6,
                         "dcr_ohm": .03 if losses else 0., "current_rating_a": 100.}}


class SmpsConverterTests(unittest.TestCase):
    def reject(self, value, code):
        with self.assertRaises(SmpsConverterError) as caught:
            evaluate_smps_converter(value)
        self.assertEqual(caught.exception.code, code)

    def test_lossless_topology_analytical_oracles(self):
        # Voltage-second and capacitor-charge balance, derived independently.
        for topology, expected_duty, expected_mean in (
            ("synchronous_buck", 5/12, 3),
            ("synchronous_boost", .5, 6),
            ("inverting_buck_boost", .5, 6),
        ):
            with self.subTest(topology=topology):
                value = request(topology)
                result = evaluate_smps_converter(value)
                ripple = (12-5 if topology == "synchronous_buck" else 12)*expected_duty/10
                self.assertAlmostEqual(result["duty_cycle"], expected_duty, delta=2e-14)
                self.assertAlmostEqual(result["inductor_average_current_a"], expected_mean, delta=2e-11)
                self.assertAlmostEqual(result["inductor_ripple_current_a"], ripple, delta=2e-11)
                self.assertAlmostEqual(result["inductor_rms_current_a"]**2,
                                       expected_mean**2+ripple**2/12, delta=2e-10)
                self.assertAlmostEqual(result["input_current_a"], abs(value["output_voltage_v"])*3/12, delta=2e-10)
                self.assertAlmostEqual(result["efficiency"], 1., delta=2e-12)
                self.assertEqual(result["total_loss_w"], 0.)

    def test_equal_phase_resistance_buck_closed_form(self):
        value = request(losses=True)
        result = evaluate_smps_converter(value)
        # With identical phase R, integrated volt seconds give Vin*D=Vo+R*Io.
        self.assertAlmostEqual(result["duty_cycle"], (5+.05*3)/12, delta=2e-14)
        self.assertGreater(result["inductor_rms_current_a"], 3)
        self.assertGreater(result["losses"][-1]["total_power_w"], .03*9)

    def test_loss_ledger_and_independent_input_power_all_topologies(self):
        for topology in ("synchronous_buck", "synchronous_boost", "inverting_buck_boost"):
            value = request(topology, True)
            before = copy.deepcopy(value)
            result = evaluate_smps_converter(value)
            self.assertEqual(value, before)
            self.assertAlmostEqual(result["input_power_w"], result["output_power_w"]+result["total_loss_w"], delta=1e-9)
            self.assertAlmostEqual(result["total_loss_w"], sum(row["total_power_w"] for row in result["losses"])
                                   + result["auxiliary_loss_w"], delta=1e-12)
            self.assertAlmostEqual(result["auxiliary_loss_w"], .04, delta=1e-14)
            self.assertLess(result["efficiency"], 1)
            self.assertEqual(result["model_status"], "approximate")
            self.assertEqual(result["auxiliary_loss_location"], "unassigned_gate_drive")

    def test_transition_edge_currents_and_overhead_are_explicit(self):
        value = request(losses=True)
        result = evaluate_smps_converter(value)
        low, high = result["inductor_minimum_current_a"], result["inductor_peak_current_a"]
        expected = .5*12*100000*(low*10e-9+high*20e-9)
        self.assertAlmostEqual(result["losses"][0]["switching_power_w"], expected, delta=1e-11)
        value["switches"][0]["rise_time_s"] = 0
        value["switches"][0]["fall_time_s"] = 0
        without = evaluate_smps_converter(value)
        self.assertEqual(result["duty_cycle"], without["duty_cycle"])
        self.assertAlmostEqual(result["input_current_a"]-without["input_current_a"], expected/12, delta=1e-12)

    def test_result_contains_an_independent_request_snapshot(self):
        value = request(losses=True)
        result = evaluate_smps_converter(value)
        self.assertEqual(result["request_snapshot"], value)
        value["input_voltage_v"] = 13.
        value["switches"][0]["rds_on_ohm"] = .5
        value["inductor"]["inductance_h"] = 200e-6
        self.assertEqual(result["request_snapshot"]["input_voltage_v"], 12.)
        self.assertEqual(result["request_snapshot"]["switches"][0]["rds_on_ohm"], .02)
        self.assertEqual(result["request_snapshot"]["inductor"]["inductance_h"], 100e-6)

    def test_series_parallel_device_ledger_and_ratings(self):
        value = request(losses=True)
        for group in value["switches"]:
            group.update(series_count=2, parallel_count=2, voltage_rating_v=6, current_rating_a=2)
            group["devices"] = [{"occurrence_id": "board-A", "component_ref": group["role"]+str(n)} for n in range(4)]
        result = evaluate_smps_converter(value)
        single = evaluate_smps_converter(request(losses=True))
        self.assertEqual(result["duty_cycle"], single["duty_cycle"])
        self.assertAlmostEqual(result["losses"][0]["total_power_w"]*4, single["losses"][0]["total_power_w"], delta=1e-12)
        self.assertAlmostEqual(result["auxiliary_loss_w"], single["auxiliary_loss_w"]*4, delta=1e-12)
        value["switches"][0]["voltage_rating_v"] = 5.9
        self.reject(value, "switch_voltage_rating")

    def test_periodic_rl_integrals_against_independent_rk4_refinement(self):
        # Integrate i, integral(i), integral(i^2) with RK4 over one unit interval.
        # This test deliberately uses the largest admitted dimensionless decay.
        actual = _phase(7., 3., .5, 1.)
        errors = []
        for count in (2, 4, 8):
            state = (7., 0., 0.)
            h = 1/count
            def derivative(s):
                return (3-.5*s[0], s[0], s[0]**2)
            def advance(s, k, factor):
                return tuple(a+factor*b for a, b in zip(s, k))
            for _ in range(count):
                k1 = derivative(state)
                k2 = derivative(advance(state, k1, h/2))
                k3 = derivative(advance(state, k2, h/2))
                k4 = derivative(advance(state, k3, h))
                state = tuple(a+h*(b+2*c+2*d+e)/6 for a, b, c, d, e in zip(state, k1, k2, k3, k4))
            errors.append(max(abs(a-b) for a, b in zip(state, actual[:3])))
        self.assertGreater(errors[0]/errors[1], 12)
        self.assertGreater(errors[1]/errors[2], 12)
        expected_end = 6+math.exp(-.5)
        expected_mean = 6+2*(1-math.exp(-.5))
        expected_square = 36+24*(1-math.exp(-.5))+(1-math.exp(-1))
        for got, expected in zip(actual, (expected_end, expected_mean, expected_square)):
            self.assertAlmostEqual(got, expected, delta=2e-13)

    def test_rl_envelope_boundary_and_nearly_ideal_conditioning(self):
        value = request()
        for resistance in (0., 1e-20, .4):
            for group in value["switches"]:
                group["rds_on_ohm"] = resistance
            value["inductor"]["inductance_h"] = 10e-6
            result = evaluate_smps_converter(value)
            self.assertAlmostEqual(result["duty_cycle"], (5+3*resistance)/12, delta=2e-14)
            self.assertLess(abs(result["solver"]["energy_balance_residual_w"]), 1e-9)
            self.assertLess(result["solver"]["duty_bracket_width"], 2e-15)

    def test_dcm_no_load_and_rating_failures(self):
        value = request()
        value["output_current_a"] = .01
        self.reject(value, "discontinuous_conduction")
        value["output_current_a"] = 0
        self.reject(value, "invalid_number")
        value = request()
        value["inductor"]["current_rating_a"] = 3
        self.reject(value, "inductor_current_rating")
        value = request()
        value["switches"][0]["current_rating_a"] = 3
        self.reject(value, "switch_current_rating")

    def test_duty_failure_and_unsupported_voltage_ratio(self):
        value = request()
        value["output_current_a"] = 100
        for group in value["switches"]:
            group["rds_on_ohm"] = .1
        self.reject(value, "duty_unbracketed")
        value = request()
        value["output_voltage_v"] = 13
        self.reject(value, "voltage_ratio")
        value = request("inverting_buck_boost")
        value["output_voltage_v"] = 12
        self.reject(value, "invalid_number")

    def test_binding_and_resource_admission(self):
        value = request()
        value["switches"][1]["devices"] = value["switches"][0]["devices"]
        self.reject(value, "duplicate_binding")
        value = request()
        value["switches"][0]["parallel_count"] = 100000
        self.reject(value, "device_budget")
        value = request()
        value["switches"][0]["rise_time_s"] = 1
        self.reject(value, "transition_duration")
        value = request()
        value["inductor"]["dcr_ohm"] = 100
        self.reject(value, "rl_envelope")

    def test_number_and_contract_admission(self):
        for invalid in (float("nan"), float("inf"), True, "12", -1, 10**1000):
            value = request()
            value["input_voltage_v"] = invalid
            self.reject(value, "invalid_number")
        value = request()
        value["unexpected"] = 1
        self.reject(value, "invalid_fields")
        value = request()
        value["topology"] = "flyback"
        self.reject(value, "unsupported_topology")

    def test_schema_and_strict_json_result(self):
        import jsonschema
        path = Path(__file__).resolve().parents[2]/"schemas"/"smps-converter-request-v1.schema.json"
        schema = json.loads(path.read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        for topology in ("synchronous_buck", "synchronous_boost", "inverting_buck_boost"):
            value = request(topology, True)
            jsonschema.validate(value, schema)
            result = evaluate_smps_converter(value)
            json.dumps(result, allow_nan=False)
            self.assertEqual(len(result["losses"]), 3)


if __name__ == "__main__":
    unittest.main()
