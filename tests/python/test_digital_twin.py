# SPDX-License-Identifier: Apache-2.0
import copy
import hashlib
import json
import math
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.digital_twin import REQUEST_CONTRACT, compare_digital_twin


def fixture():
    declarations = [{"id": "voltage", "unit": "V"}, {"id": "current", "unit": "A"}]
    return {
        "contract": REQUEST_CONTRACT,
        "model_id": "supply-A",
        "model_revision": "rev-12",
        "model_status": "experimental",
        "channels": [
            {"id": "voltage", "unit": "V", "tolerance": 0.2},
            {"id": "current", "unit": "A", "tolerance": 0.05},
        ],
        "prediction": {
            "model_id": "supply-A", "model_revision": "rev-12",
            "channels": copy.deepcopy(declarations),
            "samples": [
                {"time_s": 0.0, "values": {"voltage": 5.0, "current": 1.0}},
                {"time_s": 1.0, "values": {"voltage": 5.1, "current": 1.1}},
                {"time_s": 3.0, "values": {"voltage": 5.2, "current": 1.2}},
            ],
        },
        "telemetry": {
            "model_id": "supply-A", "model_revision": "rev-12",
            "channels": copy.deepcopy(declarations),
            "samples": [
                {"time_s": 0.0, "values": {"voltage": 5.1, "current": 0.9}},
                {"time_s": 1.0, "values": {"voltage": 4.8, "current": 1.1}},
                {"time_s": 2.0, "values": {"voltage": 5.0, "current": 1.0}},
            ],
        },
    }


class DigitalTwinTests(unittest.TestCase):
    def test_many_channel_traces_share_global_budget(self):
        request = fixture()
        declarations = [{"id": f"c{i}", "unit": "V"} for i in range(128)]
        request["channels"] = [{**c, "tolerance": 1} for c in declarations]
        for key in ("prediction", "telemetry"):
            request[key]["channels"] = copy.deepcopy(declarations)
            request[key]["samples"] = [{"time_s": t, "values": {c["id"]: t for c in declarations}}
                                       for t in range(200)]
        result = compare_digital_twin(request)
        self.assertEqual(result["status"], "completed")
        self.assertLessEqual(sum(len(c["trace"]) for c in result["channels"]), 20000)
        self.assertTrue(all(c["trace_truncated"] and c["matched_count"] == 200 for c in result["channels"]))
        self.assertEqual(result["threshold_violation_count"], 0)

    def assert_rejected(self, request, code):
        result = compare_digital_twin(request)
        self.assertEqual(result["status"], "rejected", result)
        self.assertEqual(result["issues"][0]["code"], code)
        return result

    def test_exact_timestamp_metrics_use_independent_oracle(self):
        request = fixture()
        original = copy.deepcopy(request)
        result = compare_digital_twin(request)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["model_status"], "experimental")
        self.assertEqual(result["matched_sample_count"], 2)
        self.assertEqual(result["unmatched_prediction_sample_count"], 1)
        self.assertEqual(result["unmatched_telemetry_sample_count"], 1)
        channels = {item["id"]: item for item in result["channels"]}
        voltage_errors = [0.1, -0.3]
        self.assertAlmostEqual(channels["voltage"]["max_abs_error"], 0.3)
        self.assertAlmostEqual(channels["voltage"]["rmse"],
                               math.sqrt(sum(v * v for v in voltage_errors) / 2))
        self.assertEqual(channels["voltage"]["threshold_violation_count"], 1)
        self.assertEqual(channels["current"]["threshold_violation_count"], 1)
        self.assertEqual([point["time_s"] for point in channels["voltage"]["trace"]], [0.0, 1.0])
        self.assertEqual(channels["voltage"]["trace"][1]["predicted"], 5.1)
        self.assertEqual(channels["voltage"]["trace"][1]["measured"], 4.8)
        expected_digest = hashlib.sha256(json.dumps(
            request, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode()).hexdigest()
        self.assertEqual(result["request_sha256"], expected_digest)
        self.assertEqual(request, original)

    def test_status_is_preserved_without_validation_claim(self):
        for status in ("approximate", "experimental", "validated", "unsupported"):
            request = fixture()
            request["model_status"] = status
            result = compare_digital_twin(request)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["model_status"], status)
            self.assertTrue(any("does not validate physics" in item for item in result["limitations"]))

    def test_stale_prediction_or_telemetry_identity_is_rejected(self):
        for series, field in (("prediction", "model_revision"), ("telemetry", "model_id")):
            request = fixture()
            request[series][field] = "stale"
            with self.subTest(series=series, field=field):
                self.assert_rejected(request, "MODEL_IDENTITY_MISMATCH")

    def test_per_series_unit_and_channel_declarations_are_admitted(self):
        request = fixture()
        request["telemetry"]["channels"][0]["unit"] = "mV"
        self.assert_rejected(request, "CHANNEL_DECLARATION_MISMATCH")
        request = fixture()
        request["prediction"]["channels"][0]["id"] = "bus_voltage"
        self.assert_rejected(request, "CHANNEL_DECLARATION_MISMATCH")

    def test_malformed_values_channels_and_contract_are_rejected(self):
        cases = []
        request = fixture()
        request["channels"].append(copy.deepcopy(request["channels"][0]))
        cases.append((request, "DUPLICATE_CHANNEL"))
        request = fixture()
        del request["prediction"]["samples"][0]["values"]["current"]
        cases.append((request, "CHANNEL_VALUES_MISMATCH"))
        request = fixture()
        request["telemetry"]["samples"][0]["values"]["unknown"] = 1.0
        cases.append((request, "CHANNEL_VALUES_MISMATCH"))
        request = fixture()
        request["channels"][0]["tolerance"] = -0.1
        cases.append((request, "INVALID_NUMBER"))
        request = fixture()
        request["prediction"]["samples"][0]["values"]["voltage"] = True
        cases.append((request, "INVALID_NUMBER"))
        request = fixture()
        request["contract"] = "spike/digital-twin-request/v0"
        cases.append((request, "UNSUPPORTED_CONTRACT"))
        for request, code in cases:
            with self.subTest(code=code):
                self.assert_rejected(request, code)

    def test_time_rules_empty_series_and_no_exact_overlap(self):
        request = fixture()
        request["prediction"]["samples"][1]["time_s"] = 0.0
        self.assert_rejected(request, "TIME_ORDER")
        request = fixture()
        request["telemetry"]["samples"][0]["time_s"] = -1.0
        self.assert_rejected(request, "INVALID_NUMBER")
        request = fixture()
        request["prediction"]["samples"] = []
        self.assert_rejected(request, "SAMPLE_LIMIT")
        request = fixture()
        for index, sample in enumerate(request["telemetry"]["samples"]):
            sample["time_s"] = index + 10.0
        self.assert_rejected(request, "NO_MATCHED_SAMPLES")

    def test_nonfinite_and_derived_overflow_are_rejected(self):
        request = fixture()
        request["telemetry"]["samples"][0]["values"]["voltage"] = float("nan")
        result = self.assert_rejected(request, "NON_CANONICAL_INPUT")
        self.assertIsNone(result["request_sha256"])
        request = fixture()
        request["prediction"]["samples"][0]["values"]["voltage"] = -1e308
        request["telemetry"]["samples"][0]["values"]["voltage"] = 1e308
        self.assert_rejected(request, "NUMERICAL_RANGE")

    def test_canonical_request_size_is_bounded_before_admission(self):
        request = fixture()
        with patch("python.spike_core.digital_twin.MAX_CANONICAL_BYTES", 100):
            first = compare_digital_twin(request)
            second = compare_digital_twin(request)
        self.assertEqual(first, second)
        self.assertEqual(first["issues"][0]["code"], "REQUEST_SIZE_LIMIT")
        self.assertIsNone(first["request_sha256"])

    def test_trace_is_bounded_but_metrics_cover_all_matches(self):
        request = fixture()
        count = 2050
        request["prediction"]["samples"] = [
            {"time_s": float(i), "values": {"voltage": 5.0, "current": 1.0}}
            for i in range(count)
        ]
        request["telemetry"]["samples"] = [
            {"time_s": float(i), "values": {"voltage": 5.1, "current": 1.0}}
            for i in range(count)
        ]
        result = compare_digital_twin(request)
        voltage = result["channels"][0]
        self.assertEqual(voltage["matched_count"], count)
        self.assertEqual(len(voltage["trace"]), 2048)
        self.assertTrue(voltage["trace_truncated"])
        self.assertEqual(voltage["threshold_violation_count"], 0)

    def test_extreme_finite_residual_has_finite_rmse(self):
        request = fixture()
        for series, value in (("prediction", -5e307), ("telemetry", 5e307)):
            for sample in request[series]["samples"][:2]:
                sample["values"]["voltage"] = value
        result = compare_digital_twin(request)
        self.assertEqual(result["status"], "completed", result)
        voltage = result["channels"][0]
        self.assertEqual(voltage["max_abs_error"], 1e308)
        self.assertTrue(math.isfinite(voltage["rmse"]))
        self.assertEqual(voltage["rmse"], 1e308)

    def test_request_and_both_result_shapes_conform_to_schemas(self):
        import jsonschema
        root = Path(__file__).resolve().parents[2]
        request_schema = json.loads((root / "schemas/digital-twin-request-v1.schema.json").read_text())
        result_schema = json.loads((root / "schemas/digital-twin-result-v1.schema.json").read_text())
        jsonschema.Draft202012Validator.check_schema(request_schema)
        jsonschema.Draft202012Validator.check_schema(result_schema)
        request = fixture()
        jsonschema.validate(request, request_schema)
        jsonschema.validate(compare_digital_twin(request), result_schema)
        request["telemetry"]["model_revision"] = "stale"
        jsonschema.validate(compare_digital_twin(request), result_schema)


if __name__ == "__main__":
    unittest.main()
