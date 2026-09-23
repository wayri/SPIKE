import json
import math
import unittest

from python.spikes.converter_qualification import (
    CASE_CONTRACT,
    REPORT_CONTRACT,
    run_converter_reference_qualification,
)


class ConverterCoupledReferenceQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = run_converter_reference_qualification()

    def test_all_four_bounded_reference_cases_pass(self):
        self.assertEqual(self.report["contract"], REPORT_CONTRACT)
        self.assertEqual(self.report["status"], "passed")
        self.assertEqual(self.report["case_count"], 4)
        self.assertEqual(self.report["passed_case_count"], 4)
        self.assertEqual(
            {case["case_id"] for case in self.report["cases"]},
            {
                "converter.reverse_recovery_commutation",
                "converter.electrothermal_switch_feedback",
                "converter.magnetic_saturation",
                "converter.overcurrent_protection",
            },
        )
        for case in self.report["cases"]:
            self.assertEqual(case["contract"], CASE_CONTRACT)
            self.assertTrue(case["gates"])
            self.assertTrue(all(gate["passed"] for gate in case["gates"]))
            self.assertGreaterEqual(len(case["limitations"]), 2)

    def test_reverse_recovery_is_charge_conserving_and_eventful(self):
        case = next(item for item in self.report["cases"] if "reverse_recovery" in item["case_id"])
        metrics = case["metrics"]
        self.assertLess(metrics["peak_reverse_transport_current_a"], 0.0)
        self.assertLessEqual(metrics["charge_balance_error_c"], max(1e-24, metrics["armed_charge_c"] * 1e-12))
        self.assertEqual([event["kind"] for event in case["events"]], [
            "stored_charge_armed", "reverse_current_peak", "stored_charge_recovered_90pct",
        ])

    def test_thermal_and_magnetic_effects_are_observable(self):
        thermal = next(item for item in self.report["cases"] if "electrothermal" in item["case_id"])
        magnetic = next(item for item in self.report["cases"] if "magnetic" in item["case_id"])
        self.assertGreater(thermal["metrics"]["peak_loss_w"], thermal["metrics"]["initial_loss_w"])
        self.assertLess(thermal["metrics"]["thermal_loop_gain"], 1.0)
        self.assertGreater(
            magnetic["metrics"]["nonlinear_peak_current_a"],
            magnetic["metrics"]["linear_reference_peak_current_a"],
        )
        self.assertEqual(len(magnetic["events"]), 2)

    def test_protection_event_order_and_latency_are_asserted(self):
        case = next(item for item in self.report["cases"] if "protection" in item["case_id"])
        self.assertEqual([event["kind"] for event in case["events"]], [
            "overcurrent_warning", "overcurrent_trip", "gate_shutdown", "current_extinguished",
        ])
        metrics = case["metrics"]
        self.assertLessEqual(
            abs((metrics["shutdown_time_s"] - metrics["trip_time_s"]) - metrics["shutdown_delay_s"]),
            metrics["time_step_s"],
        )

    def test_report_is_json_safe_deterministic_and_claims_remain_disabled(self):
        encoded = json.dumps(self.report, allow_nan=False, sort_keys=True)
        self.assertTrue(encoded)
        for case in self.report["cases"]:
            for value in case["metrics"].values():
                if isinstance(value, float):
                    self.assertTrue(math.isfinite(value))
        self.assertEqual(self.report["qualification_scope"], "coupled_reference_only")
        self.assertFalse(self.report["native_mna_integration_qualified"])
        self.assertFalse(self.report["production_compact_models_qualified"])
        self.assertFalse(self.report["hard_realtime_qualified"])
        self.assertFalse(self.report["hil_claim_eligible"])
        self.assertFalse(self.report["competitive_claim_eligible"])


if __name__ == "__main__":
    unittest.main()
