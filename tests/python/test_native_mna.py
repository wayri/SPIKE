import math
import unittest

from python.spike_core.native_mna import REQUEST_CONTRACT, run_native_mna, validate_native_mna_request
from python.spike_core.service import handle


def request(elements, analysis=None):
    return {
        "contract": REQUEST_CONTRACT,
        "request_id": "fixture",
        "ground_node": "0",
        "elements": elements,
        "analysis": analysis or {"mode": "operating_point"},
    }


class NativeMnaTests(unittest.TestCase):
    def test_dc_voltage_divider(self):
        result = run_native_mna(request([
            {"id": "V1", "type": "voltage_source", "positive_node": "vin", "negative_node": "0", "dc_value": 10.0},
            {"id": "R1", "type": "resistor", "positive_node": "vin", "negative_node": "vout", "resistance_ohm": 1000.0},
            {"id": "R2", "type": "resistor", "positive_node": "vout", "negative_node": "0", "resistance_ohm": 1000.0},
        ]))
        self.assertEqual(result["status"], "completed")
        self.assertAlmostEqual(result["data"]["node_voltage_v"]["vout"], 5.0, places=12)
        self.assertAlmostEqual(result["data"]["branch_current_a"]["V1"], -0.005, places=12)
        self.assertAlmostEqual(result["data"]["element_current_a"]["R1"], 0.005, places=12)
        self.assertAlmostEqual(result["data"]["element_power_w"]["R1"], 0.025, places=12)
        self.assertAlmostEqual(result["data"]["element_power_w"]["V1"], -0.05, places=12)

    def test_independent_current_source(self):
        result = run_native_mna(request([
            {"id": "I1", "type": "current_source", "positive_node": "0", "negative_node": "out", "dc_value": 0.001},
            {"id": "R1", "type": "resistor", "positive_node": "out", "negative_node": "0", "resistance_ohm": 1000.0},
        ]))
        self.assertAlmostEqual(result["data"]["node_voltage_v"]["out"], 1.0, places=12)

    def test_voltage_and_current_controlled_sources(self):
        elements = [
            {"id": "VCTRL", "type": "voltage_source", "positive_node": "ctrl", "negative_node": "0", "dc_value": 1.0},
            {"id": "RCTRL", "type": "resistor", "positive_node": "ctrl", "negative_node": "0", "resistance_ohm": 1000.0},
            {"id": "E1", "type": "vcvs", "positive_node": "eout", "negative_node": "0", "control_positive_node": "ctrl", "control_negative_node": "0", "gain": 2.0},
            {"id": "RE", "type": "resistor", "positive_node": "eout", "negative_node": "0", "resistance_ohm": 1000.0},
            {"id": "G1", "type": "vccs", "positive_node": "gout", "negative_node": "0", "control_positive_node": "ctrl", "control_negative_node": "0", "transconductance_s": 0.001},
            {"id": "RG", "type": "resistor", "positive_node": "gout", "negative_node": "0", "resistance_ohm": 1000.0},
            {"id": "F1", "type": "cccs", "positive_node": "fout", "negative_node": "0", "control_source_id": "VCTRL", "gain": 1.0},
            {"id": "RF", "type": "resistor", "positive_node": "fout", "negative_node": "0", "resistance_ohm": 1000.0},
            {"id": "H1", "type": "ccvs", "positive_node": "hout", "negative_node": "0", "control_source_id": "VCTRL", "transresistance_ohm": 1000.0},
            {"id": "RH", "type": "resistor", "positive_node": "hout", "negative_node": "0", "resistance_ohm": 1000.0},
        ]
        result = run_native_mna(request(elements))
        self.assertEqual(result["status"], "completed")
        voltages = result["data"]["node_voltage_v"]
        self.assertAlmostEqual(voltages["eout"], 2.0, places=12)
        self.assertAlmostEqual(voltages["gout"], -1.0, places=12)
        # VCTRL supplies the control resistor, so its defined branch current is -1 mA.
        self.assertAlmostEqual(voltages["fout"], 1.0, places=12)
        self.assertAlmostEqual(voltages["hout"], -1.0, places=12)

    def test_ac_rc_corner_frequency(self):
        resistance = 1000.0
        capacitance = 1e-6
        corner = 1.0 / (2.0 * math.pi * resistance * capacitance)
        result = run_native_mna(request([
            {"id": "V1", "type": "voltage_source", "positive_node": "vin", "negative_node": "0", "ac_magnitude": 1.0},
            {"id": "R1", "type": "resistor", "positive_node": "vin", "negative_node": "out", "resistance_ohm": resistance},
            {"id": "C1", "type": "capacitor", "positive_node": "out", "negative_node": "0", "capacitance_f": capacitance},
        ], {"mode": "ac", "start_hz": corner, "stop_hz": corner, "points": 1, "scale": "log"}))
        magnitude = result["data"]["node_voltage_v"]["out"]["magnitude"][0]
        self.assertAlmostEqual(magnitude, 1.0 / math.sqrt(2.0), places=10)
        capacitor_current = result["data"]["element_current_a"]["C1"]["magnitude"][0]
        self.assertAlmostEqual(capacitor_current, magnitude / resistance, places=10)

    def test_ac_rl_corner_frequency(self):
        resistance = 10.0
        inductance = 10e-3
        corner = resistance / (2.0 * math.pi * inductance)
        result = run_native_mna(request([
            {"id": "V1", "type": "voltage_source", "positive_node": "vin", "negative_node": "0", "ac_magnitude": 1.0},
            {"id": "R1", "type": "resistor", "positive_node": "vin", "negative_node": "out", "resistance_ohm": resistance},
            {"id": "L1", "type": "inductor", "positive_node": "out", "negative_node": "0", "inductance_h": inductance},
        ], {"mode": "ac", "start_hz": corner, "stop_hz": corner, "points": 1, "scale": "log"}))
        self.assertEqual(result["status"], "completed")
        magnitude = result["data"]["node_voltage_v"]["out"]["magnitude"][0]
        self.assertAlmostEqual(magnitude, 1.0 / math.sqrt(2.0), places=10)

    def test_transient_step_rc_response(self):
        result = run_native_mna(request([
            {
                "id": "V1", "type": "voltage_source", "positive_node": "vin", "negative_node": "0",
                "waveform": {"type": "step", "initial": 0.0, "final": 1.0, "delay_s": 0.0},
            },
            {"id": "R1", "type": "resistor", "positive_node": "vin", "negative_node": "out", "resistance_ohm": 1000.0},
            {"id": "C1", "type": "capacitor", "positive_node": "out", "negative_node": "0", "capacitance_f": 1e-6},
        ], {"mode": "transient", "time_step_s": 1e-5, "stop_time_s": 1e-3}))
        self.assertEqual(result["status"], "completed")
        self.assertAlmostEqual(result["data"]["node_voltage_v"]["out"][-1], 1.0 - math.exp(-1.0), delta=0.004)
        self.assertEqual(result["data"]["integration"], "backward_euler")
        self.assertEqual(len(result["data"]["element_current_a"]["C1"]), 101)
        self.assertEqual(len(result["data"]["element_power_w"]["R1"]), 101)

    def test_transient_step_rl_current_response(self):
        resistance = 10.0
        inductance = 10e-3
        result = run_native_mna(request([
            {
                "id": "V1", "type": "voltage_source", "positive_node": "vin", "negative_node": "0",
                "waveform": {"type": "step", "initial": 0.0, "final": 1.0, "delay_s": 0.0},
            },
            {"id": "R1", "type": "resistor", "positive_node": "vin", "negative_node": "out", "resistance_ohm": resistance},
            {"id": "L1", "type": "inductor", "positive_node": "out", "negative_node": "0", "inductance_h": inductance},
        ], {"mode": "transient", "time_step_s": 1e-5, "stop_time_s": 1e-3}))
        self.assertEqual(result["status"], "completed")
        expected = (1.0 / resistance) * (1.0 - math.exp(-1.0))
        self.assertAlmostEqual(result["data"]["element_current_a"]["L1"][-1], expected, delta=4e-4)

    def test_pulse_and_pwl_source_evaluation_are_bounded(self):
        for waveform in (
            {"type": "pulse", "low": 0.0, "high": 2.0, "delay_s": 1e-3, "pulse_width_s": 1e-3, "period_s": 3e-3},
            {"type": "pwl", "points": [[0.0, 0.0], [1e-3, 2.0], [2e-3, 0.0]]},
        ):
            result = run_native_mna(request([
                {"id": "V1", "type": "voltage_source", "positive_node": "out", "negative_node": "0", "waveform": waveform},
                {"id": "R1", "type": "resistor", "positive_node": "out", "negative_node": "0", "resistance_ohm": 1000.0},
            ], {"mode": "transient", "time_step_s": 1e-3, "stop_time_s": 3e-3}))
            self.assertEqual(result["status"], "completed")
            self.assertTrue(all(math.isfinite(value) for value in result["data"]["node_voltage_v"]["out"]))

    def test_unsupported_nonlinear_device_is_blocked(self):
        candidate = request([
            {"id": "Q1", "type": "mosfet", "positive_node": "d", "negative_node": "s"},
        ])
        validation = validate_native_mna_request(candidate)
        self.assertFalse(validation["valid"])
        self.assertIn("MNA_ELEMENT_UNSUPPORTED", {issue["code"] for issue in validation["issues"]})
        self.assertEqual(run_native_mna(candidate)["status"], "blocked")

    def test_malformed_waveform_and_ac_scale_are_blocked_before_solve(self):
        malformed = request([{
            "id": "V1",
            "type": "voltage_source",
            "positive_node": "out",
            "negative_node": "0",
            "waveform": {"type": "pwl", "points": [[1.0, 1.0], [0.5, 2.0]]},
        }], {"mode": "ac", "start_hz": 1.0, "stop_hz": 10.0, "points": 2, "scale": "octopus"})
        validation = validate_native_mna_request(malformed)
        self.assertFalse(validation["valid"])
        codes = {issue["code"] for issue in validation["issues"]}
        self.assertIn("MNA_PWL_POINT_INVALID", codes)
        self.assertIn("MNA_AC_SCALE_INVALID", codes)

    def test_memory_limit_is_reported_in_gigabytes_and_fails_closed(self):
        candidate = request([
            {"id": "V1", "type": "voltage_source", "positive_node": "out", "negative_node": "0", "dc_value": 1.0},
        ])
        candidate["resource_limits"] = {"memory_limit_gb": 1.0}
        validation = validate_native_mna_request(candidate)
        self.assertFalse(validation["valid"])
        self.assertIn("MNA_MEMORY_LIMIT_INVALID", {issue["code"] for issue in validation["issues"]})

    def test_forced_superlu_matches_dense_and_reports_backend(self):
        elements = [
            {"id": "V1", "type": "voltage_source", "positive_node": "vin", "negative_node": "0", "dc_value": 10.0},
            {"id": "R1", "type": "resistor", "positive_node": "vin", "negative_node": "vout", "resistance_ohm": 1000.0},
            {"id": "R2", "type": "resistor", "positive_node": "vout", "negative_node": "0", "resistance_ohm": 1000.0},
        ]
        dense_request = request(elements)
        dense_request["resource_limits"] = {"memory_limit_gb": 2.0, "linear_backend": "dense"}
        sparse_request = request(elements)
        sparse_request["resource_limits"] = {
            "memory_limit_gb": 2.0,
            "linear_backend": "scipy-superlu",
            "sparse_threshold": 1,
        }

        dense = run_native_mna(dense_request)
        sparse = run_native_mna(sparse_request)

        self.assertEqual(sparse["status"], "completed")
        self.assertAlmostEqual(
            sparse["data"]["node_voltage_v"]["vout"],
            dense["data"]["node_voltage_v"]["vout"],
            places=12,
        )
        self.assertEqual(sparse["diagnostics"]["linear_backend"]["selected"], "scipy-superlu")
        self.assertEqual(sparse["diagnostics"]["linear_backend_runs"], 1)
        self.assertIsNone(sparse["diagnostics"]["condition_number_max"])

    def test_unknown_linear_backend_is_blocked(self):
        candidate = request([
            {"id": "V1", "type": "voltage_source", "positive_node": "out", "negative_node": "0", "dc_value": 1.0},
            {"id": "R1", "type": "resistor", "positive_node": "out", "negative_node": "0", "resistance_ohm": 1000.0},
        ])
        candidate["resource_limits"] = {"memory_limit_gb": 2.0, "linear_backend": "magic"}
        validation = validate_native_mna_request(candidate)
        self.assertFalse(validation["valid"])
        self.assertIn("MNA_LINEAR_BACKEND_INVALID", {issue["code"] for issue in validation["issues"]})
        self.assertEqual(run_native_mna(candidate)["status"], "blocked")

    def test_worker_service_exposes_validation_and_execution(self):
        candidate = request([
            {"id": "V1", "type": "voltage_source", "positive_node": "out", "negative_node": "0", "dc_value": 2.0},
            {"id": "R1", "type": "resistor", "positive_node": "out", "negative_node": "0", "resistance_ohm": 1000.0},
        ])
        validation = handle({"method": "validate_native_mna", "params": {"request": candidate}})
        solved = handle({"method": "run_native_mna", "params": {"request": candidate}})
        self.assertTrue(validation["ok"])
        self.assertTrue(validation["result"]["valid"])
        self.assertTrue(solved["ok"])
        self.assertEqual(solved["result"]["status"], "completed")

    def test_singular_circuit_fails_with_diagnostic(self):
        result = run_native_mna(request([
            {"id": "R1", "type": "resistor", "positive_node": "a", "negative_node": "b", "resistance_ohm": 1000.0},
        ]))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["issues"][0]["code"], "MNA_NUMERICAL_FAILURE")


if __name__ == "__main__":
    unittest.main()
