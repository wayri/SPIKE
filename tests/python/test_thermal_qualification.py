import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from python.spike_core.thermal_qualification import (
    QUALIFICATION_CONTRACT,
    required_qualification_gates,
    validate_thermal_qualification,
)


ROOT = Path(__file__).resolve().parents[2]
PHYSICS = ["solid_conduction", "thermal_contacts", "conjugate_heat_transfer", "radiation", "fans", "potting", "electrothermal_iteration"]


def evidence() -> dict:
    fixtures = []
    for index, gate in enumerate(required_qualification_gates(PHYSICS)):
        reference_type = "analytic"
        if gate == "independent_correlation":
            reference_type = "independent_solver"
        elif gate == "measured_correlation":
            reference_type = "measured"
        fixtures.append({
            "id": gate, "gate": gate, "status": "passed",
            "fixture_sha256": f"{index + 1:064x}", "result_sha256": f"{index + 100:064x}",
            "reference_type": reference_type, "reference_id": f"reference:{gate}",
            "tolerance": 0.05, "observed": 0.01,
        })
    return {
        "contract": QUALIFICATION_CONTRACT, "evidence_id": "fixture-qualified-v1",
        "solver": {"id": "fixture.thermal", "version": "1.2.3"},
        "platforms": ["windows-x64", "linux-x64"], "capabilities": PHYSICS,
        "fixtures": fixtures,
    }


class ThermalQualificationTests(unittest.TestCase):
    def validate(self, value):
        return validate_thermal_qualification(value, solver_id="fixture.thermal", solver_version="1.2.3", requested_physics=PHYSICS)

    def test_metrics_require_nonnegative_finite_json_numbers(self):
        for field in ("observed", "tolerance"):
            for number in (-1, float("nan"), float("inf"), float("-inf"), True, False, "0.01", None, [], {}, 10**1000):
                with self.subTest(field=field, number_type=type(number).__name__):
                    value = evidence()
                    value["fixtures"][0][field] = number
                    result = self.validate(value)
                    self.assertFalse(result["valid"], result)
                    self.assertNotIn(value["fixtures"][0]["gate"], result["covered_gates"])
                    json.dumps(result, allow_nan=False)

    def test_zero_and_inclusive_tolerance_are_accepted_without_mutation(self):
        for observed, tolerance in ((0, 0), (0.05, 0.05), (1, 1)):
            value = evidence()
            value["fixtures"][0].update(observed=observed, tolerance=tolerance)
            original = copy.deepcopy(value)
            result = self.validate(value)
            self.assertTrue(result["valid"], result)
            self.assertEqual(value, original)

    def test_observation_above_tolerance_is_rejected(self):
        value = evidence()
        value["fixtures"][0].update(observed=0.051, tolerance=0.05)
        self.assertFalse(self.validate(value)["valid"])

    def test_swapped_correlation_reference_types_are_rejected(self):
        value = evidence()
        for row in value["fixtures"]:
            if row["gate"] == "independent_correlation":
                row["reference_type"] = "measured"
            elif row["gate"] == "measured_correlation":
                row["reference_type"] = "independent_solver"
        result = self.validate(value)
        self.assertFalse(result["valid"])
        self.assertNotIn("independent_correlation", result["covered_gates"])
        self.assertNotIn("measured_correlation", result["covered_gates"])

    def test_unrelated_gate_reference_cannot_satisfy_correlation(self):
        for gate in ("independent_correlation", "measured_correlation"):
            with self.subTest(gate=gate):
                value = evidence()
                fixture = next(row for row in value["fixtures"] if row["gate"] == gate)
                reference_type = fixture["reference_type"]
                fixture["reference_type"] = "analytic"
                next(row for row in value["fixtures"] if row["gate"] == "energy_conservation")["reference_type"] = reference_type
                result = self.validate(value)
                self.assertFalse(result["valid"])
                self.assertNotIn(gate, result["covered_gates"])

    def test_complete_digest_bound_cross_platform_evidence_passes(self):
        result = validate_thermal_qualification(evidence(), solver_id="fixture.thermal", solver_version="1.2.3", requested_physics=PHYSICS)
        self.assertTrue(result["valid"], result)
        self.assertIn("measured_correlation", result["covered_gates"])
        schema = json.loads((ROOT / "schemas" / "thermal-solver-qualification-evidence-v1.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(evidence())
        manifest = json.loads((ROOT / "schemas" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schemas"][QUALIFICATION_CONTRACT], "thermal-solver-qualification-evidence-v1.schema.json")

    def test_missing_measured_fixture_and_linux_package_fail_closed(self):
        value = copy.deepcopy(evidence())
        value["platforms"] = ["windows-x64"]
        value["fixtures"] = [item for item in value["fixtures"] if item["gate"] != "measured_correlation"]
        result = validate_thermal_qualification(value, solver_id="fixture.thermal", solver_version="1.2.3", requested_physics=PHYSICS)
        self.assertFalse(result["valid"])
        self.assertIn("linux-x64", " ".join(result["issues"]))
        self.assertIn("measured", " ".join(result["issues"]))

    def test_solver_version_and_digest_tampering_are_rejected(self):
        value = copy.deepcopy(evidence())
        value["fixtures"][0]["result_sha256"] = "not-a-digest"
        result = validate_thermal_qualification(value, solver_id="fixture.thermal", solver_version="9", requested_physics=PHYSICS)
        self.assertFalse(result["valid"])
        self.assertIn("version", " ".join(result["issues"]))
        self.assertIn("SHA-256", " ".join(result["issues"]))


if __name__ == "__main__":
    unittest.main()
