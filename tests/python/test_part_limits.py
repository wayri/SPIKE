# SPDX-License-Identifier: Apache-2.0
import copy
import unittest
from python.spike_core.part_limits import evaluate_part_limits
from python.spike_core.engineering_review import review_engineering
from python.spike_core.service import handle


def rule(**changes):
    return dict(id="rail-u1", occurrence_id="board-a", component_id="u1", label="Supply at U1",
                quantity="voltage", unit="V", lower=None, upper="5", reference="0", value="4",
                rating_source="Authored test operating rating, not manufacturer data",
                measurement_source="Authored scalar test observation", evidence_status="reviewed", **changes)


COMPONENTS = [{"occurrence_id": "board-a", "component_id": "u1", "reference": "U1", "dnp": False}]


class PartLimitTests(unittest.TestCase):
    def check(self, **changes):
        item = rule(); item.update(changes)
        report = evaluate_part_limits([item], COMPONENTS)
        return report, report["rows"][0]

    def test_upper_limit_boundary_overstress_and_no_source_mutation(self):
        source = [rule()]; saved = copy.deepcopy(source)
        report = evaluate_part_limits(source, COMPONENTS)
        self.assertEqual(source, saved)
        self.assertEqual(report["overall_status"], "PASS")
        self.assertEqual(report["rows"][0]["stress_percent"], "80")
        self.assertEqual(report["rows"][0]["headroom_percent"], "20")
        for value, status, stress, margin in [("5", "PASS", "100", "0"), ("6", "FAIL", "120", "-20")]:
            report, row = self.check(value=value)
            self.assertEqual((row["status"], row["stress_percent"], row["headroom_percent"]), (status, stress, margin))

    def test_lower_and_bipolar_windows(self):
        _, row = self.check(lower="3", upper="3.6", reference="3.3", value="3.15")
        self.assertEqual(row["stress_percent"], "50")
        _, row = self.check(quantity="current", unit="A", lower="-5", upper="5", reference="0", value="-6")
        self.assertEqual((row["status"], row["stress_percent"]), ("FAIL", "120"))
        _, row = self.check(lower="3", upper=None, reference="4", value="2.5")
        self.assertEqual(row["stress_percent"], "150")

    def test_temperature_offset_invariance_and_mechanical_units(self):
        _, c = self.check(quantity="temperature", unit="degC", upper="125", reference="25", value="100")
        _, k = self.check(quantity="temperature", unit="K", upper="398.15", reference="298.15", value="373.15")
        self.assertEqual(c["stress_percent"], "75")
        self.assertEqual(c["stress_percent"], k["stress_percent"])
        _, row = self.check(quantity="stress", unit="MPa", upper="250", value="200")
        self.assertEqual(row["headroom_percent"], "20")

    def test_missing_unreviewed_and_coverage_are_not_passes(self):
        for changes in ({"value": None}, {"lower": None, "upper": None}, {"rating_source": ""},
                        {"measurement_source": ""}, {"evidence_status": "unreviewed"}):
            report, row = self.check(**changes)
            self.assertEqual(report["overall_status"], "INCOMPLETE")
            self.assertEqual(row["status"], "UNKNOWN")
        report = evaluate_part_limits([rule()], COMPONENTS + [{**COMPONENTS[0], "component_id": "u2"}])
        self.assertEqual(report["overall_status"], "INCOMPLETE")
        self.assertEqual(len(report["unchecked_components"]), 1)
        self.assertEqual(evaluate_part_limits([], COMPONENTS)["overall_status"], "INCOMPLETE")
        _, row = self.check(reference=None)
        self.assertIsNone(row["stress_percent"])

    def test_fail_is_not_rounded_away_and_extremes_are_bounded(self):
        _, row = self.check(value="5.00000000000000001")
        self.assertEqual(row["comparison_status"], "FAIL")
        self.assertEqual(row["stress_percent"], "100")  # Display rounding never controls status.
        _, row = self.check(upper="1e-30", value="1e30")
        self.assertTrue(row["stress_percent"].startswith("1"))
        self.assertEqual(row["status"], "FAIL")

    def test_fail_closed_admission(self):
        for changes in ({"value": True}, {"value": "nan"}, {"value": "Infinity"}, {"value": "1e31"},
                        {"upper": "0"}, {"lower": "6"}, {"component_id": "absent"}, {"unit": "mV"},
                        {"quantity": "temperature", "unit": "K", "value": "-1"}):
            with self.assertRaises(ValueError):
                self.check(**changes)
        with self.assertRaises(ValueError):
            evaluate_part_limits([rule(), rule()], COMPONENTS)
        with self.assertRaises(ValueError):
            evaluate_part_limits([{**rule(), "surprise": 1}], COMPONENTS)
        report = evaluate_part_limits([rule()], [{**COMPONENTS[0], "dnp": True}])
        self.assertEqual(report["rows"][0]["status"], "NOT_APPLICABLE")

    def test_existing_review_worker_route_has_identical_report_and_snapshot_binding(self):
        request = {"contract": "spike/engineering-review-request/v1", "boards": [
            {"occurrence_id": "board-a", "design": {"components": [{"id": "u1", "reference": "U1"}]}}],
            "overrides": [], "part_limits": [rule()]}
        result = review_engineering(request)
        self.assertEqual(result["part_limit_report"]["overall_status"], "PASS")
        self.assertEqual(handle({"method": "review_engineering", "params": {"request": request}})["result"], result)
        request["part_limits"][0]["value"] = "6"
        self.assertNotEqual(result["snapshot_sha256"], review_engineering(request)["snapshot_sha256"])

    def test_part_summary_uses_worst_reviewed_allowance_and_unknowns_stay_unknown(self):
        thermal = {**rule(), "id": "temperature", "quantity": "temperature", "unit": "degC", "upper": "125", "reference": "25", "value": "100"}
        report = evaluate_part_limits([rule(), thermal], COMPONENTS)
        self.assertEqual(report["part_summary"][0]["stress_percent"], "80")
        self.assertEqual(report["part_summary"][0]["headroom_percent"], "20")
        thermal["evidence_status"] = "unreviewed"
        report = evaluate_part_limits([rule(), thermal], COMPONENTS)
        self.assertEqual(report["part_summary"][0]["status"], "UNKNOWN")
        self.assertIsNone(report["part_summary"][0]["stress_percent"])

    def test_public_example_schema(self):
        import json
        from pathlib import Path
        import jsonschema
        root = Path(__file__).resolve().parents[2]
        example = json.loads((root / "examples/part_limits/part-limits.json").read_text(encoding="utf-8"))
        schema = json.loads((root / "schemas/part-limits-v1.schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(example, schema)
        report_schema = json.loads((root / "schemas/part-limit-report-v1.schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(report_schema)
        jsonschema.validate(evaluate_part_limits(example["rules"], COMPONENTS), report_schema)


if __name__ == "__main__":
    unittest.main()
