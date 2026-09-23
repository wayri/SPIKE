import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from python.spike_core.si_protocol_suites import (
    SiProtocolSuiteError,
    plan_si_protocol_analysis,
    validate_si_protocol_suite,
)
from python.spike_core.service import handle


def fixture():
    return {
        "contract": "spike/si-protocol-suite/v1",
        "id": "user.si.reference",
        "name": "Reference channel",
        "family": "CUSTOM",
        "revision": "0.1.0",
        "description": "Controlled declarative protocol-suite fixture.",
        "signaling": "differential",
        "encoding": "user_defined",
        "topology": ["transmitter", "channel", "receiver"],
        "requiredInputs": ["stackup", "ports", "models", "limits"],
        "analyses": [
            {"id": "topology", "name": "Topology", "requiredCapabilities": ["design_ir", "ports"], "status": "available_input_review"},
            {"id": "eye", "name": "Eye", "requiredCapabilities": ["validated_eye_engine", "source_receiver_models"], "status": "solver_gated"},
        ],
        "rules": [{"id": "user.eye-height", "metric": "eye_height", "operator": "minimum", "value": 0.1, "unit": "V", "source": "user", "note": "Fixture-only user threshold."}],
        "provenance": {"title": "User fixture", "locator": "fixture://si", "access": "user_defined", "reviewedOn": "2026-08-30"},
        "qualification": "setup_only",
        "custom": True,
    }


class SiProtocolSuiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).parents[2] / "schemas" / "si-protocol-suite-v1.schema.json"
        cls.schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)

    def test_schema_and_runtime_accept_declarative_suite(self):
        value = fixture()
        Draft202012Validator(self.schema).validate(value)
        result = validate_si_protocol_suite(value)
        self.assertEqual(result["status"], "valid")
        self.assertFalse(result["compliance_claimed"])
        self.assertEqual(result["code_execution"], "not_permitted_by_declarative_contract")
        self.assertEqual(len(result["suite_sha256"]), 64)

    def test_custom_suite_cannot_self_assert_validation(self):
        value = fixture()
        value["qualification"] = "validated"
        with self.assertRaisesRegex(SiProtocolSuiteError, "cannot self-assert"):
            validate_si_protocol_suite(value)

    def test_schema_rejects_unknown_fields(self):
        value = fixture()
        value["python"] = "eval('unsafe')"
        with self.assertRaises(ValidationError):
            Draft202012Validator(self.schema).validate(value)
        with self.assertRaisesRegex(SiProtocolSuiteError, "unknown"):
            validate_si_protocol_suite(value)

    def test_plan_is_staged_and_fail_closed(self):
        result = plan_si_protocol_analysis(fixture(), ["design_ir", "ports"])
        self.assertEqual(result["stages"][0]["status"], "configurable")
        self.assertEqual(result["stages"][1]["status"], "blocked")
        self.assertIn("validated_eye_engine", result["stages"][1]["missing_capabilities"])
        self.assertFalse(result["can_claim_protocol_compliance"])

    def test_worker_validation_and_plan_methods(self):
        validated = handle({"method": "validate_si_protocol_suite", "params": {"suite": fixture()}})
        self.assertTrue(validated["ok"])
        planned = handle({"method": "plan_si_protocol_analysis", "params": {
            "suite": fixture(), "available_capabilities": ["design_ir", "ports"],
        }})
        self.assertTrue(planned["ok"])
        self.assertEqual(planned["result"]["stages"][1]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
