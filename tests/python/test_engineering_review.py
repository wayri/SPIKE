# SPDX-License-Identifier: Apache-2.0
import math
import unittest

from python.spike_core.engineering_review import quick_engineering_tool, review_engineering


def request():
    return {"contract": "spike/engineering-review-request/v1", "boards": [
        {"occurrence_id": "left", "design": {"components": [
            {"id": "r1", "reference": "R1", "value": "10k", "footprint": "R_0603", "properties": {"MPN": "A"}},
            {"id": "r2", "reference": "R2", "value": "10k", "footprint": "R_0603", "metadata": {"mpn": "A"}},
            {"id": "c1", "reference": "C1", "value": "1u", "footprint": "C_0603"}], "stackup": [{"name": "F.Cu"}]}},
        {"occurrence_id": "right", "design": {"components": [
            {"id": "r1", "reference": "R1", "value": "10k", "footprint": "R_0603", "properties": {"MPN": "A"}}]}}],
        "overrides": [
            {"occurrence_id": "left", "component_id": "r1", "unit_cost": "0.10", "currency": "USD", "mass_g": "0.01", "power_w": "0.1"},
            {"occurrence_id": "left", "component_id": "r2", "unit_cost": "0.20", "currency": "EUR", "mass_g": "0.02", "power_w": "0.2"},
            {"occurrence_id": "left", "component_id": "c1", "dnp": True, "unit_cost": "99", "currency": "USD"}]}


class EngineeringReviewTests(unittest.TestCase):
    def test_groups_are_occurrence_scoped_and_dnp_is_excluded_from_totals(self):
        result = review_engineering(request())
        self.assertEqual(result["contract"], "spike/engineering-review-result/v1")
        self.assertEqual(result["summary"]["components"], 4)
        self.assertEqual(result["summary"]["dnp_components"], 1)
        self.assertEqual(result["summary"]["cost"]["subtotals_by_currency"], {"EUR": "0.2", "USD": "0.1"})
        groups = {(g["occurrence_id"], g["value"], g["dnp"]): g["count"] for g in result["grouped_bom"]}
        self.assertEqual(groups[("left", "10k", False)], 2)
        self.assertEqual(groups[("right", "10k", False)], 1)
        left_group = next(g for g in result["grouped_bom"] if g["occurrence_id"] == "left" and g["value"] == "10k")
        self.assertEqual(left_group["coverage"]["cost"]["subtotals_by_currency"], {"EUR": "0.2", "USD": "0.1"})
        self.assertEqual(left_group["coverage"]["power_w"]["subtotal"], "0.3")
        self.assertEqual(result["summary"]["mass_g"], {"known_components": 2, "unknown_components": 1, "total": "0.03"})
        self.assertTrue(any(f["code"] == "physical_stackup_absent" and f["occurrence_id"] == "right"
                            for f in result["readiness"]["findings"]))
        self.assertEqual(result["readiness"]["native_drc"], "unknown")

    def test_duplicate_reference_is_local_to_occurrence(self):
        value = request()
        value["boards"][0]["design"]["components"][1]["reference"] = "R1"
        findings = review_engineering(value)["readiness"]["findings"]
        duplicates = [f for f in findings if f["code"] == "duplicate_reference"]
        self.assertEqual(len(duplicates), 2)
        self.assertTrue(all(f["occurrence_id"] == "left" for f in duplicates))

    def test_invalid_inputs_and_override_contract(self):
        value = request()
        value["overrides"][0]["unit_cost"] = math.inf
        with self.assertRaisesRegex(ValueError, "finite"):
            review_engineering(value)
        value = request()
        value["overrides"][0]["surprise"] = 1
        with self.assertRaisesRegex(ValueError, "unknown keys"):
            review_engineering(value)
        value = request()
        value["overrides"][0].pop("currency")
        with self.assertRaisesRegex(ValueError, "requires currency"):
            review_engineering(value)
        value = request()
        value["overrides"][0]["unit_cost"] = "1e999999999999999999"
        with self.assertRaisesRegex(ValueError, "exponent"):
            review_engineering(value)
        value = request()
        value["boards"][0]["design"]["metadata"] = "x" * (8 * 1024 * 1024)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            review_engineering(value)

    def test_snapshot_is_deterministic_and_sensitive(self):
        first = review_engineering(request())["snapshot_sha256"]
        self.assertEqual(first, review_engineering(request())["snapshot_sha256"])
        changed = request(); changed["boards"][0]["design"]["components"][0]["value"] = "11k"
        self.assertNotEqual(first, review_engineering(changed)["snapshot_sha256"])

    def test_null_override_clears_declared_values_and_canonical_fields_are_recognized(self):
        value = {"contract": "spike/engineering-review-request/v1", "boards": [{
            "occurrence_id": "board", "design": {
                "metadata": {"spike.v1.stackup": [{"name": "F.Cu", "thickness_mm": 0.035}]},
                "components": [{"id": "u1", "reference": "", "value": "IC", "footprint_id": "Package_QFP",
                                "properties": {"mpn": "ABC", "unit_cost": "2.5", "currency": "USD",
                                               "mass_g": "1.2", "power_w": "0.4"}}]}}],
            "overrides": [{"occurrence_id": "board", "component_id": "u1", "unit_cost": None,
                           "currency": None, "mass_g": None, "power_w": None}]}
        result = review_engineering(value)
        row = result["component_rows"][0]
        self.assertEqual(row["footprint"], "Package_QFP")
        self.assertIsNone(row["unit_cost"])
        self.assertIsNone(row["currency"])
        self.assertIsNone(row["mass_g"])
        self.assertIsNone(row["power_w"])
        codes = {finding["code"] for finding in result["readiness"]["findings"]}
        self.assertIn("missing_reference", codes)
        self.assertNotIn("physical_stackup_absent", codes)

    def test_currency_subtotal_preserves_tiny_contribution_next_to_large_value(self):
        value = {"contract": "spike/engineering-review-request/v1", "boards": [{
            "occurrence_id": "board", "design": {"components": [
                {"id": "a", "reference": "A", "footprint": "F", "properties": {"mpn": "A"}},
                {"id": "b", "reference": "B", "footprint": "F", "properties": {"mpn": "B"}}]}}],
            "overrides": [
                {"occurrence_id": "board", "component_id": "a", "unit_cost": "1e30", "currency": "USD"},
                {"occurrence_id": "board", "component_id": "b", "unit_cost": "1e-30", "currency": "USD"}]}
        subtotal = review_engineering(value)["summary"]["cost"]["subtotals_by_currency"]["USD"]
        self.assertEqual(subtotal, "1000000000000000000000000000000.000000000000000000000000000001")

    def test_quick_tools_against_analytic_values(self):
        divider = quick_engineering_tool({"contract": "spike/quick-engineering-tool-request/v1", "tool": "resistor_divider",
                                          "vin": "12", "r_top_ohm": "2000", "r_bottom_ohm": "1000"})
        self.assertEqual(divider["result"]["vout_v"], "4")
        trace = quick_engineering_tool({"contract": "spike/quick-engineering-tool-request/v1", "tool": "dc_trace_resistance",
                                        "length_m": "1", "width_m": "0.001", "thickness_m": "0.000035", "resistivity_ohm_m": "1.68e-8"})
        self.assertAlmostEqual(float(trace["result"]["resistance_ohm"]), 0.48)
        rc = quick_engineering_tool({"contract": "spike/quick-engineering-tool-request/v1", "tool": "rc_step",
                                     "time_s": "1", "r_ohm": "1000", "c_f": "0.001", "vin": "10"})
        self.assertAlmostEqual(float(rc["result"]["capacitor_voltage_v"]), 10 * (1 - math.exp(-1)), places=12)
        self.assertEqual(len(rc["request_sha256"]), 64)
        bounded = quick_engineering_tool({"contract": "spike/quick-engineering-tool-request/v1", "tool": "rc_step",
                                          "time_s": "1e30", "r_ohm": "1e-30", "c_f": "1e-30", "vin": "1e30"})
        self.assertTrue(all(math.isfinite(float(value)) for value in bounded["result"].values()))
        with self.assertRaisesRegex(ValueError, "positive"):
            quick_engineering_tool({"contract": "spike/quick-engineering-tool-request/v1", "tool": "rc_step",
                                    "time_s": 1, "r_ohm": 0, "c_f": 1, "vin": 1})


if __name__ == "__main__":
    unittest.main()
