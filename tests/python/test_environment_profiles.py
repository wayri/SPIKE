import json
import unittest
from pathlib import Path

from python.spike_core.environment_profiles import (
    ENVIRONMENT_PROFILE_CONTRACT,
    ENVIRONMENT_PROFILE_VALIDATION_CONTRACT,
    EnvironmentProfileError,
    create_user_defined_profile,
    get_environment_profile,
    list_environment_profiles,
    materialize_environment_profile,
    validate_environment_profile,
)


class EnvironmentProfileTests(unittest.TestCase):
    def test_catalog_contains_every_required_environment_class(self):
        summaries = list_environment_profiles()
        self.assertEqual(
            {item["profile_id"] for item in summaries},
            {
                "standard-lab-air",
                "sealed-potted",
                "automotive",
                "marine",
                "aerospace-altitude",
                "vacuum-space",
                "user-defined",
            },
        )
        self.assertEqual(len(summaries), 7)

    def test_presets_are_versioned_traceable_and_never_claim_certification(self):
        for summary in list_environment_profiles():
            profile = get_environment_profile(summary["profile_id"])
            self.assertEqual(profile["contract"], ENVIRONMENT_PROFILE_CONTRACT)
            self.assertEqual(profile["revision"], "1.0.0")
            self.assertFalse(profile["validity"]["certification_claimed"])
            self.assertEqual(profile["validity"]["certification_basis"], [])
            self.assertTrue(profile["provenance"]["sources"])
            self.assertTrue(profile["provenance"]["parameter_sources"])

    def test_standard_lab_profile_supplies_all_domain_inputs_but_requires_review(self):
        result = validate_environment_profile(get_environment_profile("standard-lab-air"))
        self.assertEqual(result["contract"], ENVIRONMENT_PROFILE_VALIDATION_CONTRACT)
        self.assertTrue(result["can_supply_solver_inputs"])
        self.assertEqual(result["status"], "review_required")
        self.assertTrue(all(item["inputs_complete"] for item in result["domain_readiness"].values()))
        self.assertEqual(result["certification"]["status"], "not_assessed")
        self.assertFalse(result["certification"]["claimed"])

    def test_potted_profile_carries_thermal_and_dielectric_material_inputs(self):
        profile = get_environment_profile("sealed-potted")
        material = profile["physical"]["encapsulation"]
        self.assertTrue(material["enabled"])
        self.assertGreater(material["thermal_conductivity_w_m_k"], 0)
        self.assertGreater(material["relative_permittivity"], 1)
        result = validate_environment_profile(profile, ("thermal", "si", "emi"))
        self.assertTrue(result["can_supply_solver_inputs"])

        incomplete = materialize_environment_profile(
            "sealed-potted",
            {"physical": {"encapsulation": {"relative_permittivity": None}}},
        )
        incomplete_result = validate_environment_profile(incomplete, ("si",))
        self.assertFalse(incomplete_result["can_supply_solver_inputs"])
        self.assertIn(
            "ENV_PHYSICAL_INPUT_REQUIRED",
            {item["code"] for item in incomplete_result["issues"]},
        )

    def test_vacuum_rejects_continuum_flow_and_certification_claims(self):
        profile = materialize_environment_profile(
            "vacuum-space",
            {
                "physical": {
                    "flow": {"regime": "forced", "velocity_m_s": [2.0, 0.0, 0.0]},
                    "convection": {"model": "forced"},
                },
                "validity": {"certification_claimed": True, "certification_basis": ["unsupported claim"]},
            },
        )
        result = validate_environment_profile(profile, ("thermal",))
        codes = {item["code"] for item in result["issues"]}
        self.assertFalse(result["can_supply_solver_inputs"])
        self.assertIn("ENV_VACUUM_CONVECTION_FORBIDDEN", codes)
        self.assertIn("ENV_VACUUM_FLOW_FORBIDDEN", codes)
        self.assertIn("ENV_CERTIFICATION_CLAIM_FORBIDDEN", codes)

    def test_user_defined_profile_is_blocked_until_physical_inputs_are_supplied(self):
        draft = create_user_defined_profile("chamber-a", "Chamber A")
        result = validate_environment_profile(draft)
        self.assertFalse(result["can_supply_solver_inputs"])
        self.assertIn(
            "ENV_REQUIRED_OVERRIDES_UNRESOLVED",
            {item["code"] for item in result["issues"]},
        )

        lab_physical = get_environment_profile("standard-lab-air")["physical"]
        complete = create_user_defined_profile(
            "chamber-a",
            "Chamber A",
            lab_physical,
            source_title="Chamber A measured operating point",
            source_locator="lab://chamber-a/run-42",
        )
        completed_result = validate_environment_profile(complete)
        self.assertTrue(completed_result["can_supply_solver_inputs"])
        self.assertEqual(completed_result["status"], "review_required")

    def test_operating_point_outside_declared_range_is_rejected(self):
        profile = materialize_environment_profile(
            "standard-lab-air",
            {"physical": {"thermal": {"ambient_temperature_k": 350.0}}},
        )
        result = validate_environment_profile(profile, ("thermal",))
        self.assertFalse(result["can_supply_solver_inputs"])
        self.assertIn(
            "ENV_OPERATING_POINT_OUTSIDE_VALIDITY",
            {item["code"] for item in result["issues"]},
        )

    def test_materialization_does_not_mutate_catalog_profiles(self):
        modified = materialize_environment_profile(
            "automotive",
            {"physical": {"thermal": {"ambient_temperature_k": 373.15}}},
        )
        original = get_environment_profile("automotive")
        self.assertEqual(original["physical"]["thermal"]["ambient_temperature_k"], 358.15)
        self.assertEqual(modified["physical"]["thermal"]["ambient_temperature_k"], 373.15)
        self.assertEqual(modified["provenance"]["transformations"][0]["kind"], "explicit_override")

    def test_unknown_profile_has_an_explicit_error(self):
        with self.assertRaises(EnvironmentProfileError):
            get_environment_profile("not-a-profile")

    def test_schema_is_valid_json_and_matches_contract(self):
        schema_path = Path(__file__).parents[2] / "schemas" / "environment-profile-v1.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["properties"]["contract"]["const"], ENVIRONMENT_PROFILE_CONTRACT)
        self.assertEqual(schema["properties"]["validity"] if "validity" in schema["properties"] else None, {"$ref": "#/$defs/validity"})
        self.assertFalse(schema["$defs"]["validity"]["properties"]["certification_claimed"]["const"])
        self.assertEqual(schema["$defs"]["validity"]["properties"]["certification_basis"]["maxItems"], 0)


if __name__ == "__main__":
    unittest.main()
